# Legal Intake Agent — Claude Code Build Guide

## 1. MCP Servers You Should Wire Into Claude Code

Yes, Claude Code fully supports MCP servers. You add them with `claude mcp add` and they become tools Claude Code can use during your development sessions. This is a significant advantage: Claude Code can directly interact with Twilio, Google Calendar, databases, and other services *while it's building and testing your application*.

There are two distinct ways MCPs matter for this project, and it's important not to confuse them:

**A) MCPs for your dev workflow (Claude Code uses these while building)**

These help Claude Code write, test, and debug your app:

| MCP Server | What it does for you during development | How to add |
|---|---|---|
| **Twilio MCP** | Claude Code can directly test SMS sending, phone number provisioning, and webhook configuration without you writing test scripts. It uses Twilio's actual API. Filter to just the messaging service to keep context costs down. | `claude mcp add twilio -- npx -y @twilio-alpha/mcp YOUR_SID/YOUR_KEY:YOUR_SECRET --services twilio_messaging_v1` |
| **GitHub MCP** | Claude Code can create branches, open PRs, check CI, and manage issues as you build. | `claude mcp add --transport http github https://api.githubcopilot.com/mcp -H "Authorization: Bearer YOUR_PAT"` |
| **PostgreSQL / SQLite MCP** | Claude Code can query your development database directly to verify schemas, check seed data, and debug queries while coding. The community `@benborla29/mcp-server-mysql` and `@modelcontextprotocol/server-postgres` servers work well. | `claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres postgresql://user:pass@localhost/legalintake_dev` |
| **Filesystem MCP** | Already built into Claude Code, but worth noting. It reads and writes files, which is how Claude Code does most of its work. | Built-in, no setup needed. |

**B) MCPs your application uses at runtime (the deployed system calls these)**

This is separate from Claude Code. Your running FastAPI application will call these APIs directly using their Python SDKs, not through MCP. MCP is a development-time protocol for AI assistants; your production system talks to APIs the normal way:

- **Twilio Python SDK** (`twilio` package) for sending/receiving SMS
- **Google Calendar API** (`google-api-python-client`) for scheduling
- **Asana Python SDK** or direct REST API for task management
- **Anthropic Python SDK** (`anthropic` package) for the Claude API calls your agent makes

The key insight: MCP helps Claude Code *build* the integrations faster and test them live. But the deployed app uses standard API clients.

**One exception worth considering:** If you build a custom MCP server as part of your project (using FastMCP in Python), you could expose your legal intake agent's tools via MCP. This would let you connect it to Claude Desktop later, so attorneys could interact with the intake system through a chat interface. That's a Phase 4 feature, not something to worry about now.

### MCP servers to skip

- **Twilio's full API surface** (nearly 2,000 endpoints): Way too large for the context window. Always filter with `--services` to just messaging or the specific APIs you need.
- **Generic "search the web" MCPs**: Claude Code already has web access and its own search. Don't stack redundant capabilities.
- **Multiple MCPs from untrusted community sources alongside Twilio**: Twilio's own security guidance explicitly warns against this due to prompt injection risk.

---

## 2. How to Prompt Claude Code to Start This Build

The single most important thing is your `CLAUDE.md` file. This is a markdown file in your project root that Claude Code reads at the start of every session. It acts as persistent context: your project's architectural decisions, coding standards, file structure, and constraints. Without it, every session starts from zero.

### Step 1: Create the project directory and CLAUDE.md

Before you even open Claude Code, create the folder structure and seed the CLAUDE.md:

```bash
mkdir legal-intake-agent && cd legal-intake-agent
```

Then create this `CLAUDE.md`:

