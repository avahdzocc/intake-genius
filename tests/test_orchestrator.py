import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.queries import create_case
from src.models.case import Case, CaseStatus


def _make_classification():
    c = MagicMock()
    c.case_type = "personal_injury"
    c.urgency = MagicMock(value="standard")
    c.jurisdiction = "California"
    c.complexity = MagicMock(value="moderate")
    c.key_entities = {"adverse_parties": []}
    return c


def _make_attorney():
    a = MagicMock()
    a.id = "atty-001"
    a.name = "Sarah Chen"
    a.email = "schen@firm.com"
    return a


@patch("src.agent.orchestrator.create_task", new_callable=AsyncMock)
@patch("src.agent.orchestrator.create_event", new_callable=AsyncMock)
@patch("src.agent.orchestrator.find_next_available_slot", new_callable=AsyncMock)
@patch("src.agent.orchestrator.send_sms", new_callable=AsyncMock)
@patch("src.agent.orchestrator.get_attorney_by_id", new_callable=AsyncMock)
@patch("src.agent.orchestrator.route_to_attorney")
@patch("src.agent.orchestrator.check_conflicts")
@patch("src.agent.orchestrator.classify_intake")
async def test_orchestrator_happy_path(
    mock_classify,
    mock_conflicts,
    mock_route,
    mock_get_attorney,
    mock_sms,
    mock_find_slot,
    mock_create_event,
    mock_create_task,
):
    # Build a real case in the temp DB (conftest creates schema)
    case = Case(
        client_name="Alex Johnson",
        client_phone="+15550001234",
        raw_intake_text="I was in a car accident.",
        intake_source="web_form",
    )
    await create_case(case)

    classification = _make_classification()
    attorney = _make_attorney()
    slot_dt = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)

    async def fake_classify(text):
        return classification

    async def fake_conflicts(c):
        return {"status": "CLEAR", "matches": []}

    async def fake_route(c):
        return attorney

    mock_classify.side_effect = fake_classify
    mock_conflicts.side_effect = fake_conflicts
    mock_route.side_effect = fake_route
    mock_get_attorney.return_value = attorney
    mock_find_slot.return_value = slot_dt
    mock_create_event.return_value = {"event_id": "evt-123", "datetime": slot_dt.isoformat(), "html_link": ""}
    mock_create_task.return_value = {"task_gid": "task-456", "title": "New intake", "url": ""}
    mock_sms.return_value = {"sid": "SM123", "status": "queued"}

    from src.agent.orchestrator import run_intake_agent

    result = await run_intake_agent(case.id)

    assert result is not None
    assert result.status == CaseStatus.SCHEDULING
    assert result.case_type == "personal_injury"
    assert result.assigned_attorney_id == "atty-001"
    assert result.consult_datetime is not None

    # Verify all integrations were called
    mock_classify.assert_called_once()
    mock_conflicts.assert_called_once()
    mock_route.assert_called_once()
    mock_find_slot.assert_called_once()
    mock_create_event.assert_called_once()
    mock_create_task.assert_called_once()
    mock_sms.assert_called_once()


@patch("src.agent.orchestrator.create_task", new_callable=AsyncMock)
@patch("src.agent.orchestrator.send_sms", new_callable=AsyncMock)
@patch("src.agent.orchestrator.get_attorney_by_id", new_callable=AsyncMock)
@patch("src.agent.orchestrator.route_to_attorney")
@patch("src.agent.orchestrator.check_conflicts")
@patch("src.agent.orchestrator.classify_intake")
async def test_orchestrator_conflict_flagged(
    mock_classify,
    mock_conflicts,
    mock_route,
    mock_get_attorney,
    mock_sms,
    mock_create_task,
):
    case = Case(
        client_name="Jamie Torres",
        client_phone="+15550005678",
        raw_intake_text="I need a divorce. My spouse is Morgan Ellis.",
        intake_source="web_form",
    )
    await create_case(case)

    classification = _make_classification()
    classification.case_type = "family_law"

    async def fake_classify(text):
        return classification

    async def fake_conflicts(c):
        return {"status": "CONFLICT_FLAGGED", "matches": [{"existing_party": "Morgan L. Ellis"}]}

    mock_classify.side_effect = fake_classify
    mock_conflicts.side_effect = fake_conflicts
    mock_create_task.return_value = {"task_gid": "task-789", "title": "Conflict review", "url": ""}

    from src.agent.orchestrator import run_intake_agent

    result = await run_intake_agent(case.id)

    assert result is not None
    assert result.status == CaseStatus.CONFLICT_FLAGGED
    mock_route.assert_not_called()     # Router should NOT run on a conflict
    mock_sms.assert_not_called()       # Client should NOT be contacted
    mock_create_task.assert_called_once()  # Managing partner task created


@patch("src.agent.orchestrator.create_task", new_callable=AsyncMock)
@patch("src.agent.orchestrator.create_event", new_callable=AsyncMock)
@patch("src.agent.orchestrator.find_next_available_slot", new_callable=AsyncMock)
@patch("src.agent.orchestrator.send_sms", new_callable=AsyncMock)
@patch("src.agent.orchestrator.get_attorney_by_id", new_callable=AsyncMock)
async def test_handle_client_confirmed(
    mock_get_attorney,
    mock_sms,
    mock_find_slot,
    mock_create_event,
    mock_create_task,
):
    from src.agent.orchestrator import IntakeAgent

    slot_dt = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    case = Case(
        client_name="Alex Johnson",
        client_phone="+15550001234",
        case_type="personal_injury",
        status=CaseStatus.SCHEDULING,
        assigned_attorney_id="atty-001",
        consult_datetime=slot_dt.isoformat(),
        raw_intake_text="Car accident.",
    )
    await create_case(case)

    mock_sms.return_value = {"sid": "SM999", "status": "queued"}

    agent = IntakeAgent(case)
    result = await agent.handle_client_confirmed()

    assert result.status == CaseStatus.AWAITING_DOCS
    mock_sms.assert_called_once()
    # Verify the SMS mentions the expected documents
    sms_body = mock_sms.call_args[0][1]
    assert "Police Report" in sms_body or "Medical Records" in sms_body
