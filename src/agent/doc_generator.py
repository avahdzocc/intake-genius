"""Engagement letter generation via Claude."""
import logging
from pathlib import Path
from datetime import datetime

import anthropic

from src.config import settings
from src.models.case import Case

logger = logging.getLogger(__name__)

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3)
_PROMPT_PATH = Path(__file__).parent / "prompts" / "engagement_letter.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text()


def _first_name(full_name: str | None) -> str:
    if not full_name:
        return "Valued Client"
    return full_name.split()[0]


def _format_datetime(iso: str | None) -> str:
    if not iso:
        return "To be confirmed"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%A, %B %-d, %Y at %-I:%M %p")
    except Exception:
        return iso


async def generate_engagement_letter(
    case: Case,
    attorney_name: str = "",
    required_docs: list[str] | None = None,
) -> str:
    """Generate a professional engagement letter using Claude.

    Falls back to a plain-text template if the API call fails.
    """
    docs_text = (
        ", ".join(required_docs) if required_docs else "None required at this stage"
    )
    prompt = _PROMPT_TEMPLATE.format(
        client_name=case.client_name or "Valued Client",
        first_name=_first_name(case.client_name),
        case_type=(case.case_type or "legal").replace("_", " ").title(),
        jurisdiction=case.jurisdiction or "your jurisdiction",
        attorney_name=attorney_name or "your assigned attorney",
        consult_datetime=_format_datetime(case.consult_datetime),
        intake_summary=case.raw_intake_text or "No summary provided.",
        required_docs=docs_text,
        firm_name=settings.firm_name,
        intake_email=settings.intake_email,
    )

    try:
        response = await _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("Engagement letter generation failed (%s), using fallback", exc)
        return _fallback_letter(case, attorney_name, docs_text)


def _fallback_letter(case: Case, attorney_name: str, docs_text: str) -> str:
    first = _first_name(case.client_name)
    consult = _format_datetime(case.consult_datetime)
    return (
        f"Dear {first},\n\n"
        f"Thank you for contacting {settings.firm_name}. We are pleased to confirm "
        f"that we will be representing you in your "
        f"{(case.case_type or 'legal').replace('_', ' ')} matter.\n\n"
        f"Your consultation with {attorney_name or 'your assigned attorney'} is "
        f"scheduled for {consult}.\n\n"
        f"Please bring or send the following documents before our meeting:\n"
        f"{docs_text}\n\n"
        f"Everything you share with us is protected by attorney-client privilege and "
        f"will remain strictly confidential.\n\n"
        f"If you have questions in the meantime, please reach us at {settings.intake_email}.\n\n"
        f"We look forward to working with you.\n\n"
        f"Sincerely,\n{settings.firm_name}"
    )
