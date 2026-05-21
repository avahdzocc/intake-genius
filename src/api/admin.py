"""Admin dashboard API — serves the dashboard HTML and its data endpoints."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from src.config import settings
from src.db.database import get_db
from src.db.queries import load_case, load_engagement_letter

router = APIRouter(prefix="/admin", tags=["admin"])

_STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def admin_dashboard():
    html = _STATIC_DIR / "admin.html"
    if not html.exists():
        raise HTTPException(status_code=404, detail="Admin UI not found")
    return FileResponse(str(html))


@router.get("/api/cases")
async def admin_cases(status: str | None = None, limit: int = 100):
    """List cases for the admin dashboard with audit summary counts."""
    async with get_db() as db:
        if status:
            async with db.execute(
                "SELECT * FROM cases WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM cases ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["key_entities"] = json.loads(d.pop("key_entities_json", None) or "{}")
        result.append(d)
    return result


@router.get("/api/cases/{case_id}")
async def admin_case_detail(case_id: str):
    """Full case detail with audit log, missing docs, and engagement letter status."""
    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM audit_log WHERE case_id=? ORDER BY timestamp ASC",
            (case_id,),
        ) as cur:
            audit_rows = await cur.fetchall()

        async with db.execute(
            "SELECT * FROM missing_documents WHERE case_id=? ORDER BY requested_at ASC",
            (case_id,),
        ) as cur:
            doc_rows = await cur.fetchall()

    letter = await load_engagement_letter(case_id)

    return {
        "case": case.model_dump(),
        "audit_log": [dict(r) for r in audit_rows],
        "missing_documents": [dict(r) for r in doc_rows],
        "engagement_letter": letter,
    }


@router.get("/api/cases/{case_id}/activity")
async def admin_case_activity(case_id: str):
    """Audit log entries enriched with parsed action types for the activity feed."""
    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM audit_log WHERE case_id=? ORDER BY timestamp ASC",
            (case_id,),
        ) as cur:
            rows = await cur.fetchall()

    entries = []
    for row in rows:
        d = dict(row)
        # Parse action type from the reasoning/action fields
        reasoning = (d.get("agent_reasoning") or "").lower()
        action = (d.get("action_taken") or "").lower()
        observation = (d.get("agent_observation") or "").lower()

        if "sms" in reasoning or "sms" in action:
            d["activity_type"] = "sms"
        elif "schedul" in reasoning or "calendar" in reasoning or "consult" in observation:
            d["activity_type"] = "calendar"
        elif "conflict" in reasoning or "conflict" in observation:
            d["activity_type"] = "conflict"
        elif "classif" in reasoning or "classif" in action:
            d["activity_type"] = "classification"
        elif "task" in reasoning or "asana" in reasoning:
            d["activity_type"] = "task"
        elif "document" in reasoning or "doc" in observation:
            d["activity_type"] = "document"
        else:
            d["activity_type"] = "agent"

        entries.append(d)

    return {
        "case_id": case_id,
        "client_name": case.client_name,
        "entries": entries,
    }


@router.get("/api/stats")
async def admin_stats():
    """Aggregate stats for the dashboard header."""
    async with get_db() as db:
        async with db.execute("SELECT status, COUNT(*) as cnt FROM cases GROUP BY status") as cur:
            rows = await cur.fetchall()
        async with db.execute("SELECT COUNT(*) as total FROM cases") as cur:
            total_row = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE timestamp >= datetime('now', '-7 days')"
        ) as cur:
            recent_audit = await cur.fetchone()

    by_status = {r["status"]: r["cnt"] for r in rows}
    return {
        "total_cases": total_row["total"] if total_row else 0,
        "by_status": by_status,
        "audit_entries_7d": recent_audit["cnt"] if recent_audit else 0,
        "firm_name": settings.firm_name,
    }
