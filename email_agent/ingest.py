"""
PatrAI — Email ingestion module.

Handles IMAP polling, Gmail webhook parsing, deduplication, MIME extraction,
and Celery task dispatch.
"""
import base64
import email
import hashlib
import imaplib
import json
import logging
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

import config
from database import get_db
from models import EmailData, WebhookPayload

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_message_id(message_id: str) -> str:
    """Return the SHA-256 hex digest of the given message_id string."""
    return hashlib.sha256(message_id.encode()).hexdigest()


def _dedup(message_id: str) -> bool:
    """
    Check whether message_id has already been processed.

    Returns True if the hash already exists in dedup_hashes (already seen),
    False if it is new (and inserts the hash so future calls return True).
    """
    h = _hash_message_id(message_id)
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT 1 FROM dedup_hashes WHERE hash = ?", (h,)
        ).fetchone()
        if row:
            return True
        conn.execute(
            "INSERT INTO dedup_hashes (hash) VALUES (?)", (h,)
        )
        conn.commit()
        return False
    finally:
        conn.close()


def _parse_mime(raw: bytes) -> EmailData:
    """
    Parse raw MIME bytes and return an EmailData model.

    Extracts: message_id, thread_id, sender, recipients, subject,
    plain-text body, and timestamp.
    """
    msg = email.message_from_bytes(raw)

    # Message-ID — strip surrounding angle brackets
    raw_mid = msg.get("Message-ID", "")
    message_id = raw_mid.strip().strip("<>")

    # thread_id — prefer X-GM-THRID, then Thread-Topic, fallback to message_id
    thread_id: str = (
        msg.get("X-GM-THRID")
        or msg.get("Thread-Topic")
        or message_id
    )
    thread_id = thread_id.strip()

    # Sender
    _, sender = parseaddr(msg.get("From", ""))

    # Recipients — combine To and Cc
    to_header = msg.get("To", "")
    cc_header = msg.get("Cc", "")
    combined = ", ".join(filter(None, [to_header, cc_header]))
    recipients: list[str] = [
        addr
        for _, addr in email.utils.getaddresses([combined])
        if addr
    ]

    # Subject
    subject: str = msg.get("Subject", "")

    # Plain-text body — walk parts
    body_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode(charset, errors="replace"))
    else:
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body_parts.append(payload.decode(charset, errors="replace"))

    body = "\n".join(body_parts)

    # Timestamp — parse Date header
    date_str = msg.get("Date", "")
    try:
        timestamp: datetime = parsedate_to_datetime(date_str)
    except Exception:
        timestamp = datetime.utcnow()

    return EmailData(
        message_id=message_id,
        thread_id=thread_id,
        sender=sender,
        recipients=recipients,
        subject=subject,
        body=body,
        timestamp=timestamp,
    )


def _dispatch(email_data: EmailData) -> str:
    """
    Send a process_email Celery task and return the task ID.

    celery_app is imported lazily to avoid circular imports.
    """
    from celery_app import celery_app  # noqa: PLC0415 — intentional lazy import

    result = celery_app.send_task(
        "patrai.process_email",
        args=[email_data.model_dump(mode="json")],
    )
    return result.id


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def poll_inbox() -> None:
    """
    Connect to the configured IMAP server, fetch UNSEEN messages, and
    dispatch each new (non-duplicate) message as a Celery task.
    """
    imap: Optional[imaplib.IMAP4_SSL] = None
    seen = 0
    dispatched = 0

    try:
        imap = imaplib.IMAP4_SSL(config.IMAP_SERVER)
        imap.login(config.ASSISTANT_EMAIL, config.ASSISTANT_EMAIL_PASSWORD)
        imap.select("INBOX")

        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            logger.warning("IMAP SEARCH returned non-OK status: %s", status)
            return

        uids = data[0].split() if data[0] else []
        logger.info("poll_inbox: found %d UNSEEN message(s)", len(uids))

        for uid in uids:
            try:
                fetch_status, fetch_data = imap.fetch(uid, "(RFC822)")
                if fetch_status != "OK" or not fetch_data:
                    logger.warning("Failed to fetch UID %s", uid)
                    continue

                raw: bytes = fetch_data[0][1]  # type: ignore[index]
                seen += 1

                # Quick dedup check using Message-ID header before full parse
                msg_preview = email.message_from_bytes(raw)
                raw_mid = msg_preview.get("Message-ID", uid.decode())
                message_id = raw_mid.strip().strip("<>")

                if _dedup(message_id):
                    logger.debug("Duplicate message_id=%s — skipping", message_id)
                    continue

                email_data = _parse_mime(raw)
                task_id = _dispatch(email_data)
                dispatched += 1
                logger.info(
                    "Dispatched task %s for message_id=%s", task_id, message_id
                )

            except Exception:
                logger.exception("Error processing UID %s — continuing", uid)

    except Exception:
        logger.exception("poll_inbox: IMAP connection error")
    finally:
        if imap is not None:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass

    logger.info(
        "poll_inbox complete: seen=%d dispatched=%d", seen, dispatched
    )


def handle_webhook(payload: WebhookPayload) -> None:
    """
    Handle a Gmail push notification webhook.

    Decodes the base64-encoded data field, extracts the historyId, and
    triggers poll_inbox() as a fallback to fetch new messages.
    """
    try:
        encoded_data = payload.message.get("data", "")
        # Gmail pub/sub data is base64url-encoded JSON
        decoded = base64.urlsafe_b64decode(encoded_data + "==")
        notification = json.loads(decoded)
        history_id = notification.get("historyId", "unknown")
        logger.info("Webhook received: historyId=%s", history_id)
    except Exception:
        logger.exception("handle_webhook: failed to decode notification payload")

    # Fallback: poll inbox to pick up any new messages referenced by this push
    poll_inbox()


# ---------------------------------------------------------------------------
# Celery tasks (registered in celery_app.py via include=)
# ---------------------------------------------------------------------------

def process_email(email_data_dict: dict) -> None:
    """
    Main pipeline task: embed → classify → extract slots → check availability → book/negotiate.
    Registered as 'patrai.process_email' by celery_app.py.
    """
    from email_agent.thread_memory import embed_and_store, retrieve_context
    from email_agent.intent import classify
    from email_agent.slot_extractor import extract_slots
    from calendar.availability import get_free_slots
    from calendar.booking import book_meeting
    from calendar.negotiation import start_negotiation

    try:
        email_data = EmailData(**email_data_dict)
    except Exception as exc:
        logger.error("process_email: invalid EmailData payload: %s", exc)
        return

    try:
        embed_and_store(email_data.thread_id, email_data.body)
    except Exception:
        logger.exception("process_email: thread memory store failed")

    history = retrieve_context(email_data.thread_id, email_data.body)
    result = classify(email_data.body, email_data.subject, history)
    logger.info("process_email: intent=%s confidence=%.2f", result.intent, result.confidence)

    if result.intent in ("needs_human_review", "status_update", "other"):
        return

    participants = list(email_data.recipients) + [email_data.sender]
    slots_result = extract_slots(email_data.body)

    if isinstance(slots_result, str):
        logger.info("process_email: slot extraction status=%s", slots_result)
        return

    free_slots = get_free_slots(participants, slots_result)
    if not free_slots:
        start_negotiation(email_data.thread_id, participants)
        return

    booking = book_meeting(free_slots[0], participants, cot=result.chain_of_thought)
    if booking:
        logger.info("process_email: booking complete event_id=%s", booking.event_id)
