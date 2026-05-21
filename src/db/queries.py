import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.db.database import get_db
from src.models.case import Case, CaseStatus
from src.models.attorney import Attorney
from src.models.audit import AuditEntry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_case(row: dict) -> Case:
    data = dict(row)
    raw_ke = data.pop("key_entities_json", None) or "{}"
    data["key_entities"] = json.loads(raw_ke)
    data.pop("calendar_event_id", None)  # not on the model yet; ignore
    return Case(**data)


async def create_case(case: Case) -> Case:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO cases (id, status, client_name, client_email, client_phone,
                intake_source, raw_intake_text, key_entities_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.id,
                case.status.value,
                case.client_name,
                case.client_email,
                case.client_phone,
                case.intake_source,
                case.raw_intake_text,
                json.dumps(case.key_entities),
                _now(),
                _now(),
            ),
        )
        await db.commit()
    return case


async def load_case(case_id: str) -> Case | None:
    async with get_db() as db:
        async with db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_case(row)


async def find_case_by_phone(phone: str) -> Case | None:
    """Find the most-recently-updated active case for a given client phone number."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM cases
            WHERE client_phone = ?
              AND status NOT IN ('INTAKE_COMPLETE', 'REJECTED', 'BLOCKED')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (phone,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_case(row)


async def update_case(case: Case) -> None:
    async with get_db() as db:
        await db.execute(
            """
            UPDATE cases SET status=?, case_type=?, urgency=?, jurisdiction=?,
                complexity=?, assigned_attorney_id=?, consult_datetime=?,
                key_entities_json=?, last_client_contact_at=?, follow_up_count=?,
                updated_at=?
            WHERE id=?
            """,
            (
                case.status.value,
                case.case_type,
                case.urgency,
                case.jurisdiction,
                case.complexity,
                case.assigned_attorney_id,
                case.consult_datetime,
                json.dumps(case.key_entities),
                case.last_client_contact_at,
                case.follow_up_count,
                _now(),
                case.id,
            ),
        )
        await db.commit()


async def update_calendar_event_id(case_id: str, event_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE cases SET calendar_event_id=? WHERE id=?",
            (event_id, case_id),
        )
        await db.commit()


async def get_stale_cases(hours: int = 48) -> list[Case]:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM cases
            WHERE status IN ('AWAITING_DOCS', 'SCHEDULING')
            AND (
                last_client_contact_at IS NULL
                OR (julianday('now') - julianday(last_client_contact_at)) * 24 >= ?
            )
            """,
            (hours,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_case(r) for r in rows]


async def get_attorneys() -> list[Attorney]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM attorneys") as cursor:
            rows = await cursor.fetchall()
    return [Attorney(**dict(r)) for r in rows]


async def get_attorney_by_id(attorney_id: str) -> Attorney | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM attorneys WHERE id = ?", (attorney_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return Attorney(**dict(row))


async def log_audit(entry: AuditEntry) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO audit_log (id, case_id, timestamp, agent_observation,
                agent_reasoning, action_taken, action_result)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                entry.case_id,
                _now(),
                entry.agent_observation,
                entry.agent_reasoning,
                entry.action_taken,
                entry.action_result,
            ),
        )
        await db.commit()


async def search_parties_exact(name: str) -> list[dict[str, Any]]:
    normalized = name.lower().strip()
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM case_parties WHERE normalized_name = ?", (normalized,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def search_parties_all() -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM case_parties") as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def save_case_parties(case_id: str, parties: list[dict[str, str]]) -> None:
    """Store extracted parties for future conflict checks."""
    async with get_db() as db:
        for party in parties:
            await db.execute(
                """
                INSERT OR IGNORE INTO case_parties (id, case_id, party_name, party_role, normalized_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    case_id,
                    party["name"],
                    party["role"],
                    party["name"].lower().strip(),
                ),
            )
        await db.commit()


async def get_missing_docs(case_id: str) -> list[str]:
    async with get_db() as db:
        async with db.execute(
            "SELECT document_type FROM missing_documents WHERE case_id=? AND received_at IS NULL",
            (case_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [r["document_type"] for r in rows]


async def add_missing_docs(case_id: str, doc_types: list[str]) -> None:
    async with get_db() as db:
        for doc_type in doc_types:
            await db.execute(
                """
                INSERT OR IGNORE INTO missing_documents (id, case_id, document_type, requested_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), case_id, doc_type, _now()),
            )
        await db.commit()


async def mark_doc_received(case_id: str, doc_type: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE missing_documents SET received_at=? WHERE case_id=? AND document_type=?",
            (_now(), case_id, doc_type),
        )
        await db.commit()


async def save_engagement_letter(case_id: str, letter_text: str) -> str:
    letter_id = str(uuid.uuid4())
    async with get_db() as db:
        await db.execute(
            "INSERT INTO engagement_letters (id, case_id, generated_at, letter_text) VALUES (?, ?, ?, ?)",
            (letter_id, case_id, _now(), letter_text),
        )
        await db.commit()
    return letter_id


async def load_engagement_letter(case_id: str) -> str | None:
    """Return the most recently generated engagement letter for a case."""
    async with get_db() as db:
        async with db.execute(
            "SELECT letter_text FROM engagement_letters WHERE case_id=? ORDER BY generated_at DESC LIMIT 1",
            (case_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return row["letter_text"] if row else None