```markdown
# Legal Intake Agent — Project Context

## What This Is
An agentic AI system for law firm client intake. When a potential client
submits information (web form, email, SMS, or referral), the agent
autonomously classifies the case, checks for conflicts of interest,
routes to an appropriate attorney, schedules a consultation, and follows
up on missing documents via SMS.

## Architecture
- **Python 3.12+ / FastAPI** backend with async support
- **SQLite** for development (migrate to PostgreSQL for production)
- **Claude API** (claude-sonnet-4-20250514) for classification, conflict
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
    twilio_sms.py
    google_calendar.py
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
NEW -> CLASSIFYING -> CONFLICT_CHECK -> ROUTING -> SCHEDULING ->
AWAITING_DOCS -> INTAKE_COMPLETE

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

## Current Phase
Phase 1: Core agent without integrations. Focus on the orchestrator,
classifier, conflict checker, and router. Use mock/stub integrations.
```

### Step 2: Your opening prompt to Claude Code

Run `claude` in the project directory, then use a prompt like this:

```
I'm building an agentic AI legal intake system. Read the CLAUDE.md for
full context.

For this session, let's set up the project foundation:

1. Initialize pyproject.toml with these dependencies: fastapi, uvicorn,
   anthropic, httpx, pydantic, pydantic-settings, python-dotenv,
   aiosqlite, pytest, pytest-asyncio

2. Create src/config.py using pydantic-settings to load env vars

3. Create the SQLite database schema in src/db/database.py with tables
   for: cases, case_parties, attorneys, missing_documents, audit_log
   (see CLAUDE.md for the state machine states)

4. Create the Pydantic models in src/models/ matching those tables

5. Create src/main.py with a FastAPI app skeleton that initializes the
   database on startup

6. Create .env.example with all required variables

7. Create a seed script at src/db/seed.py that inserts 4-5 sample
   attorneys with different practice areas, jurisdictions, and
   capacity levels

Don't build the agent logic yet. Just the foundation that everything
else will plug into.
```

### Step 3: Follow-up sessions (one per module)

Each subsequent Claude Code session should focus on one module. Here's the sequence with example prompts:

**Session 2 — The Classifier:**
```
Read CLAUDE.md. Now build the case classifier in
src/agent/classifier.py.

It should:
- Take raw intake text (a description from a potential client)
- Call Claude API with a structured prompt
- Return a ClassificationResult with: case_type (enum of your top 8
  practice areas), urgency (emergency/time_sensitive/standard),
  jurisdiction (state + county), complexity (simple/moderate/complex),
  key_entities (client name, adverse parties, dates, locations)

Create the prompt in src/agent/prompts/classifier.txt. Include 3-4
few-shot examples covering different practice areas.

Write tests in tests/test_classifier.py using 5 sample intake
descriptions. Mock the Claude API call for fast tests, but also
include one integration test marked with @pytest.mark.integration
that hits the real API.
```

**Session 3 — Conflict Checker:**
```
Read CLAUDE.md. Build the conflict checker in
src/agent/conflict_checker.py.

It needs:
- extract_all_parties(case) to pull client + adverse parties from
  classification results
- search_exact(name) and search_fuzzy(name, threshold) against the
  case_parties table
- A Claude API call in evaluate_conflicts() that takes a case and a
  list of potential matches and returns whether each is a real
  conflict, with a confidence score and explanation

Store the evaluation prompt in src/agent/prompts/conflict_eval.txt.

For fuzzy matching, use simple normalized Levenshtein distance (don't
add a heavy dependency, just implement a basic version or use
difflib.SequenceMatcher).

Write tests with fixtures that include: a clear match, a fuzzy match
that is a real conflict, a fuzzy match that is not a conflict (same
last name, different person), and a clean case with no matches.
```

**Session 4 — Attorney Router:**
```
Read CLAUDE.md. Build the attorney router in src/agent/router.py.

Scoring algorithm:
- practice_area_match: 40 points if the attorney's practice areas
  include the case type
- jurisdiction_match: 30 points if the attorney is admitted in the
  relevant state
- capacity_score: 20 points * (1 - current_cases / max_cases)
- complexity_match: 10 points if attorney seniority fits case
  complexity

Return the top-ranked attorney. If no attorney scores above 50,
return None (the case needs manual assignment).

Don't check calendar availability yet, that comes in the integration
phase. Just add a TODO comment where that check will go.
```

