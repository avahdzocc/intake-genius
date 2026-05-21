from pathlib import Path

import anthropic

from src.config import settings
from src.models.case import Case

_PROMPT_PATH = Path(__file__).parent / "prompts" / "follow_up.txt"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3)

MAX_FOLLOW_UPS = 3


async def should_follow_up(case: Case) -> bool:
    return case.follow_up_count < MAX_FOLLOW_UPS


async def generate_follow_up_message(case: Case, missing_docs: list[str]) -> str:
    system_prompt = _PROMPT_PATH.read_text()
    context = (
        f"Client first name: {(case.client_name or 'there').split()[0]}\n"
        f"Missing documents: {', '.join(missing_docs) if missing_docs else 'none specified'}\n"
        f"Consultation: {case.consult_datetime or 'not yet scheduled'}\n"
        f"Prior follow-ups sent: {case.follow_up_count}\n"
        f"Firm name: {settings.firm_name}"
    )

    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": context}],
    )

    return response.content[0].text.strip() if response.content else ""
