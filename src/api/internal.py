from fastapi import APIRouter, HTTPException

from src.config import settings
from src.db.queries import get_stale_cases, load_case
from src.db.database import get_db

router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.get("/health")
async def health():
    """Health check — also exposes firm_name so the intake form can display it."""
    try:
        async with get_db() as db:
            await db.execute("SELECT 1")
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "firm_name": settings.firm_name,
    }


@router.get("/cases/stale")
async def stale_cases(hours: int = 48):
    cases = await get_stale_cases(hours)
    return [c.model_dump() for c in cases]


@router.get("/cases")
async def list_cases(status: str | None = None, limit: int = 50):
    """List cases, optionally filtered by status. Used by the admin dashboard."""
    async with get_db() as db:
        if status:
            async with db.execute(
                "SELECT * FROM cases WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM cases ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()

    import json
    result = []
    for row in rows:
        d = dict(row)
        d["key_entities"] = json.loads(d.pop("key_entities_json", None) or "{}")
        d.pop("calendar_event_id", None)
        result.append(d)
    return result


@router.get("/audit/{case_id}")
async def audit_trail(case_id: str):
    """Return the full audit trail for a case — every agent decision logged."""
    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM audit_log WHERE case_id = ? ORDER BY timestamp ASC",
            (case_id,),
        ) as cur:
            rows = await cur.fetchall()

    return {
        "case_id": case_id,
        "case_status": case.status.value,
        "client_name": case.client_name,
        "entries": [dict(r) for r in rows],
    }


@router.get("/cases/{case_id}/missing-docs")
async def missing_docs(case_id: str):
    """Return outstanding document requests for a case."""
    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_db() as db:
        async with db.execute(
            """
            SELECT document_type, requested_at, received_at, follow_up_count
            FROM missing_documents WHERE case_id = ?
            ORDER BY requested_at ASC
            """,
            (case_id,),
        ) as cur:
            rows = await cur.fetchall()

    return {
        "case_id": case_id,
        "documents": [dict(r) for r in rows],
        "outstanding": sum(1 for r in rows if not dict(r)["received_at"]),
    }