**Session 5 — The Orchestrator:**
```
Read CLAUDE.md. Now build the main agentic loop in
src/agent/orchestrator.py.

This ties together classifier, conflict_checker, and router.

The loop:
1. observe() - check current case state, what's present, what's missing
2. reason() - based on observation, determine next actions
3. act() - execute actions (for now, just update case state and log
   to audit_log; integration actions are stubs)
4. evaluate() - did the actions succeed? is intake complete or does
   the loop need to continue?

The orchestrator should be async and process one case at a time.
Include a run(case_id) entry point that loads a case and runs the
loop until it reaches a terminal state or needs external input.

Every iteration must write to audit_log with the observation,
reasoning, action taken, and result.

Write an end-to-end test that creates a new case from raw intake
text and verifies it moves through:
NEW -> CLASSIFYING -> CONFLICT_CHECK -> ROUTING
```

### Tips for effective Claude Code prompting

- **Always start with "Read CLAUDE.md"** so it loads your architectural context
- **One module per session**. Don't ask for the whole system at once.
- **Be specific about what NOT to build yet**. "Don't add calendar integration, just put a TODO" prevents scope creep.
- **Ask for tests alongside code**. Claude Code writes better code when it knows it also has to write tests for it.
- **Update CLAUDE.md between sessions** to reflect what's been built. Add a "Completed" section and update "Current Phase."
- **Use `/init` on first run** if you want Claude Code to generate an initial CLAUDE.md for you, but you'll probably want to replace it with the detailed one above.

---

## 3. Full Tech Stack and Infrastructure

### Backend

| Layer | Tool | Why |
|---|---|---|
| **Framework** | FastAPI (Python 3.12+) | Async-native, automatic OpenAPI docs, Pydantic integration, great for webhook endpoints |
| **AI** | Anthropic Python SDK + Claude Sonnet | The reasoning engine for classification, conflict evaluation, and reply parsing |
| **Database (dev)** | SQLite via aiosqlite | Zero setup, perfect for development and demos. Single file, easy to reset. |
| **Database (prod)** | PostgreSQL via asyncpg | When you deploy for real, migrate to Postgres. Same SQL, better concurrency. Supabase is an easy hosted option. |
| **Task queue** | arq (Redis-backed) | Lightweight async task queue. The agent loop should run in the background, not block the API response. Alternative: just use asyncio.create_task() for the MVP. |
| **SMS** | Twilio Python SDK | Outbound SMS, inbound webhook processing, delivery status callbacks |
| **Calendar** | Google Calendar API (google-api-python-client) | Check attorney availability, create consultation events with Zoom/Meet links |
| **Task management** | Asana Python SDK or Linear API | Create case tasks, assign to attorneys, track status. Pick whichever your firm already uses. |

### Frontend

You have a few options depending on how polished you need the demo to be:

**Option A: No custom frontend (fastest path to a demo)**

Skip building a frontend entirely for Phase 1. Use:
- A simple HTML form (static file served by FastAPI) that POSTs to your intake endpoint
- Asana boards as the "attorney dashboard" (they can see and manage cases there)
- SMS as the client interface (clients interact entirely via text message)

This is actually a viable production architecture for a small firm. The attorneys live in Asana, clients interact via SMS, and the agent handles everything in between.

**Option B: Simple React frontend (good for demos and investor presentations)**

| Tool | Role |
|---|---|
| **Next.js 14+** | React framework with App Router, server components, API routes |
| **Tailwind CSS** | Styling without writing custom CSS |
| **shadcn/ui** | Pre-built accessible components (tables, forms, dialogs) |
| **Vercel** | One-click deploy for the frontend. Free tier is fine for demos. |

