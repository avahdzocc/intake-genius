"""Phase 4 tests: retry logic, PII redaction, rate limiting, doc generator, admin dashboard."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport, TimeoutException

from src.main import app
from src.db.queries import create_case
from src.models.case import Case, CaseStatus
from src.utils.pii import redact, redact_phone
from src.utils.retry import retry_async


# ── PII redaction ─────────────────────────────────────────────────────────────

def test_redact_phone_in_text():
    text = "Call the client at +1 (555) 123-4567 to confirm."
    result = redact(text)
    assert "123-4567" not in result
    assert "555" not in result or "***" in result


def test_redact_email_in_text():
    text = "Send documents to john.doe@example.com before the hearing."
    result = redact(text)
    assert "john.doe@example.com" not in result
    assert "@***" in result


def test_redact_phone_helper():
    assert redact_phone("+15551234567") == "***-4567"
    assert redact_phone("555-123-4567") == "***-4567"


def test_redact_preserves_non_pii():
    text = "Case involves a car accident on Highway 101."
    assert redact(text) == text


# ── Retry logic ───────────────────────────────────────────────────────────────

async def test_retry_succeeds_first_attempt():
    call_count = 0

    async def always_ok():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(always_ok, label="test")
    assert result == "ok"
    assert call_count == 1


async def test_retry_recovers_on_second_attempt():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutException("timeout")
        return "recovered"

    result = await retry_async(flaky, max_attempts=3, backoff_base=0.01, label="test")
    assert result == "recovered"
    assert call_count == 2


async def test_retry_raises_after_exhaustion():
    async def always_fails():
        raise TimeoutException("always fails")

    with pytest.raises(TimeoutException):
        await retry_async(always_fails, max_attempts=2, backoff_base=0.01, label="test")


async def test_retry_does_not_retry_non_retryable():
    call_count = 0

    async def bad_input():
        nonlocal call_count
        call_count += 1
        raise ValueError("bad input — should not retry")

    with pytest.raises(ValueError):
        await retry_async(bad_input, max_attempts=3, backoff_base=0.01, label="test")
    assert call_count == 1  # only tried once


# ── Rate limiting ─────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_rate_limit_allows_normal_traffic(client):
    """A single intake submission should not be rate-limited."""
    resp = await client.post(
        "/api/intake/new",
        json={
            "client_name": "Rate Test",
            "client_phone": "+15550001234",
            "description": "Test intake.",
        },
    )
    assert resp.status_code == 200


async def test_rate_limit_returns_429_on_burst(client):
    """11 rapid POSTs from the same IP should trigger a 429 on the 11th."""
    results = []
    for _ in range(11):
        r = await client.post(
            "/api/intake/new",
            json={
                "client_name": "Burst Test",
                "client_phone": "+15550009876",
                "description": "burst",
            },
        )
        results.append(r.status_code)
    assert 429 in results


# ── Security headers ──────────────────────────────────────────────────────────

async def test_security_headers_present(client):
    resp = await client.get("/api/internal/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-xss-protection") == "1; mode=block"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


# ── Engagement letter endpoint ────────────────────────────────────────────────

@patch("src.agent.doc_generator._client")
async def test_engagement_letter_endpoint(mock_claude, client):
    """GET /api/intake/{id}/engagement-letter returns generated letter text."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Dear Test,\n\nWelcome to our firm.\n\nSincerely,\nTest Firm")]
    mock_claude.messages.create = AsyncMock(return_value=mock_msg)

    case = Case(
        client_name="Letter Test",
        client_phone="+15550001111",
        case_type="personal_injury",
        status=CaseStatus.AWAITING_DOCS,
        consult_datetime="2026-07-01T09:00:00+00:00",
        raw_intake_text="Car accident on Main St.",
    )
    await create_case(case)

    resp = await client.get(f"/api/intake/{case.id}/engagement-letter")
    assert resp.status_code == 200
    assert "Dear" in resp.text


async def test_engagement_letter_404_for_missing_case(client):
    resp = await client.get("/api/intake/nonexistent-id/engagement-letter")
    assert resp.status_code == 404


# ── Admin dashboard ───────────────────────────────────────────────────────────

async def test_admin_dashboard_served(client):
    resp = await client.get("/admin/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Intake Genius" in resp.text


async def test_admin_stats_endpoint(client):
    resp = await client.get("/admin/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cases" in data
    assert "by_status" in data
    assert "firm_name" in data


async def test_admin_cases_endpoint(client):
    case = Case(client_name="Admin List Test", raw_intake_text="Test.")
    await create_case(case)

    resp = await client.get("/admin/api/cases")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert case.id in ids


async def test_admin_case_detail_endpoint(client):
    case = Case(
        client_name="Admin Detail Test",
        case_type="estate_planning",
        raw_intake_text="Need a will.",
    )
    await create_case(case)

    resp = await client.get(f"/admin/api/cases/{case.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case"]["id"] == case.id
    assert "audit_log" in data
    assert "missing_documents" in data
    assert "engagement_letter" in data


async def test_admin_case_detail_404(client):
    resp = await client.get("/admin/api/cases/does-not-exist")
    assert resp.status_code == 404
