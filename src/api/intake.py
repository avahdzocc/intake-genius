import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from src.db.queries import create_case, load_case, load_engagement_letter, save_engagement_letter
from src.models.case import Case, IntakeRequest, CaseStatus
from src.agent.orchestrator import run_intake_agent, run_follow_up

router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.post("/new", response_model=dict)
async def new_intake(request: IntakeRequest):
    case = Case(
        client_name=request.client_name,
        client_email=request.client_email,
        client_phone=request.client_phone,
        raw_intake_text=request.description,
        intake_source=request.intake_source,
    )
    await create_case(case)
    asyncio.create_task(run_intake_agent(case.id))
    return {"case_id": case.id, "status": case.status.value}


@router.get("/{case_id}", response_model=dict)
async def get_case(case_id: str):
    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case.model_dump()


class ClientReplyPayload(BaseModel):
    body: str
    from_phone: str | None = None


@router.post("/{case_id}/client-reply", response_model=dict)
async def client_reply(case_id: str, payload: ClientReplyPayload):
    """Process a client's SMS reply for a specific case.

    Called by n8n after it resolves the case_id from the inbound phone number.
    """
    from src.agent.reply_parser import parse_reply
    from src.agent.orchestrator import IntakeAgent

    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    parsed = await parse_reply(payload.body, case)
    agent = IntakeAgent(case)

    if parsed.is_confirmation() and case.status == CaseStatus.SCHEDULING:
        case = await agent.handle_client_confirmed()
        return {"case_id": case_id, "action": "confirmed", "new_status": case.status.value}

    if parsed.is_cancellation():
        return {"case_id": case_id, "action": "cancel_flagged", "note": "Flagged for human review"}

    return {
        "case_id": case_id,
        "action": "parsed",
        "intent": parsed.intent,
        "extracted_info": parsed.extracted_info,
        "suggested_response": parsed.suggested_response,
    }


@router.post("/{case_id}/follow-up", response_model=dict)
async def trigger_follow_up(case_id: str):
    """Trigger an automated follow-up for a stale case. Called by n8n cron."""
    case = await run_follow_up(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case_id, "status": case.status.value, "follow_up_count": case.follow_up_count}


@router.get("/{case_id}/engagement-letter", response_class=PlainTextResponse)
async def get_engagement_letter(case_id: str, regenerate: bool = False):
    """Return the engagement letter for a case; generate one if it doesn't exist."""
    from src.agent.doc_generator import generate_engagement_letter
    from src.db.queries import get_attorney_by_id, get_missing_docs
    from src.agent.doc_list import friendly_doc_name

    case = await load_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not regenerate:
        existing = await load_engagement_letter(case_id)
        if existing:
            return existing

    attorney_name = ""
    if case.assigned_attorney_id:
        attorney = await get_attorney_by_id(case.assigned_attorney_id)
        if attorney:
            attorney_name = attorney.name or ""

    missing = await get_missing_docs(case_id)
    required_docs = [friendly_doc_name(d) for d in missing] if missing else []

    letter = await generate_engagement_letter(case, attorney_name=attorney_name, required_docs=required_docs)
    await save_engagement_letter(case_id, letter)
    return letter
