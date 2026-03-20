"""
PatrAI — Celery application configuration.
"""
from celery import Celery

import config

celery_app = Celery(
    "patrai",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "send-briefings-every-minute": {
            "task": "patrai.send_briefings",
            "schedule": 60.0,
        },
        "poll-inbox-every-60s": {
            "task": "patrai.poll_inbox",
            "schedule": 60.0,
        },
    },
)


@celery_app.task(name="patrai.process_email", max_retries=3, default_retry_delay=60)
def process_email_task(email_data_dict: dict) -> None:
    """Celery task wrapper — delegates to ingest.process_email."""
    from email_agent.ingest import process_email
    process_email(email_data_dict)


@celery_app.task(name="patrai.poll_inbox", max_retries=3, default_retry_delay=60)
def poll_inbox_task() -> None:
    """Celery beat task — polls IMAP inbox."""
    from email_agent.ingest import poll_inbox
    poll_inbox()


@celery_app.task(name="patrai.send_briefings", max_retries=3, default_retry_delay=60)
def send_briefings_task() -> None:
    """Celery beat task — sends pre-meeting briefings."""
    from scheduler.briefing import send_briefings
    send_briefings()
