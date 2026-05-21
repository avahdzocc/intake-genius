import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.case import CaseUrgency, CaseComplexity, ClassificationResult


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sample_intakes.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES)
@patch("src.agent.classifier._client")
async def test_classify_returns_result(mock_client, fixture):
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.name = "submit_classification"
    mock_tool_use.input = {
        "case_type": fixture["expected_case_type"],
        "urgency": fixture["expected_urgency"],
        "jurisdiction": "California",
        "complexity": fixture["expected_complexity"],
        "key_entities": {},
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_use]
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    from src.agent.classifier import classify_intake

    result = await classify_intake(fixture["description"])

    assert isinstance(result, ClassificationResult)
    assert result.case_type == fixture["expected_case_type"]
    assert result.urgency == CaseUrgency(fixture["expected_urgency"])
    assert result.complexity == CaseComplexity(fixture["expected_complexity"])


@pytest.mark.integration
async def test_classify_real_api():
    """Hits the real Claude API. Run with: pytest -m integration"""
    import os
    if os.environ.get("ANTHROPIC_API_KEY", "").startswith("test-"):
        pytest.skip("No real API key — set ANTHROPIC_API_KEY to run integration tests")

    from src.agent.classifier import classify_intake

    result = await classify_intake(
        "I was in a car accident last week and the other driver ran a red light. "
        "I have whiplash and my car is damaged. We are in Los Angeles, California."
    )
    assert result.case_type in ("personal_injury", "other")
    assert result.urgency in (CaseUrgency.STANDARD, CaseUrgency.TIME_SENSITIVE)
