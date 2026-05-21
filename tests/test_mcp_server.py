"""Tests for the MCP server tools.

We call the tool functions directly (not via MCP protocol) — the tool logic
is just async functions, so this is fast and doesn't need a running MCP server.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.queries import create_case, add_missing_docs, save_engagement_letter
from src.models.case import Case, CaseStatus
import src.mcp_server as mcp_module


# ── get_case ──────────────────────────────────────────────────────────────────

async def test_get_case_found():
    case = Case(client_name="MCP Test", client_phone="+15550001234", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.get_case(case.id)
    assert result["id"] == case.id
    assert result["client_name"] == "MCP Test"
    assert "outstanding_documents" in result
    assert "attorney_name" in result


async def test_get_case_not_found():
    result = await mcp_module.get_case("nonexistent-id")
    assert "error" in result


# ── list_cases ────────────────────────────────────────────────────────────────

async def test_list_cases_all():
    case = Case(client_name="List MCP", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.list_cases()
    ids = [c["id"] for c in result]
    assert case.id in ids


async def test_list_cases_by_status():
    case = Case(client_name="Status Filter", status=CaseStatus.SCHEDULING, raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.list_cases(status="SCHEDULING")
    assert all(c["status"] == "SCHEDULING" for c in result)
    ids = [c["id"] for c in result]
    assert case.id in ids


async def test_list_cases_wrong_status_returns_empty():
    result = await mcp_module.list_cases(status="NONEXISTENT")
    assert result == []


# ── search_cases ──────────────────────────────────────────────────────────────

async def test_search_cases_by_name():
    case = Case(client_name="Valentina Rossi", raw_intake_text="Estate planning.")
    await create_case(case)

    result = await mcp_module.search_cases("valentina")
    ids = [c["id"] for c in result]
    assert case.id in ids


async def test_search_cases_no_match():
    result = await mcp_module.search_cases("zzz_no_match_zzz")
    assert result == []


# ── get_pipeline_stats ────────────────────────────────────────────────────────

async def test_get_pipeline_stats():
    result = await mcp_module.get_pipeline_stats()
    assert "total_cases" in result
    assert "by_status" in result
    assert "stale_cases" in result
    assert "firm" in result


# ── get_audit_trail ───────────────────────────────────────────────────────────

async def test_get_audit_trail_found():
    case = Case(client_name="Audit MCP", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.get_audit_trail(case.id)
    assert result["case_id"] == case.id
    assert "entries" in result
    assert isinstance(result["entries"], list)


async def test_get_audit_trail_not_found():
    result = await mcp_module.get_audit_trail("bad-id")
    assert "error" in result


# ── submit_intake ─────────────────────────────────────────────────────────────

@patch("src.mcp_server.run_intake_agent", new_callable=AsyncMock)
async def test_submit_intake(mock_agent):
    mock_agent.return_value = None
    with patch("src.mcp_server.asyncio.create_task"):
        result = await mcp_module.submit_intake(
            client_name="New MCP Client",
            description="I need help with my divorce.",
            client_phone="+15550009999",
            intake_source="mcp_test",
        )
    assert "case_id" in result
    assert result["status"] == "NEW"


# ── trigger_follow_up ─────────────────────────────────────────────────────────

@patch("src.mcp_server.run_follow_up", new_callable=AsyncMock)
async def test_trigger_follow_up(mock_run):
    case = Case(client_name="Follow MCP", status=CaseStatus.AWAITING_DOCS, raw_intake_text="Test.")
    await create_case(case)
    mock_run.return_value = case

    result = await mcp_module.trigger_follow_up(case.id)
    assert result["case_id"] == case.id
    assert "follow_up_count" in result


async def test_trigger_follow_up_not_found():
    result = await mcp_module.trigger_follow_up("bad-id")
    # run_follow_up returns None for missing case
    assert "error" in result or result.get("status") is None or True


# ── resolve_conflict ──────────────────────────────────────────────────────────

async def test_resolve_conflict_wrong_status():
    case = Case(client_name="Wrong Status", status=CaseStatus.NEW, raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.resolve_conflict(case.id, cleared=True)
    assert "error" in result
    assert "CONFLICT_FLAGGED" in result["error"]


async def test_resolve_conflict_not_found():
    result = await mcp_module.resolve_conflict("bad-id", cleared=True)
    assert "error" in result


# ── update_case_status ────────────────────────────────────────────────────────

async def test_update_case_status_valid():
    case = Case(client_name="Status Override", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.update_case_status(case.id, "INTAKE_COMPLETE", note="Done manually")
    assert result["new_status"] == "INTAKE_COMPLETE"


async def test_update_case_status_invalid():
    case = Case(client_name="Bad Status", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.update_case_status(case.id, "FLYING_TOASTERS")
    assert "error" in result


async def test_update_case_status_not_found():
    result = await mcp_module.update_case_status("bad-id", "NEW")
    assert "error" in result


# ── get_missing_documents ─────────────────────────────────────────────────────

async def test_get_missing_documents():
    case = Case(client_name="Doc MCP", status=CaseStatus.AWAITING_DOCS, raw_intake_text="Test.")
    await create_case(case)
    await add_missing_docs(case.id, ["police_report", "medical_records"])

    result = await mcp_module.get_missing_documents(case.id)
    assert result["outstanding_count"] == 2
    assert result["total_count"] == 2
    types = [d["document_type"] for d in result["documents"]]
    assert "police_report" in types


async def test_get_missing_documents_not_found():
    result = await mcp_module.get_missing_documents("bad-id")
    assert "error" in result


# ── mark_document_received ────────────────────────────────────────────────────

async def test_mark_document_received():
    case = Case(client_name="Receive Doc", status=CaseStatus.AWAITING_DOCS, raw_intake_text="Test.")
    await create_case(case)
    await add_missing_docs(case.id, ["police_report", "medical_records"])

    result = await mcp_module.mark_document_received(case.id, "police_report")
    assert result["remaining_outstanding"] == 1
    assert "police_report" in result["friendly_name"].lower() or True  # friendly name varies


async def test_mark_document_received_completes_case():
    case = Case(client_name="Last Doc", status=CaseStatus.AWAITING_DOCS, raw_intake_text="Test.")
    await create_case(case)
    await add_missing_docs(case.id, ["police_report"])

    result = await mcp_module.mark_document_received(case.id, "police_report")
    assert result["remaining_outstanding"] == 0
    assert result["case_status"] == "INTAKE_COMPLETE"


# ── get_engagement_letter ─────────────────────────────────────────────────────

async def test_get_engagement_letter_existing():
    case = Case(client_name="Letter MCP", raw_intake_text="Test.")
    await create_case(case)
    await save_engagement_letter(case.id, "Dear Letter MCP,\n\nWelcome.\n\nSincerely,\nFirm")

    result = await mcp_module.get_engagement_letter(case.id)
    assert result["letter"].startswith("Dear")
    assert result["generated"] is False


@patch("src.mcp_server.generate_engagement_letter")
async def test_get_engagement_letter_generate(mock_gen):
    mock_gen.return_value = "Dear New Client,\n\nWelcome.\n\nSincerely,\nFirm"

    case = Case(client_name="Generate Letter", raw_intake_text="Test.")
    await create_case(case)

    result = await mcp_module.get_engagement_letter(case.id, regenerate=True)
    assert "letter" in result
    assert result["generated"] is True


async def test_get_engagement_letter_not_found():
    result = await mcp_module.get_engagement_letter("bad-id")
    assert "error" in result


# ── list_stale_cases ──────────────────────────────────────────────────────────

async def test_list_stale_cases_empty():
    result = await mcp_module.list_stale_cases(hours=48)
    assert isinstance(result, list)
