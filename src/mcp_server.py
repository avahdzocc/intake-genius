"""Intake Genius MCP Server.

Exposes the legal intake pipeline as MCP tools so attorneys can manage
the system conversationally through Claude Desktop or any MCP client.

Run via stdio (Claude Desktop):
    python -m src.mcp_server

Run via SSE (network / browser):
    fastmcp run src/mcp_server.py --transport sse --port 8001

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "intake-genius": {
          "command": "/path/to/intake-genius/.venv/bin/python",
          "args": ["-m", "src.mcp_server"],
          "cwd": "/path/to/intake-genius"
        }
      }
    }
"""
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is on sys.path when run as `python -m src.mcp_server`
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Load .env before importing settings
from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=True)

from fastmcp import FastMCP


@asynccontextmanager
async def _lifespan(server):
    from src.db.database import init_db
    await init_db()
    yield


from src.db.database import get_db
from src.db.queries import (
    load_case,
    create_case,
    update_case,
    get_stale_cases,
    get_missing_docs,
    mark_doc_received,
    load_engagement_letter,
    save_engagement_letter,
    get_attorney_by_id,
    log_audit,
)
from src.models.case import Case, CaseStatus, IntakeRequest
from src.models.audit import AuditEntry
from src.agent.doc_generator import generate_engagement_letter
from src.agent.doc_list import friendly_doc_name
from src.agent.orchestrator import run_follow_up, run_conflict_resolution, run_intake_agent
from src.config import settings

mcp = FastMCP(
    name="Intake Genius",
    lifespan=_lifespan,
    instructions=(
        "You are an AI assistant with direct access to the Intake Genius legal intake pipeline. "
        "You can look up cases, submit new intakes, trigger follow-ups, resolve conflicts, "
        "manage document checklists, and generate engagement letters. "
        "Always confirm destructive or client-facing actions before executing. "
        f"This system serves {settings.firm_name}."
    ),
)


# ── Case lookup tools ─────────────────────────────────────────────────────────

@mcp.tool()
async def get_case(case_id: str) -> dict:
    """Retrieve full details for a single case by its ID.

    Returns the case fields, assigned attorney name, and outstanding document count.
    Use this to answer questions like 'What's the status of the Johnson intake?'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    attorney_name = None
    if case.assigned_attorney_id:
        attorney = await get_attorney_by_id(case.assigned_attorney_id)
        if attorney:
            attorney_name = attorney.name

    missing = await get_missing_docs(case_id)

    return {
        **case.model_dump(),
        "attorney_name": attorney_name,
        "outstanding_documents": len(missing),
        "missing_document_types": missing,
    }


@mcp.tool()
async def list_cases(
    status: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """List cases, optionally filtered by status.

    status options: NEW, CLASSIFYING, CONFLICT_CHECK, ROUTING, SCHEDULING,
                    AWAITING_DOCS, INTAKE_COMPLETE, CONFLICT_FLAGGED, REJECTED, BLOCKED

    Use this to get an overview: 'Show me all cases awaiting documents' or
    'How many new intakes do we have today?'
    """
    async with get_db() as db:
        if status:
            async with db.execute(
                "SELECT * FROM cases WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                (status.upper(), limit),
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
        d.pop("calendar_event_id", None)
        result.append(d)
    return result


@mcp.tool()
async def search_cases(query: str, limit: int = 20) -> list[dict]:
    """Search cases by client name, phone number, or case type.

    Use this to find a specific client's intake: 'Find the intake for Maria Santos'
    """
    q = f"%{query.lower()}%"
    async with get_db() as db:
        async with db.execute(
            """
            SELECT * FROM cases
            WHERE lower(client_name) LIKE ?
               OR lower(client_phone) LIKE ?
               OR lower(case_type) LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (q, q, q, limit),
        ) as cur:
            rows = await cur.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["key_entities"] = json.loads(d.pop("key_entities_json", None) or "{}")
        d.pop("calendar_event_id", None)
        result.append(d)
    return result


@mcp.tool()
async def get_pipeline_stats() -> dict:
    """Get aggregate statistics for the intake pipeline.

    Returns total case count, breakdown by status, stale cases count, and
    recent activity. Use this for a quick dashboard view.
    """
    async with get_db() as db:
        async with db.execute(
            "SELECT status, COUNT(*) as cnt FROM cases GROUP BY status"
        ) as cur:
            status_rows = await cur.fetchall()

        async with db.execute("SELECT COUNT(*) as total FROM cases") as cur:
            total_row = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM cases WHERE created_at >= datetime('now', '-7 days')"
        ) as cur:
            new_this_week = await cur.fetchone()

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM audit_log WHERE timestamp >= datetime('now', '-24 hours')"
        ) as cur:
            recent_actions = await cur.fetchone()

    stale = await get_stale_cases(hours=48)

    return {
        "firm": settings.firm_name,
        "total_cases": total_row["total"] if total_row else 0,
        "new_this_week": new_this_week["cnt"] if new_this_week else 0,
        "stale_cases": len(stale),
        "agent_actions_24h": recent_actions["cnt"] if recent_actions else 0,
        "by_status": {r["status"]: r["cnt"] for r in status_rows},
    }


