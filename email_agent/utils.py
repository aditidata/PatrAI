"""
PatrAI — Shared email utilities.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config

logger = logging.getLogger(__name__)

AI_DISCLAIMER = "This message was sent by an experimental AI email assistant."


def append_disclaimer(body: str) -> str:
    """Return body with the mandatory AI disclaimer as the final non-empty line."""
    stripped = body.rstrip()
    return f"{stripped}\n\n{AI_DISCLAIMER}"


def send_email(to: list[str], subject: str, body: str) -> None:
    """Send an email from ASSISTANT_EMAIL via SMTP. Always appends AI disclaimer."""
    body_with_disclaimer = append_disclaimer(body)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.ASSISTANT_EMAIL
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(body_with_disclaimer, "plain"))

    try:
        with smtplib.SMTP_SSL(config.SMTP_SERVER, 465) as server:
            server.login(config.ASSISTANT_EMAIL, config.ASSISTANT_EMAIL_PASSWORD)
            server.sendmail(config.ASSISTANT_EMAIL, to, msg.as_string())
        logger.info("Email sent to %d recipient(s), subject=%r", len(to), subject)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        raise
