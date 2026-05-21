from contextlib import asynccontextmanager

import aiosqlite

from src.config import settings

_DB_PATH = settings.database_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'NEW',
    client_name TEXT,
    client_email TEXT,
    client_phone TEXT,
    case_type TEXT,
    urgency TEXT,
    jurisdiction TEXT,
    complexity TEXT,
    assigned_attorney_id TEXT,
    consult_datetime TEXT,
    calendar_event_id TEXT,
    intake_source TEXT,
    raw_intake_text TEXT,
    key_entities_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    last_client_contact_at TEXT,
    follow_up_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS case_parties (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    party_name TEXT NOT NULL,
    party_role TEXT NOT NULL,
    normalized_name TEXT
);

CREATE TABLE IF NOT EXISTS attorneys (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    practice_areas TEXT,
    bar_admissions TEXT,
    max_active_cases INTEGER DEFAULT 25,
    current_active_cases INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS missing_documents (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    document_type TEXT,
    requested_at TEXT,
    received_at TEXT,
    follow_up_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS engagement_letters (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    generated_at TEXT DEFAULT (datetime('now')),
    letter_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    timestamp TEXT DEFAULT (datetime('now')),
    agent_observation TEXT,
    agent_reasoning TEXT,
    action_taken TEXT,
    action_result TEXT
);
"""

# Incremental column additions — each silently ignored if already present
_MIGRATIONS = [
    "ALTER TABLE cases ADD COLUMN key_entities_json TEXT DEFAULT '{}'",
    "ALTER TABLE cases ADD COLUMN calendar_event_id TEXT",
]


@asynccontextmanager
async def get_db():
    """Async context manager that yields a configured aiosqlite connection."""
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.executescript(SCHEMA)
        for migration in _MIGRATIONS:
            try:
                await db.execute(migration)
            except Exception:
                pass  # column already exists
        await db.commit()

        # Auto-seed attorneys on first run (empty table)
        async with db.execute("SELECT COUNT(*) FROM attorneys") as cur:
            row = await cur.fetchone()
            if row and row[0] == 0:
                from src.db.seed import seed_attorneys

                await seed_attorneys(db)
