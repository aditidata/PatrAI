"""
PatrAI — Slot extractor using Duckling NER for time entity recognition.
"""
import logging
from datetime import datetime, timedelta

import pytz
import requests
from dateutil import parser as dateutil_parser

import config
from models import TimeSlot

logger = logging.getLogger(__name__)


def _call_duckling(text: str, ref_time: datetime) -> list[dict]:
    """POST to Duckling /parse and return the parsed JSON list.

    Raises requests.RequestException on connection error.
    """
    response = requests.post(
        f"{config.DUCKLING_URL}/parse",
        data={
            "locale": "en_US",
            "text": text,
            "dims": '["time"]',
            "reftime": ref_time.isoformat(),
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _normalize_to_utc(entity: dict) -> TimeSlot | None:
    """Parse a Duckling entity dict into a TimeSlot with UTC datetimes.

    Returns None for ambiguous or invalid entities.
    """
    value = entity.get("value", {})
    value_type = value.get("type")
    original_text = entity["body"]

    try:
        if value_type == "value":
            start_str = value["value"]
            start_dt = dateutil_parser.parse(start_str)
            end_dt = start_dt + timedelta(hours=1)

        elif value_type == "interval":
            from_obj = value.get("from")
            to_obj = value.get("to")

            # Open-ended interval — ambiguous, skip
            if to_obj is None:
                return None

            start_dt = dateutil_parser.parse(from_obj["value"])
            end_dt = dateutil_parser.parse(to_obj["value"])

        else:
            return None

        # Convert to UTC
        start_utc = start_dt.astimezone(pytz.UTC)
        end_utc = end_dt.astimezone(pytz.UTC)

        # Ensure ordering
        if start_utc >= end_utc:
            return None

        # Extract timezone label from the UTC offset in the original datetime string
        tz_detected = _extract_timezone_label(start_dt)

        return TimeSlot(
            start_utc=start_utc,
            end_utc=end_utc,
            original_text=original_text,
            timezone_detected=tz_detected,
        )

    except (KeyError, ValueError):
        return None


def _extract_timezone_label(dt: datetime) -> str:
    """Derive a human-readable timezone label from a datetime's UTC offset."""
    if dt.tzinfo is None:
        return "UTC"
    offset = dt.utcoffset()
    if offset is None:
        return "UTC"
    total_seconds = int(offset.total_seconds())
    hours = total_seconds // 3600
    if hours == 0:
        return "UTC"
    sign = "+" if hours >= 0 else "-"
    return f"UTC{sign}{abs(hours)}"


def extract_slots(body: str, ref_time: datetime | None = None) -> list[TimeSlot] | str:
    """Extract time slots from email body text using Duckling NER.

    Returns:
        list[TimeSlot]          — one or more parsed slots
        "needs_clarification"   — Duckling returned no usable time entities
        "needs_human_review"    — Duckling is unreachable
    """
    if ref_time is None:
        ref_time = datetime.utcnow()

    try:
        raw_entities = _call_duckling(body, ref_time)
    except requests.RequestException as exc:
        logger.error("Duckling unreachable: %s", exc)
        return "needs_human_review"

    time_entities = [e for e in raw_entities if e.get("dim") == "time"]

    slots: list[TimeSlot] = []
    for entity in time_entities:
        slot = _normalize_to_utc(entity)
        if slot is not None:
            slots.append(slot)

    if not slots:
        return "needs_clarification"

    return slots