# ── Audit trail ───────────────────────────────────────────────────────────────

@mcp.tool()
async def get_audit_trail(case_id: str) -> dict:
    """Return the complete agent audit trail for a case — every decision the AI made.

    Use this to explain what happened: 'Walk me through the Johnson intake decisions'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM audit_log WHERE case_id=? ORDER BY timestamp ASC",
            (case_id,),
        ) as cur:
            rows = await cur.fetchall()

    return {
        "case_id": case_id,
        "client_name": case.client_name,
        "current_status": case.status.value,
        "entries": [dict(r) for r in rows],
        "entry_count": len(rows),
    }


# ── Intake submission ──────────────────────────────────────────────────────────

@mcp.tool()
async def submit_intake(
    client_name: str,
    description: str,
    client_phone: str = "",
    client_email: str = "",
    intake_source: str = "mcp",
) -> dict:
    """Submit a new client intake and start the agentic pipeline.

    The agent will classify the case, check for conflicts, route to an attorney,
    and send the client an SMS (if phone provided). Returns the new case ID.

    Use this when an attorney or staff member describes a walk-in or phone inquiry.
    """
    case = Case(
        client_name=client_name,
        client_phone=client_phone or None,
        client_email=client_email or None,
        raw_intake_text=description,
        intake_source=intake_source,
    )
    await create_case(case)

    # Fire the agent loop in the background (non-blocking)
    asyncio.create_task(run_intake_agent(case.id))

    return {
        "case_id": case.id,
        "status": case.status.value,
        "message": f"Intake submitted. The agent is processing case {case.id[:8].upper()}.",
    }


# ── Action tools ───────────────────────────────────────────────────────────────

@mcp.tool()
async def trigger_follow_up(case_id: str) -> dict:
    """Manually trigger a follow-up SMS for a stale case.

    Use this when an attorney asks: 'Can you follow up with the Garcia family?'
    The agent generates a contextual message and sends it via Twilio.
    """
    case = await run_follow_up(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}
    return {
        "case_id": case_id,
        "status": case.status.value,
        "follow_up_count": case.follow_up_count,
        "message": "Follow-up triggered successfully.",
    }


@mcp.tool()
async def resolve_conflict(case_id: str, cleared: bool, reason: str = "") -> dict:
    """Clear or reject a conflict-flagged case after human review.

    cleared=True  → resume the pipeline (route to attorney, schedule consult)
    cleared=False → send client a polite declination SMS and close the case

    Use this when a managing partner has reviewed a potential conflict and made a decision.
    Always confirm the decision with the attorney before calling this tool.
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}
    if case.status != CaseStatus.CONFLICT_FLAGGED:
        return {"error": f"Case {case_id[:8].upper()} is in status {case.status.value!r}, not CONFLICT_FLAGGED."}

    updated = await run_conflict_resolution(case_id, cleared)

    return {
        "case_id": case_id,
        "cleared": cleared,
        "new_status": updated.status.value if updated else "unknown",
        "reason": reason,
        "message": (
            "Conflict cleared — pipeline resumed." if cleared
            else "Conflict rejected — client notified, case closed."
        ),
    }


