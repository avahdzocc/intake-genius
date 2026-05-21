"""Parse client SMS replies in context of the current case state."""
import json
import logging
from pathlib import Path
from typing import Optional

import anthropic

from src.config import settings
from src.models.case import Case

logger = logging.getLogger(__name__)
_PROMPT_PATH = Path(__file__).parent / "prompts" / "reply_parser.txt"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

# Fast-path keywords that don't need an LLM call
_CONFIRM_WORDS = {"yes", "yep", "yeah", "confirmed", "confirm", "ok", "okay", "sure", "y"}
_CANCEL_WORDS = {"no", "cancel", "stop", "nope", "nevermind", "n"}


class ParsedReply:
    def __init__(self, intent: str, extracted_info: dict, suggested_response: Optional[str] = None):
        self.intent = intent          # CONFIRM | CANCEL | PROVIDE_INFO | ASK_QUESTION | UNKNOWN
        self.extracted_info = extracted_info
        self.suggested_response = suggested_response

    def is_confirmation(self) -> bool:
        return self.intent == "CONFIRM"

    def is_cancellation(self) -> bool:
        return self.intent == "CANCEL"


async def parse_reply(body: str, case: Case) -> ParsedReply:
    """Classify a client's SMS reply. Uses fast-path for obvious yes/no, Claude for everything else."""
    normalized = body.strip().lower().rstrip("!.,")

    if normalized in _CONFIRM_WORDS:
        return ParsedReply("CONFIRM", {})

    if normalized in _CANCEL_WORDS and normalized != "stop":
        return ParsedReply("CANCEL", {})

    if normalized == "stop":
        return ParsedReply("CANCEL", {"opt_out": True})

    # Use Claude for nuanced replies
    return await _llm_parse(body, case)


async def _llm_parse(body: str, case: Case) -> ParsedReply:
    system_prompt = _PROMPT_PATH.read_text()
    context = (
        f"Case status: {case.status.value}\n"
        f"Case type: {case.case_type or 'unknown'}\n"
        f"Client name: {case.client_name or 'unknown'}\n"
        f"Consultation scheduled: {case.consult_datetime or 'none'}\n"
        f"Client SMS reply: {body}"
    )

    try:
        response = await _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": context}],
        )
        raw = response.content[0].text if response.content else "{}"
        # Strip markdown fences if present
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(raw)
        return ParsedReply(
            intent=data.get("intent", "UNKNOWN"),
            extracted_info=data.get("extracted_info", {}),
            suggested_response=data.get("suggested_response"),
        )
    except Exception as exc:
        logger.warning("Reply parser LLM call failed: %s", exc)
        return ParsedReply("UNKNOWN", {})
