import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from src.integrations.twilio_client import parse_inbound
from src.db.queries import find_case_by_phone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio/inbound", response_class=PlainTextResponse)
async def twilio_inbound(request: Request):
    """Receive inbound SMS from Twilio, route to the matching case's reply handler."""
    form = dict(await request.form())
    parsed = parse_inbound(form)

    from_number = parsed["from"]
    body = parsed["body"]
    logger.info("Inbound SMS from=%s body=%r", from_number, body)

    case = await find_case_by_phone(from_number)
    if not case:
        logger.warning("No active case found for phone %s", from_number)
        return PlainTextResponse("<?xml version='1.0'?><Response></Response>", media_type="text/xml")

    # Hand off to the case reply handler asynchronously
    asyncio.create_task(_process_reply(case.id, body))

    # Return empty TwiML — Twilio requires a response
    return PlainTextResponse("<?xml version='1.0'?><Response></Response>", media_type="text/xml")


async def _process_reply(case_id: str, body: str) -> None:
    from src.agent.reply_parser import parse_reply
    from src.agent.orchestrator import IntakeAgent
    from src.db.queries import load_case
    from src.models.case import CaseStatus

    case = await load_case(case_id)
    if not case:
        return

    parsed = await parse_reply(body, case)
    agent = IntakeAgent(case)

    if parsed.is_confirmation() and case.status == CaseStatus.SCHEDULING:
        await agent.handle_client_confirmed()
        logger.info("Case %s confirmed by client", case_id)
    elif parsed.is_cancellation():
        logger.info("Case %s: client indicated cancellation — flagged for human review", case_id)
    else:
        logger.info("Case %s: reply intent=%s info=%s", case_id, parsed.intent, parsed.extracted_info)


@router.post("/twilio/status")
async def twilio_status(request: Request):
    """Twilio delivery status callback — log and acknowledge."""
    form = dict(await request.form())
    logger.info("Twilio status: sid=%s status=%s", form.get("MessageSid"), form.get("MessageStatus"))
    return {"ok": True}


@router.post("/n8n/conflict-resolved")
async def conflict_resolved(payload: dict):
    """n8n posts here when a managing partner clears or rejects a conflict."""
    from src.agent.orchestrator import run_conflict_resolution

    case_id = payload.get("case_id")
    cleared = bool(payload.get("cleared", False))

    if not case_id:
        return {"error": "case_id required"}

    asyncio.create_task(run_conflict_resolution(case_id, cleared))
    return {"case_id": case_id, "cleared": cleared, "action": "queued"}
