import json
from difflib import SequenceMatcher
from pathlib import Path

import anthropic

from src.config import settings
from src.db.queries import search_parties_all
from src.models.case import Case

_PROMPT_PATH = Path(__file__).parent / "prompts" / "conflict_eval.txt"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3)

_CONFLICT_EVAL_TOOL = {
    "name": "submit_conflict_evaluation",
    "description": "Submit structured conflict evaluation results",
    "input_schema": {
        "type": "object",
        "properties": {
            "evaluations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "match_index": {"type": "integer"},
                        "is_conflict": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["match_index", "is_conflict", "confidence", "explanation"],
                },
            }
        },
        "required": ["evaluations"],
    },
}


def _normalize(name: str) -> str:
    return name.lower().strip()


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def extract_all_parties(case: Case) -> list[str]:
    parties: list[str] = []
    if case.client_name:
        parties.append(case.client_name)
    for adverse in case.key_entities.get("adverse_parties", []):
        if adverse and adverse not in parties:
            parties.append(adverse)
    return parties


async def check_conflicts(case: Case) -> dict:
    parties = extract_all_parties(case)
    if not parties:
        return {"status": "CLEAR", "matches": []}

    all_existing = await search_parties_all()
    potential_matches = []

    for party in parties:
        for existing in all_existing:
            score = _fuzzy_score(party, existing.get("party_name", ""))
            if score >= 0.82:
                potential_matches.append(
                    {
                        "new_party": party,
                        "existing_party": existing.get("party_name"),
                        "existing_case_id": existing.get("case_id"),
                        "existing_role": existing.get("party_role"),
                        "similarity_score": score,
                    }
                )

    if not potential_matches:
        return {"status": "CLEAR", "matches": []}

    evaluation = await _evaluate_conflicts(case, potential_matches)
    return evaluation


async def _evaluate_conflicts(case: Case, matches: list[dict]) -> dict:
    system_prompt = _PROMPT_PATH.read_text()
    context = {
        "new_case": {
            "client_name": case.client_name,
            "case_type": case.case_type,
            "raw_intake": case.raw_intake_text,
        },
        "potential_matches": matches,
    }

    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Evaluate these potential conflicts:\n\n{json.dumps(context, indent=2)}",
            }
        ],
        tools=[_CONFLICT_EVAL_TOOL],
        tool_choice={"type": "auto"},
    )

    evaluations: list[dict] = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_conflict_evaluation":
            evaluations = block.input.get("evaluations", [])
            break

    real_conflicts = []
    for i, match in enumerate(matches):
        eval_entry = next((e for e in evaluations if e.get("match_index") == i), None)
        if eval_entry and eval_entry.get("is_conflict") and eval_entry.get("confidence", 0) >= 0.7:
            real_conflicts.append({**match, "evaluation": eval_entry})

    if real_conflicts:
        return {"status": "CONFLICT_FLAGGED", "matches": real_conflicts, "evaluations": evaluations}

    return {"status": "CLEAR", "matches": matches, "evaluations": evaluations}
