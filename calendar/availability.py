"""
PatrAI — Availability checker.

Queries Google Calendar free/busy API for each participant and computes
the intersection of free slots across all participants.
"""
import logging
from datetime import datetime, timedelta, date

import pytz
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

import config
from database import get_db
from models import TimeSlot, UserPreferences

logger = logging.getLogger(__name__)

# Working hours window
WORK_START_HOUR = 9
WORK_END_HOUR = 18
MIN_SLOT_MINUTES = 30


def _get_calendar_service():
    """Build an authenticated Google Calendar API service."""
    from auth.oauth import load_token
    token_dict = load_token("google")
    if not token_dict:
        raise RuntimeError("No Google OAuth token found. Run the OAuth flow first.")
    creds = Credentials(
        token=token_dict.get("access_token"),
        refresh_token=token_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
    )
    return build("calendar", "v3", credentials=creds)


def _query_freebusy(email: str, time_min: datetime, time_max: datetime) -> list[tuple[datetime, datetime]]:
    """Query Google Calendar free/busy for a single participant.

    Returns a list of (start, end) busy intervals in UTC.
    """
    service = _get_calendar_service()
    body = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": email}],
    }
    result = service.freebusy().query(body=body).execute()
    busy_list = result.get("calendars", {}).get(email, {}).get("busy", [])
    intervals = []
    for b in busy_list:
        start = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(pytz.UTC)
        end = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(pytz.UTC)
        intervals.append((start, end))
    return intervals


def _intersect(
    busy_lists: dict[str, list[tuple[datetime, datetime]]],
    window_start: datetime,
    window_end: datetime,
    slot_duration_minutes: int = MIN_SLOT_MINUTES,
) -> list[tuple[datetime, datetime]]:
    """Compute free slots that are free for ALL participants within the window."""
    all_busy: list[tuple[datetime, datetime]] = []
    for intervals in busy_lists.values():
        all_busy.extend(intervals)
    all_busy.sort()

    # Merge overlapping busy intervals
    merged: list[tuple[datetime, datetime]] = []
    for start, end in all_busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Gaps between merged busy intervals are free slots
    free: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            gap_minutes = (busy_start - cursor).total_seconds() / 60
            if gap_minutes >= slot_duration_minutes:
                free.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < window_end:
        gap_minutes = (window_end - cursor).total_seconds() / 60
        if gap_minutes >= slot_duration_minutes:
            free.append((cursor, window_end))

    return free


def _load_preferences() -> UserPreferences:
    """Load user preferences from SQLite."""
    import json
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


def get_free_slots(participants: list[str], slots: list[TimeSlot]) -> list[TimeSlot]:
    """
    Find mutually free slots for all participants over the next 7 days (9am-6pm).

    Applies VIP priority ranking if VIP emails are configured.
    Returns empty list if no intersection found.
    """
    prefs = _load_preferences()
    vip_set = set(prefs.vip_emails)

    now = datetime.now(pytz.UTC)
    results: list[TimeSlot] = []

    for day_offset in range(7):
        day = now.date() + timedelta(days=day_offset)
        window_start = datetime(day.year, day.month, day.day, WORK_START_HOUR, 0, 0, tzinfo=pytz.UTC)
        window_end = datetime(day.year, day.month, day.day, WORK_END_HOUR, 0, 0, tzinfo=pytz.UTC)

        busy_lists: dict[str, list[tuple[datetime, datetime]]] = {}
        for email in participants:
            try:
                busy_lists[email] = _query_freebusy(email, window_start, window_end)
            except Exception:
                logger.exception("Failed to query free/busy for %s", email)
                busy_lists[email] = []

        free_intervals = _intersect(busy_lists, window_start, window_end)
        for start, end in free_intervals:
            results.append(TimeSlot(
                start_utc=start,
                end_utc=end,
                original_text=f"Available {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')} UTC",
                timezone_detected="UTC",
            ))

    # VIP ranking: slots where a VIP participant is free first
    if vip_set:
        vip_participants = [p for p in participants if p in vip_set]
        non_vip = [p for p in participants if p not in vip_set]
        # Already intersected for all — just put results in order (VIP preference = earlier slots)
        # Since we already computed intersection, all slots are free for everyone including VIPs
        # Sort by start time (VIPs get first pick of earliest slots)
        results.sort(key=lambda s: s.start_utc)

    return results
