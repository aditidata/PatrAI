"""
PatrAI — Booking engine + Load guard.

Handles meeting-load protection, Google Calendar event creation,
confirmation emails, and booking log persistence.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, date

import pytz
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import config
from database import get_db
from models import TimeSlot, BookingRecord, UserPreferences, LoadCheckResult
from email_agent.utils import send_email

logger = logging.getLogger(__name__)


def _get_calendar_service():
    from auth.oauth import load_token
    token_dict = load_token("google")
    if not token_dict:
        raise RuntimeError("No Google OAuth token found.")
    creds = Credentials(
        token=token_dict.get("access_token"),
        refresh_token=token_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
    )
    return build("calendar", "v3", credentials=creds)


def _load_preferences() -> UserPreferences:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
        if row:
            return UserPreferences(
                max_daily_hours=row["max_daily_hours"],
                vip_emails=json.loads(row["vip_emails"]),
                focus_blocks=json.loads(row["focus_blocks"]),
            )
    finally:
        conn.close()
    return UserPreferences()


# ---------------------------------------------------------------------------
# Load guard
# ---------------------------------------------------------------------------

def _get_day_hours(day: date) -> float:
    """Query Google Calendar for total meeting duration on a given day (in hours)."""
    service = _get_calendar_service()
    tz = pytz.UTC
    time_min = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz).isoformat()
    time_max = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=tz).isoformat()
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = events_result.get("items", [])
    total_seconds = 0
    for event in events:
        start_str = event["start"].get("dateTime")
        end_str = event["end"].get("dateTime")
        if start_str and end_str:
            start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            total_seconds += max(0, (end - start).total_seconds())
    return total_seconds / 3600


def _suggest_alternatives(day: date, n: int = 3) -> list[str]:
    """Return n future dates with lighter meeting loads."""
    candidates = []
    check_day = day + timedelta(days=1)
    prefs = _load_preferences()
    while len(candidates) < n:
        try:
            hours = _get_day_hours(check_day)
            if hours < prefs.max_daily_hours:
                candidates.append(check_day.isoformat())
        except Exception:
            candidates.append(check_day.isoformat())
        check_day += timedelta(days=1)
    return candidates


def check_load(day: date, preferences: UserPreferences | None = None) -> LoadCheckResult:
    """Check if the given day is within the daily meeting-hour limit."""
    if preferences is None:
        preferences = _load_preferences()
    total_hours = _get_day_hours(day)
    if total_hours >= preferences.max_daily_hours:
        alternatives = _suggest_alternatives(day)
        return LoadCheckResult(allowed=False, total_hours=total_hours, alternative_dates=alternatives)
    return LoadCheckResult(allowed=True, total_hours=total_hours)


# ---------------------------------------------------------------------------
# Booking engine
# ---------------------------------------------------------------------------

def _compute_fingerprint(slot: TimeSlot, participants: list[str]) -> str:
    """SHA-256 fingerprint over canonical (slot, participants) for dedup."""
    canonical = json.dumps({
        "start": slot.start_utc.isoformat(),
        "end": slot.end_utc.isoformat(),
        "participants": sorted(participants),
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _create_event(slot: TimeSlot, participants: list[str], title: str = "Meeting", description: str = "") -> str:
    """Create a Google Calendar event and return the event ID."""
    service = _get_calendar_service()
    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": slot.start_utc.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": slot.end_utc.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": p} for p in participants],
        "sendUpdates": "all",
    }
    created = service.events().insert(calendarId="primary", body=event, sendNotifications=True).execute()
    return created["id"]


def _send_confirmation(booking: BookingRecord, cot: str) -> None:
    """Send a confirmation email to all participants."""
    subject = f"Meeting Confirmed: {booking.slot_start.strftime('%Y-%m-%d %H:%M')} UTC"
    body = (
        f"Your meeting has been booked.\n\n"
        f"Start: {booking.slot_start.isoformat()}\n"
        f"End:   {booking.slot_end.isoformat()}\n"
        f"Attendees: {', '.join(booking.participants)}\n\n"
        f"Why this slot was chosen:\n{cot}\n"
    )
    send_email(list(booking.participants), subject, body)


def book_meeting(slot: TimeSlot, participants: list[str], cot: str, title: str = "Meeting") -> BookingRecord | None:
    """
    Orchestrate load check, dedup, event creation, confirmation email, and log write.

    Returns the BookingRecord on success, or None if blocked/duplicate.
    """
    # Load guard
    load = check_load(slot.start_utc.date())
    if not load.allowed:
        logger.info("Booking blocked: daily load exceeded for %s", slot.start_utc.date())
        decline_body = (
            f"Unfortunately, the requested meeting on {slot.start_utc.date()} cannot be booked "
            f"because the daily meeting limit ({_load_preferences().max_daily_hours}h) has been reached.\n\n"
            f"Alternative dates with lighter loads:\n"
            + "\n".join(f"  - {d}" for d in load.alternative_dates)
        )
        send_email(participants, "Meeting Request Declined", decline_body)
        return None

    # Fingerprint dedup
    fingerprint = _compute_fingerprint(slot, participants)
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT 1 FROM bookings WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if existing:
            logger.info("Duplicate booking fingerprint — skipping: %s", fingerprint)
            return None

        # Create calendar event
        event_id = _create_event(slot, participants, title=title, description=cot)

        # Build record
        record = BookingRecord(
            event_id=event_id,
            thread_id="",  # caller should set this
            participants=participants,
            slot_start=slot.start_utc,
            slot_end=slot.end_utc,
            fingerprint=fingerprint,
        )

        # Persist to booking log
        conn.execute(
            """INSERT INTO bookings (event_id, thread_id, participants, slot_start, slot_end, fingerprint)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                record.event_id,
                record.thread_id,
                json.dumps(list(record.participants)),
                record.slot_start.isoformat(),
                record.slot_end.isoformat(),
                record.fingerprint,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Send confirmation
    _send_confirmation(record, cot)
    logger.info("Booking complete: event_id=%s", event_id)
    return record
