"""
PatrAI — Negotiation manager.

State machine: proposed → counter_proposed → escalated | resolved
Max 3 rounds before escalation to human owner.
"""
import json
import logging
from datetime import datetime, timedelta

import pytz

import config
from database import get_db
from models import NegotiationState, TimeSlot
from email_agent.utils import send_email

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3

VALID_TRANSITIONS = {
    "proposed": {"counter_proposed", "resolved"},
    "counter_proposed": {"counter_proposed", "resolved", "escalated"},
    "escalated": set(),
    "resolved": set(),
}


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _load_state(thread_id: str) -> NegotiationState | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM negotiations WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        if row:
            return NegotiationState(
                thread_id=row["thread_id"],
                state=row["state"],
                round_count=row["round_count"],
                history=json.loads(row["history"]),
            )
    finally:
        conn.close()
    return None


def _save_state(state: NegotiationState) -> None:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO negotiations (thread_id, state, round_count, history, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(thread_id) DO UPDATE SET
                   state = excluded.state,
                   round_count = excluded.round_count,
                   history = excluded.history,
                   updated_at = excluded.updated_at""",
            (state.thread_id, state.state, state.round_count, json.dumps(state.history)),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _llm_generate(prompt: str) -> str:
    """Call Ollama (primary) with OpenAI fallback."""
    import requests
    import openai
    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={"model": "llama3.1:8b", "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        logger.warning("Ollama failed in negotiation: %s — trying OpenAI", e)
    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content
    except Exception as e2:
        logger.error("Both LLMs failed in negotiation: %s", e2)
        return ""


def _generate_alternatives(thread_id: str) -> list[TimeSlot]:
    """Generate 3 alternative time slots starting from tomorrow."""
    now = datetime.now(pytz.UTC)
    slots = []
    for i in range(1, 4):
        start = (now + timedelta(days=i)).replace(hour=10, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        slots.append(TimeSlot(
            start_utc=start,
            end_utc=end,
            original_text=f"Alternative slot {i}",
            timezone_detected="UTC",
        ))
    return slots


def _format_alternatives(slots: list[TimeSlot]) -> str:
    lines = []
    for i, s in enumerate(slots, 1):
        lines.append(f"  {i}. {s.start_utc.strftime('%A, %B %d at %H:%M UTC')} – {s.end_utc.strftime('%H:%M UTC')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_negotiation(thread_id: str, participants: list[str]) -> None:
    """Initiate negotiation when no free slot was found."""
    alternatives = _generate_alternatives(thread_id)
    alt_text = _format_alternatives(alternatives)

    prompt = (
        f"Write a polite email proposing 3 alternative meeting times to participants "
        f"who could not find a common slot. Alternatives:\n{alt_text}\n"
        f"Keep it brief and professional."
    )
    email_body = _llm_generate(prompt) or (
        f"I was unable to find a common meeting time. Here are 3 alternatives:\n{alt_text}"
    )

    state = NegotiationState(
        thread_id=thread_id,
        state="proposed",
        round_count=1,
        history=[f"Round 1 — proposed alternatives:\n{alt_text}"],
    )
    _save_state(state)

    send_email(participants, "Meeting Time Proposal", email_body)
    logger.info("Negotiation started for thread_id=%s (round 1)", thread_id)


def handle_reply(thread_id: str, reply_body: str, participants: list[str]) -> NegotiationState:
    """Process a participant reply and advance the state machine."""
    state = _load_state(thread_id)
    if state is None:
        logger.warning("No negotiation state found for thread_id=%s", thread_id)
        state = NegotiationState(thread_id=thread_id, state="proposed", round_count=0)

    # Determine acceptance vs counter via LLM
    classify_prompt = (
        f"Does this email reply accept a proposed meeting time, or does it propose a counter?\n"
        f"Reply with exactly one word: 'accept' or 'counter'.\n\nEmail:\n{reply_body}"
    )
    decision = _llm_generate(classify_prompt).strip().lower()
    accepted = "accept" in decision

    state.history.append(f"Round {state.round_count} reply: {reply_body[:200]}")

    if accepted:
        state.state = "resolved"
        _save_state(state)
        logger.info("Negotiation resolved for thread_id=%s", thread_id)
        return state

    # Counter-proposal
    state.round_count += 1
    if state.round_count > MAX_ROUNDS:
        _escalate(thread_id, state, participants)
        return state

    state.state = "counter_proposed"
    alternatives = _generate_alternatives(thread_id)
    alt_text = _format_alternatives(alternatives)
    state.history.append(f"Round {state.round_count} — new alternatives:\n{alt_text}")
    _save_state(state)

    email_body = (
        f"Thank you for your reply. Here are {MAX_ROUNDS - state.round_count + 1} more options:\n{alt_text}"
    )
    send_email(participants, "Updated Meeting Proposal", email_body)
    logger.info("Negotiation counter-proposed for thread_id=%s (round %d)", thread_id, state.round_count)
    return state


def _escalate(thread_id: str, state: NegotiationState, participants: list[str]) -> None:
    """Escalate to human owner after max rounds exceeded."""
    state.state = "escalated"
    _save_state(state)

    summary = "\n\n".join(state.history)
    escalation_body = (
        f"The scheduling negotiation for thread {thread_id} could not be resolved "
        f"after {MAX_ROUNDS} rounds.\n\nFull history:\n{summary}\n\n"
        f"Participants: {', '.join(participants)}\n"
        f"Please intervene manually."
    )
    send_email([config.ASSISTANT_EMAIL], f"[PatrAI Escalation] Thread {thread_id}", escalation_body)
    logger.warning("Negotiation escalated for thread_id=%s", thread_id)