@mcp.tool()
async def update_case_status(
    case_id: str,
    new_status: str,
    note: str = "",
) -> dict:
    """Manually override a case's status and log the reason in the audit trail.

    Valid statuses: NEW, CLASSIFYING, CONFLICT_CHECK, ROUTING, SCHEDULING,
                    AWAITING_DOCS, INTAKE_COMPLETE, CONFLICT_FLAGGED, REJECTED, BLOCKED

    Use sparingly — prefer the agent pipeline for normal transitions.
    This is for corrections: 'Mark the Chen case as complete, we finished intake manually.'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    try:
        case.status = CaseStatus[new_status.upper()]
    except KeyError:
        return {"error": f"Unknown status {new_status!r}. Valid values: {[s.value for s in CaseStatus]}"}

    await update_case(case)

    entry = AuditEntry(
        case_id=case_id,
        agent_observation="Manual status override via MCP",
        agent_reasoning=note or "No reason provided",
        action_taken=f"status={new_status.upper()}",
        action_result="manual_override",
    )
    await log_audit(entry)

    return {
        "case_id": case_id,
        "new_status": case.status.value,
        "message": f"Status updated to {case.status.value}.",
    }


# ── Document management ────────────────────────────────────────────────────────

@mcp.tool()
async def get_missing_documents(case_id: str) -> dict:
    """List the outstanding document requests for a case.

    Use this to check what's still needed: 'What documents are we still waiting on from Smith?'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    async with get_db() as db:
        async with db.execute(
            """
            SELECT document_type, requested_at, received_at, follow_up_count
            FROM missing_documents WHERE case_id=? ORDER BY requested_at ASC
            """,
            (case_id,),
        ) as cur:
            rows = await cur.fetchall()

    docs = [dict(r) for r in rows]
    outstanding = [d for d in docs if not d["received_at"]]

    return {
        "case_id": case_id,
        "client_name": case.client_name,
        "documents": [
            {
                **d,
                "friendly_name": friendly_doc_name(d["document_type"]),
                "status": "received" if d["received_at"] else "outstanding",
            }
            for d in docs
        ],
        "outstanding_count": len(outstanding),
        "total_count": len(docs),
    }


@mcp.tool()
async def mark_document_received(case_id: str, document_type: str) -> dict:
    """Mark a document as received for a case.

    document_type should match the type stored in the database (e.g. 'police_report',
    'medical_records', 'tax_returns'). You can get the exact types from get_missing_documents.

    Use this when staff receives a document: 'The Garcia family just dropped off their police report.'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    await mark_doc_received(case_id, document_type)

    # Check if all docs are now received — if so, advance to INTAKE_COMPLETE
    remaining = await get_missing_docs(case_id)
    if not remaining and case.status == CaseStatus.AWAITING_DOCS:
        case.status = CaseStatus.INTAKE_COMPLETE
        await update_case(case)
        entry = AuditEntry(
            case_id=case_id,
            agent_observation="All documents received",
            agent_reasoning="Last outstanding document marked received via MCP",
            action_taken="status=INTAKE_COMPLETE",
            action_result="auto_advanced",
        )
        await log_audit(entry)
        return {
            "case_id": case_id,
            "document_type": document_type,
            "friendly_name": friendly_doc_name(document_type),
            "remaining_outstanding": 0,
            "case_status": "INTAKE_COMPLETE",
            "message": "Document received. All documents collected — case marked INTAKE_COMPLETE!",
        }

    return {
        "case_id": case_id,
        "document_type": document_type,
        "friendly_name": friendly_doc_name(document_type),
        "remaining_outstanding": len(remaining),
        "case_status": case.status.value,
        "message": f"Document marked received. {len(remaining)} document(s) still outstanding.",
    }


# ── Engagement letter ──────────────────────────────────────────────────────────

@mcp.tool()
async def get_engagement_letter(case_id: str, regenerate: bool = False) -> dict:
    """Retrieve (or generate) the engagement letter for a case.

    Returns the letter text. Set regenerate=True to create a fresh version
    using Claude, even if one already exists.

    Use this when an attorney asks: 'Show me the engagement letter for the Martinez case'
    or 'Generate a new letter for the updated consultation time.'
    """
    case = await load_case(case_id)
    if case is None:
        return {"error": f"Case {case_id!r} not found."}

    if not regenerate:
        existing = await load_engagement_letter(case_id)
        if existing:
            return {
                "case_id": case_id,
                "client_name": case.client_name,
                "letter": existing,
                "generated": False,
            }

    attorney_name = ""
    if case.assigned_attorney_id:
        attorney = await get_attorney_by_id(case.assigned_attorney_id)
        if attorney:
            attorney_name = attorney.name or ""

    missing = await get_missing_docs(case_id)
    required_docs = [friendly_doc_name(d) for d in missing]

    letter = await generate_engagement_letter(
        case, attorney_name=attorney_name, required_docs=required_docs
    )
    await save_engagement_letter(case_id, letter)

    return {
        "case_id": case_id,
        "client_name": case.client_name,
        "letter": letter,
        "generated": True,
    }


# ── Stale case review ──────────────────────────────────────────────────────────

@mcp.tool()
async def list_stale_cases(hours: int = 48) -> list[dict]:
    """List cases that haven't had client contact in the given number of hours.

    Use this for a morning review: 'Which cases need follow-up today?'
    Default threshold is 48 hours.
    """
    cases = await get_stale_cases(hours)
    return [
        {
            **c.model_dump(),
            "hours_since_contact": round(c.days_since_last_contact() * 24, 1),
        }
        for c in cases
    ]


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
