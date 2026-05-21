"""Tests for the Twilio and n8n webhook endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from src.main import app
from src.db.queries import create_case
from src.models.case import Case, CaseStatus


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_health_endpoint(client):
    resp = await client.get("/api/internal/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "firm_name" in data


async def test_new_intake_endpoint(client):
    resp = await client.post(
        "/api/intake/new",
        json={
            "client_name": "Test Client",
            "client_phone": "+15550001111",
            "description": "I need help with my case.",
            "intake_source": "web_form",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "case_id" in data
    assert data["status"] == "NEW"


async def test_get_case_endpoint(client):
    case = Case(client_name="Lookup Test", raw_intake_text="Test.")
    await create_case(case)

    resp = await client.get(f"/api/intake/{case.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == case.id


async def test_get_case_not_found(client):
    resp = await client.get("/api/intake/nonexistent-id")
    assert resp.status_code == 404


async def test_stale_cases_empty(client):
    resp = await client.get("/api/internal/cases/stale")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_cases(client):
    case = Case(client_name="List Test", raw_intake_text="Test.")
    await create_case(case)

    resp = await client.get("/api/internal/cases")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert case.id in ids


async def test_audit_trail_endpoint(client):
    case = Case(client_name="Audit Test", raw_intake_text="Audit test.")
    await create_case(case)

    resp = await client.get(f"/api/internal/audit/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case.id
    assert "entries" in data


async def test_twilio_inbound_no_matching_case(client):
    """Inbound SMS from an unknown number returns TwiML and doesn't crash."""
    resp = await client.post(
        "/webhooks/twilio/inbound",
        data={
            "From": "+19990000000",
            "To": "+10000000000",
            "Body": "Hello",
            "MessageSid": "SM_test_000",
            "NumMedia": "0",
        },
    )
    assert resp.status_code == 200
    assert "Response" in resp.text  # TwiML


@patch("src.agent.orchestrator.send_sms", new_callable=AsyncMock)
async def test_client_reply_confirm(mock_sms, client):
    """Client replying YES to a SCHEDULING case should advance it."""
    mock_sms.return_value = {"sid": "SM1", "status": "queued"}

    case = Case(
        client_name="Reply Test",
        client_phone="+15550002222",
        case_type="personal_injury",
        status=CaseStatus.SCHEDULING,
        consult_datetime="2026-06-01T14:00:00+00:00",
        raw_intake_text="Car accident.",
    )
    await create_case(case)

    resp = await client.post(
        f"/api/intake/{case.id}/client-reply",
        json={"body": "YES", "from_phone": "+15550002222"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "confirmed"
    assert data["new_status"] == "AWAITING_DOCS"


async def test_n8n_conflict_resolved_webhook(client):
    """n8n posts to /webhooks/n8n/conflict-resolved to clear a flagged case."""
    case = Case(
        client_name="Conflict Test",
        status=CaseStatus.CONFLICT_FLAGGED,
        raw_intake_text="Divorce case.",
    )
    await create_case(case)

    resp = await client.post(
        "/webhooks/n8n/conflict-resolved",
        json={"case_id": case.id, "cleared": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == case.id


async def test_intake_form_served(client):
    """The root path should serve the HTML intake form."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "consultation" in resp.text.lower()
