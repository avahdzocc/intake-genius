# Intake Genius — Project Context

## What This Is
An agentic AI system for law firm client intake. When a potential client
submits information (web form, email, SMS, or referral), the agent
autonomously classifies the case, checks for conflicts of interest,
routes to an appropriate attorney, schedules a consultation, and follows
up on missing documents via SMS.

## Architecture
- **Python 3.12+ / FastAPI** backend with async support
- **SQLite** for development (migrate to PostgreSQL for production)
- **Claude API** (claude-sonnet-4-6) for classification, conflict
  evaluation, and reply parsing
- **Twilio** for SMS communication (outbound and inbound)
- **Google Calendar API** for attorney scheduling
- **n8n** (external, self-hosted) for webhook routing and cron jobs

## Project Structure
```
src/
  main.py              — FastAPI app, CORS, lifespan
  config.py            — Settings from env vars (pydantic-settings)
  models/              — Pydantic models (Case, Attorney, AuditEntry)
  db/                  — SQLite setup, queries, migrations
  agent/               — The agentic loop
    orchestrator.py    — observe/reason/act/evaluate loop
    classifier.py      — Case classification via Claude
    conflict_checker.py — Conflict of interest detection
    router.py          — Attorney matching
    follow_up.py       — Stale case follow-up logic
    prompts/           — Text files for each Claude prompt
  integrations/        — External API clients
    twilio_client.py
    calendar_client.py
    task_board.py
  api/                 — FastAPI route handlers
    intake.py          — POST /api/intake/new
    webhooks.py        — Twilio and n8n webhook receivers
    internal.py        — Admin/status endpoints
tests/
  fixtures/
  test_classifier.py
  test_conflict_checker.py
  test_orchestrator.py
```

## Case State Machine
```
NEW -> CLASSIFYING -> CONFLICT_CHECK -> ROUTING -> SCHEDULING ->
AWAITING_DOCS -> INTAKE_COMPLETE
```
Special states: CONFLICT_FLAGGED (needs human), REJECTED, BLOCKED

## Coding Standards
- Use async/await for all I/O (database, API calls, HTTP)
- Type hints on every function signature
- Pydantic models for all data crossing API boundaries
- Store Claude prompts in src/agent/prompts/ as .txt files, not inline
- Every agent action must write to the audit_log table with the
  observation, reasoning, and result
- Use httpx for async HTTP calls (not requests)
- Use python-dotenv for local env management
- Tests use pytest + pytest-asyncio

## Environment Variables (see .env.example)
ANTHROPIC_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
TWILIO_PHONE_NUMBER, GOOGLE_CALENDAR_CREDENTIALS_PATH,
DATABASE_URL, FIRM_NAME, INTAKE_EMAIL

## Completed
- [x] Phase 1: Core agent without integrations
- [x] Phase 2: Integrations
- [x] Phase 3: n8n orchestration
- [x] Phase 4: Polish
- [x] Phase 5: MCP server

## Current Phase
Complete. All five phases shipped.
- FastAPI + n8n system: `uvicorn src.main:app --reload`
- MCP server: `python -m src.mcp_server` (stdio) or `./scripts/mcp-server.sh --sse`
- See docs/mcp-setup.md for Claude Desktop config.

## Phase 5 Notes
- MCP server: `src/mcp_server.py` — 11 tools covering case lookup, intake submission, follow-up, conflict resolution, document management, engagement letters
- FastMCP 3.x — lifespan passed via constructor (not decorator); `@mcp.tool()` for each tool
- DB init happens in `_lifespan` context manager on server startup
- Module-level imports for `run_follow_up`, `run_conflict_resolution`, `run_intake_agent` required for test patching
- Transports: stdio (Claude Desktop), SSE (network), or Claude Code `.claude/settings.json`
- `asyncio.create_task(run_intake_agent(case.id))` fires the agent pipeline non-blocking from `submit_intake`
- `mark_document_received` auto-advances case to INTAKE_COMPLETE when all docs collected
- Tests: 26 MCP tool tests in `tests/test_mcp_server.py`; 66 total passing across all test files
- Setup guide: docs/mcp-setup.md (Claude Desktop config, tool reference, example conversations)
- Shell helper: `scripts/mcp-server.sh` (stdio default, `--sse [port]` for network mode)

## Phase 4 Notes
- Retry logic: `src/utils/retry.py` — async exponential backoff (1s, 2s, 4s) for Twilio, Calendar, Asana
- PII redaction: `src/utils/pii.py` — `redact(text)` masks phones + emails for safe logging
- Security headers middleware: `src/middleware/security_headers.py` — X-Content-Type-Options, X-Frame-Options, etc.
- Rate limiting: `src/middleware/rate_limit.py` — 10 req/60s per IP on `/api/intake/new` (in-process sliding window)
- Engagement letter: Claude-powered via `src/agent/doc_generator.py`; stored in `engagement_letters` table; fallback to template on API failure
- Trigger: auto-generated when case advances to AWAITING_DOCS; accessible at GET /api/intake/{id}/engagement-letter
- Admin dashboard: `GET /admin/` serves `src/static/admin.html`; data from `/admin/api/cases`, `/admin/api/cases/{id}`, `/admin/api/stats`
- Admin features: filterable case list, full audit trail timeline, document status, engagement letter viewer + download
- CORS tightened: no longer `allow_origins=["*"]`; configured via `ALLOWED_ORIGINS` env var (comma-separated)
- `INTERNAL_API_KEY` env var available for production protection of /api/internal/* (not enforced in dev)
- Test suite: 40 tests passing; rate-limit state reset in conftest autouse fixture for isolation
- See docs/security.md for production hardening checklist

## Phase 3 Notes
- Docker Compose: two services (intake-genius + n8n) on shared network; n8n pre-loads workflow JSONs via volume
- n8n workflows: proper 1.x format with UUIDs, typeVersion, webhookId — import from n8n-workflows/
- Intake form: served at GET / from src/static/intake-form.html; submits to n8n or /api/intake/new directly
- New endpoints: GET /api/internal/health, /cases, /audit/{id}, /cases/{id}/missing-docs
- Webhooks: POST /webhooks/twilio/inbound (TwiML response), /webhooks/n8n/conflict-resolved
- python-multipart required for Twilio form-encoded inbound webhook parsing
- Test suite: 22 tests passing (22 unit/integration, 1 integration-only deselected)
- E2E smoke test: scripts/test-e2e.sh against a running server

## Phase 2 Notes
- Twilio: httpx-based REST client; falls back to console log if not configured
- Google Calendar: service account or OAuth; graceful fallback to next-business-day slot
- Asana: httpx REST client; falls back to console log if not configured
- `get_db()` is now an @asynccontextmanager (was previously double-starting the aiosqlite thread)
- Orchestrator scheduling step: find slot → create event → SMS client → Asana task → SCHEDULING
- Conflict notify step: Asana high-priority task for managing partner, client NOT contacted
- `handle_client_confirmed()`: SCHEDULING → AWAITING_DOCS, seeds missing_documents, sends doc SMS
- `handle_follow_up()`: generates follow-up SMS; blocks + creates manual task after MAX_FOLLOW_UPS
- `handle_conflict_resolved()`: resumes agent loop (cleared) or sends declination SMS (rejected)
- New endpoints: POST /api/intake/{id}/client-reply, POST /api/intake/{id}/follow-up
- Twilio inbound webhook: looks up case by phone, routes reply to handle_client_confirmed
- Conftest uses per-test temp SQLite file (not :memory:) so multiple connections share schema
