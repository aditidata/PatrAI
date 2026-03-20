"""
PatrAI — Database layer.

Provides get_db() for acquiring a SQLite connection and init_db() for
idempotent schema creation + default-row seeding.
"""
import sqlite3

import config

_DDL = """
CREATE TABLE IF NOT EXISTS dedup_hashes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash        TEXT UNIQUE NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL,
    thread_id       TEXT NOT NULL,
    participants    TEXT NOT NULL,
    slot_start      TEXT NOT NULL,
    slot_end        TEXT NOT NULL,
    fingerprint     TEXT UNIQUE NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS negotiations (
    thread_id   TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    round_count INTEGER NOT NULL DEFAULT 0,
    history     TEXT NOT NULL DEFAULT '[]',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS preferences (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    max_daily_hours REAL NOT NULL DEFAULT 4.0,
    vip_emails      TEXT NOT NULL DEFAULT '[]',
    focus_blocks    TEXT NOT NULL DEFAULT '[]',
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service     TEXT UNIQUE NOT NULL,
    ciphertext  BLOB NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection to the configured DB_PATH with Row factory."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables (idempotent) and seed the singleton preferences row."""
    conn = get_db()
    try:
        conn.executescript(_DDL)
        conn.execute("INSERT OR IGNORE INTO preferences (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()
