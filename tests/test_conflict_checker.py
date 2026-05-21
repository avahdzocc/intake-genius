import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.case import Case

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sample_conflicts.json").read_text())

# Adverse parties keyed by scenario — simulates what the classifier would extract
_ADVERSE_PARTIES: dict[str, list[str]] = {
    "clear_conflict": ["Morgan Ellis"],
    "same_last_name_different_person": [],
    "no_matches": [],
}


def _make_tool_response(evaluations: list[dict]) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "submit_conflict_evaluation"
    tool_block.input = {"evaluations": evaluations}
    mock_response = MagicMock()
    mock_response.content = [tool_block]
    return mock_response


@pytest.mark.parametrize("fixture", FIXTURES)
@patch("src.agent.conflict_checker.search_parties_all")
@patch("src.agent.conflict_checker._client")
async def test_conflict_scenarios(mock_client, mock_search, fixture):
    mock_search.return_value = fixture["existing_parties"]

    num_matches = len(fixture["existing_parties"])
    if fixture["expected_status"] == "CONFLICT_FLAGGED":
        evaluations = [
            {"match_index": i, "is_conflict": True, "confidence": 0.94, "explanation": "Direct conflict."}
            for i in range(num_matches)
        ]
    else:
        evaluations = [
            {"match_index": i, "is_conflict": False, "confidence": 0.1, "explanation": "Different person."}
            for i in range(num_matches)
        ]

    mock_client.messages.create = AsyncMock(return_value=_make_tool_response(evaluations))

    case_data = fixture["new_case"]
    adverse = _ADVERSE_PARTIES.get(fixture["scenario"], [])
    case = Case(
        client_name=case_data["client_name"],
        case_type=case_data["case_type"],
        raw_intake_text=case_data["raw_intake_text"],
        key_entities={"adverse_parties": adverse},
    )

    from src.agent.conflict_checker import check_conflicts

    result = await check_conflicts(case)
    assert result["status"] == fixture["expected_status"]
