"""
PatrAI — Pre-meeting briefing scheduler.

Celery beat task that scans for meetings starting in 30-35 minutes
and sends a bullet-point summary to all attendees.
"""
import json
import logging
from datetime import datetime, timedelta

import pytz
import requests
import openai

import config
from database import get_db
from email_agent.utils import send_email
from email_agent.thread_memory import retrieve_context

logger = logging.getLogger(__name__)


def _summarize_thread(thread_text: str) -> str:
    """Ask the LLM to summarize the thread into 3-5 bullet points."""
    prompt = (
        "Summarize the following email thread into 3 to 5 concise bullet points "
        "that will help meeting attendees prepare. Use plain text bullets starting with '•'.\n\n"
        f"Thread:\n{thread_text}"
    )
    # Try Ollama first
    try:
        resp = requests.post(
            f"{config.OLLAMA_BASE_URL}/api/generate",
            json={"model": "llama3.1:8b", "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["response"]
    except Exception as e:
        logger.warning("Ollama failed in briefing: %s — trying OpenAI", e)

    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content
    except Exception as e2:
        logger.error("Both LLMs failed in briefing: %s", e2)
        return "• (Summary unavailable — please review the original thread.)"


def _send_briefing_email(attendees: list[str], summary: str, meeting_start: str) -> None:
    """Send the briefing email to all attendees."""
    subject = f"Pre-Meeting Briefing — {meeting_start}"
    body = f"Your meeting starts in approximately 30 minutes.\n\nThread summary:\n{summary}\n"
    send_email(attendees, subject, body)


def send_briefings() -> None:
    """
    Scan the bookings table for meetings starting in 30-35 minutes and
    send a briefing email to all attendees.

    Registered as a Celery beat task in celery_app.py.
    """
    now = datetime.now(pytz.UTC)
    window_start = now + timedelta(minutes=30)
    window_end = now + timedelta(minutes=35)

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE slot_start >= ? AND slot_start <= ?",
            (window_start.isoformat(), window_end.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return

    logger.info("send_briefings: found %d meeting(s) in the 30-35 min window", len(rows))

    for row in rows:
        thread_id = row["thread_id"]
        participants = json.loads(row["participants"])
        slot_start = row["slot_start"]

        try:
            # Retrieve thread context from ChromaDB
            thread_docs = retrieve_context(thread_id, query="meeting context", top_k=5)
            thread_text = "\n\n".join(thread_docs) if thread_docs else "(No thread context available)"

            summary = _summarize_thread(thread_text)
            _send_briefing_email(participants, summary, slot_start)
            logger.info("Briefing sent for thread_id=%s to %d attendee(s)", thread_id, len(participants))
        except Exception:
            logger.exception("Failed to send briefing for thread_id=%s", thread_id)