Pages you'd build:
- `/intake` — Client-facing intake form
- `/dashboard` — Attorney view showing their assigned cases, statuses, upcoming consultations
- `/case/[id]` — Individual case detail with audit trail, timeline, and status
- `/admin` — Manage attorneys, view system health, conflict queue

**Option C: Use an existing tool as the frontend**

If this is for a real firm, consider skipping custom frontend code entirely and using Retool, Softr, or Bubble to build admin dashboards on top of your API. These connect directly to your database or API and you can build CRUD interfaces in hours instead of days.

### Workflow Orchestration

| Tool | Role |
|---|---|
| **n8n (self-hosted via Docker)** | Webhook routing, cron jobs, visual workflow debugging. Run it with `docker run -d --name n8n -p 5678:5678 n8nio/n8n` |
| **Alternative: Make.com** | If you don't want to self-host. Easier UI, but your data flows through their servers. |
| **Alternative: Zapier** | Best for quick prototyping. Most limited in terms of custom logic, but fastest to set up. |

### Deployment

**For the demo/MVP:**

```
┌─────────────────────────┐     ┌──────────────────────┐
│  Vercel (free tier)     │     │  Railway / Render     │
│  Next.js frontend       │────→│  FastAPI backend      │
│  Static intake form     │     │  SQLite database      │
└─────────────────────────┘     │  Agent orchestrator   │
                                └──────────┬───────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                    ┌──────────┐   ┌──────────────┐  ┌──────────┐
                    │ Twilio   │   │ Google Cal   │  │ Asana    │
                    │ (SMS)    │   │ (Scheduling) │  │ (Tasks)  │
                    └──────────┘   └──────────────┘  └──────────┘
```

| Service | What | Cost |
|---|---|---|
| **Railway** or **Render** | Host the FastAPI backend. Both support Python, have free/cheap tiers, and handle HTTPS. Railway is slightly easier for Python apps. | $5-7/mo for a hobby instance |
| **Vercel** | Host the Next.js frontend (if you build one). Free tier is generous. | Free |
| **Twilio** | SMS. You need a phone number ($1/mo) and per-message costs ($0.0079/SMS). | ~$5-15/mo for a demo |
| **Supabase** | Hosted PostgreSQL when you outgrow SQLite. Free tier includes a database. | Free for dev |
| **n8n Cloud** or self-hosted on Railway | Workflow orchestration. Self-hosting is free (just costs the server). n8n Cloud starts at ~$24/mo. | $0-24/mo |

**For production (later):**

Move the FastAPI backend to a VPS (DigitalOcean, Hetzner) or AWS ECS where you control the environment. Legal data should live on infrastructure you control, not shared free-tier hosting. Use PostgreSQL, add encryption at rest, set up proper backup rotation.

### Tools you do NOT need

- **LangChain / LangGraph**: Adds complexity without value here. Your agent loop is straightforward enough to build directly with the Anthropic SDK. LangChain's abstractions would get in the way more than they'd help.
- **Vector databases (Pinecone, Weaviate)**: You're not doing semantic search over documents. Your conflict checker uses fuzzy string matching, not embeddings. If you later add a "search similar past cases" feature, consider it then.
- **Kubernetes**: Massive overkill. A single Railway or Render instance handles this easily.
- **Celery**: Too heavy for this use case. Use `arq` or just `asyncio.create_task()` for background processing.

### The complete dependency list

```toml
[project]
name = "legal-intake-agent"
requires-python = ">=3.12"
dependencies = [
    # Core
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",

    # AI
    "anthropic>=0.40.0",

    # Database
    "aiosqlite>=0.20.0",

    # Integrations
    "twilio>=9.3.0",
    "google-api-python-client>=2.150.0",
    "google-auth-oauthlib>=1.2.0",

    # Background tasks (optional, can use asyncio for MVP)
    # "arq>=0.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-httpx>=0.34.0",
    "ruff>=0.7.0",
]
```
