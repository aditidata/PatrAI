"""
PatrAI — FastAPI application entry point.

Exposes all REST endpoints and initialises the database on startup.
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, get_db
from models import (
    EmailData,
    WebhookPayload,
    BookingRecord,
    UserPreferences,
    NegotiationState,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("PatrAI started — database initialised")
    yield


app = FastAPI(title="PatrAI", version="1.0.0", lifespan=lifespan)

# Serve React frontend static files if built
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str = ""):
        # Don't intercept API routes
        if full_path.startswith(("health", "webhook", "process", "bookings", "preferences", "negotiation")):
            raise HTTPException(status_code=404)
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /webhook/gmail
# ---------------------------------------------------------------------------

@app.post("/webhook/gmail")
def webhook_gmail(payload: WebhookPayload):
    from email_agent.ingest import handle_webhook
    handle_webhook(payload)
    return {"status": "accepted"}


# ---------------------------------------------------------------------------
# POST /process  (manual trigger for testing)
# ---------------------------------------------------------------------------

@app.post("/process")
def process(email_data: EmailData):
    from celery_app import celery_app
    result = celery_app.send_task(
        "patrai.process_email",
        args=[email_data.model_dump(mode="json")],
    )
    return {"task_id": result.id, "status": "queued"}


# ---------------------------------------------------------------------------
# GET /bookings
# ---------------------------------------------------------------------------

@app.get("/bookings")
def list_bookings():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r["id"],
            "event_id": r["event_id"],
            "thread_id": r["thread_id"],
            "participants": json.loads(r["participants"]),
            "slot_start": r["slot_start"],
            "slot_end": r["slot_end"],
            "fingerprint": r["fingerprint"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /preferences
# ---------------------------------------------------------------------------

@app.get("/preferences", response_model=UserPreferences)
def get_preferences():
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
    finally:
        conn.close()
    if not row:
        return UserPreferences()
    return UserPreferences(
        max_daily_hours=row["max_daily_hours"],
        vip_emails=json.loads(row["vip_emails"]),
        focus_blocks=json.loads(row["focus_blocks"]),
    )


# ---------------------------------------------------------------------------
# PUT /preferences
# ---------------------------------------------------------------------------

@app.put("/preferences", response_model=UserPreferences)
def update_preferences(prefs: UserPreferences):
    conn = get_db()
    try:
        conn.execute(
            """UPDATE preferences SET
                max_daily_hours = ?,
                vip_emails = ?,
                focus_blocks = ?,
                updated_at = datetime('now')
               WHERE id = 1""",
            (
                prefs.max_daily_hours,
                json.dumps([str(e) for e in prefs.vip_emails]),
                json.dumps([b.model_dump(mode="json") for b in prefs.focus_blocks]),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return prefs


# ---------------------------------------------------------------------------
# GET /negotiation/{thread_id}
# ---------------------------------------------------------------------------

@app.get("/negotiation/{thread_id}", response_model=NegotiationState)
def get_negotiation(thread_id: str):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM negotiations WHERE thread_id = ?", (thread_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"No negotiation found for thread_id={thread_id}")
    return NegotiationState(
        thread_id=row["thread_id"],
        state=row["state"],
        round_count=row["round_count"],
        history=json.loads(row["history"]),
    )
