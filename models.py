from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

VALID_INTENTS = frozenset({
    "scheduling_request",
    "availability_query",
    "status_update",
    "other",
    "needs_human_review",
})

VALID_NEGOTIATION_STATES = frozenset({
    "proposed",
    "counter_proposed",
    "escalated",
    "resolved",
})


class EmailData(BaseModel):
    message_id: str
    thread_id: str
    sender: EmailStr
    recipients: list[EmailStr]
    subject: str
    body: str
    timestamp: datetime


class TimeSlot(BaseModel):
    start_utc: datetime
    end_utc: datetime
    original_text: str
    timezone_detected: str


class ClassificationResult(BaseModel):
    intent: str   # scheduling_request | availability_query | status_update | other | needs_human_review
    confidence: float = Field(ge=0.0, le=1.0)
    chain_of_thought: str


class BookingRecord(BaseModel):
    event_id: str
    thread_id: str
    participants: list[EmailStr]
    slot_start: datetime
    slot_end: datetime
    fingerprint: str


class UserPreferences(BaseModel):
    max_daily_hours: float = 4.0
    vip_emails: list[EmailStr] = []
    focus_blocks: list[TimeSlot] = []


class NegotiationState(BaseModel):
    thread_id: str
    state: str   # proposed | counter_proposed | escalated | resolved
    round_count: int = 0
    history: list[str] = []


class WebhookPayload(BaseModel):
    message: dict
    subscription: str


class LoadCheckResult(BaseModel):
    allowed: bool
    total_hours: float
    alternative_dates: list[str] = []
