# Agentic AI Legal Intake System — Architecture & Build Plan

## What Makes This Genuinely Agentic

A form with AI is not an agent. An agent has an **observe-reason-act loop** that runs autonomously until a goal is met. In this system, that means: a new lead arrives, the agent classifies it, checks for conflicts, picks the right attorney, schedules a consultation, creates a case board, sends the client a text, and then *monitors for missing information and follows up on its own*. No human clicks "next step" at each stage.

The agent's loop looks like this:

```
1. OBSERVE  — new intake arrives (form, email, referral, SMS reply)
2. REASON   — classify case type, urgency, jurisdiction; check conflicts
3. ACT      — create tasks, schedule consult, send SMS, draft engagement letter
4. EVALUATE — is intake complete? did the client respond? is anything stale?
5. LOOP     — if incomplete, follow up; if complete, hand off to attorney
```

Every action is logged with the agent's reasoning so attorneys can audit the "why" behind each decision.

---

## The Three Automation Pillars

The system is built on three tools that each own a distinct responsibility. They communicate through webhooks and a shared state store, not through fragile point-to-point integrations.

| Tool | Role | Why This One |
|---|---|---|
| **Python (FastAPI + Claude API)** | Agent brain, state machine, conflict checks, document generation | Full control over the agentic loop, prompt engineering, and data persistence. You build this with Claude Code. |
| **n8n (self-hosted)** | Workflow orchestration and event routing | Visual workflow builder, self-hosted so you own the data (critical for legal), native webhook support, and a generous free tier. Handles the "when X happens, trigger Y" logic. |
| **Twilio** | Client communication (SMS/voice) | Programmable SMS for follow-ups, appointment reminders, and document request nudges. Two-way: the client can reply and the agent processes the response. |

### Why n8n over Make or Zapier?

For a legal system, **self-hosting matters**. Client PII, case details, and conflict data should not flow through third-party SaaS workflow tools where you have limited control over data retention. n8n can run on your own server or VPS. That said, the architecture below works with Make or Zapier if you swap the webhook URLs; the Python core stays the same. If you want to prototype fast before self-hosting, Zapier is the quickest path to a working demo.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENT TOUCHPOINTS                        │
│  Web Form  |  Email Forwarding  |  Twilio SMS  |  Referral API │
└──────┬──────────────┬───────────────┬──────────────┬────────────┘
       │              │               │              │
       ▼              ▼               ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    n8n WORKFLOW ENGINE                          │
│                                                                │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Webhook  │  │ Email Trigger│  │ Twilio    │  │ Scheduled │ │
│  │ Receiver │  │ (IMAP/Gmail) │  │ Webhook   │  │ Cron Jobs │ │
│  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  └─────┬─────┘ │
│       │               │               │              │        │
│       └───────────────┴───────┬───────┴──────────────┘        │
│                               ▼                                │
│                    ┌─────────────────┐                          │
│                    │ Normalize &     │                          │
│                    │ POST to Python  │                          │
│                    └────────┬────────┘                          │
└─────────────────────────────┼──────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PYTHON AGENT CORE (FastAPI)                     │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Agent Orchestrator                       │  │
│  │  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │  │
│  │  │ Intake     │ │ Conflict │ │ Attorney │ │ Doc       │ │  │
│  │  │ Classifier │ │ Checker  │ │ Router   │ │ Generator │ │  │
│  │  └────────────┘ └──────────┘ └──────────┘ └───────────┘ │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                  │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │               State Machine (per case)                    │  │
│  │  NEW → CLASSIFYING → CONFLICT_CHECK → ROUTING →           │  │
│  │  SCHEDULING → AWAITING_DOCS → INTAKE_COMPLETE → ACTIVE    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌────────────┐  ┌────────────┐  ┌─────────────────────────┐  │
│  │ SQLite DB  │  │ Audit Log  │  │ Attorney Capacity Table │  │
│  └────────────┘  └────────────┘  └─────────────────────────┘  │
└─────────────────────────────┬──────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌───────────┐  ┌───────────┐  ┌───────────────┐
        │  Twilio   │  │  Google   │  │  Asana /      │
        │  SMS API  │  │  Calendar │  │  Task Board   │
        └───────────┘  └───────────┘  └───────────────┘
```

---

## Component Deep Dive

### 1. Python Agent Core (what you build with Claude Code)

This is the brain. It is a FastAPI application with the following modules:

#### `agent/orchestrator.py` — The Agentic Loop

```python
# Pseudocode for the core loop
class IntakeAgent:
    def __init__(self, case_id: str):
        self.case = load_case_state(case_id)
        self.tools = ToolRegistry()  # Twilio, Calendar, Asana clients

    async def run(self):
        """Observe-reason-act loop. Runs until intake is complete or blocked."""
        while self.case.status not in ("INTAKE_COMPLETE", "REJECTED", "BLOCKED"):
            observation = self.observe()
            plan = await self.reason(observation)
            results = await self.act(plan)
            self.case = self.evaluate(results)
            save_case_state(self.case)
            log_audit_trail(self.case.id, observation, plan, results)

    def observe(self) -> Observation:
        """Check current case state: what do we have, what is missing?"""
        return Observation(
            has_contact_info=bool(self.case.phone and self.case.email),
            has_case_description=bool(self.case.description),
            conflict_status=self.case.conflict_status,
            assigned_attorney=self.case.attorney_id,
            consult_scheduled=self.case.consult_datetime is not None,
            missing_documents=self.case.get_missing_docs(),
            days_since_last_contact=self.case.days_since_last_contact(),
        )

    async def reason(self, obs: Observation) -> ActionPlan:
        """Call Claude API to decide next actions given current state."""
        prompt = build_reasoning_prompt(self.case, obs)
        response = await claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            system=LEGAL_INTAKE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            tools=AVAILABLE_TOOL_DEFINITIONS,
        )
        return parse_action_plan(response)

    async def act(self, plan: ActionPlan) -> list[ActionResult]:
        """Execute each action in the plan."""
        results = []
        for action in plan.actions:
            result = await self.tools.execute(action)
            results.append(result)
        return results
```

#### `agent/classifier.py` — Case Classification

Uses Claude with a structured output prompt to extract:

- **Case type**: personal injury, family law, criminal defense, employment, real estate, immigration, etc.
- **Urgency**: emergency (restraining order, arrest), time-sensitive (statute of limitations approaching), standard
- **Jurisdiction**: state, federal, which county
- **Complexity estimate**: simple consultation, moderate, complex litigation
- **Key entities**: client name, adverse parties, incident date, location

The classifier prompt should include few-shot examples from your firm's actual case mix so it learns your specific practice areas.

#### `agent/conflict_checker.py` — Conflict of Interest Search

```python
async def check_conflicts(case: Case) -> ConflictResult:
    """
    Search existing clients and matters for conflicts.
    This is where agentic behavior matters most: the agent
    does fuzzy matching, asks Claude to evaluate edge cases,
    and flags anything ambiguous for human review.
    """
    parties = extract_all_parties(case)

    # Exact and fuzzy match against client/matter database
    matches = []
    for party in parties:
        exact = db.search_exact(party.name)
        fuzzy = db.search_fuzzy(party.name, threshold=0.82)
        matches.extend(exact + fuzzy)

    if not matches:
        return ConflictResult(status="CLEAR", matches=[])

    # Ask Claude to evaluate whether fuzzy matches are real conflicts
    evaluation = await claude_evaluate_conflicts(case, matches)
    return evaluation
```

#### `agent/router.py` — Attorney Matching

Picks the best attorney based on:
- Practice area match
- Bar admission in the relevant jurisdiction
- Current caseload and capacity
- Calendar availability (checked via Google Calendar API)
- Seniority appropriate to case complexity

#### `agent/state_machine.py` — Case Lifecycle

```
NEW
  └→ CLASSIFYING (agent runs classifier)
       └→ CONFLICT_CHECK (agent checks for conflicts)
            ├→ CONFLICT_FLAGGED (human review required)
            └→ ROUTING (agent picks attorney)
                 └→ SCHEDULING (agent books consultation)
                      └→ AWAITING_DOCS (agent requests missing docs via SMS)
                           └→ INTAKE_COMPLETE (hand off to attorney)

At any state, the agent can loop back:
  - AWAITING_DOCS can trigger follow-up SMS after 48 hours
  - SCHEDULING can retry if the client does not confirm
  - CONFLICT_FLAGGED can resolve to ROUTING after human clears it
```

### 2. n8n Workflows (event routing and orchestration)

You self-host n8n and build these workflows:

#### Workflow A: "New Intake Ingestion"
```
Trigger: Webhook (from web form) OR Email trigger OR Twilio incoming SMS
  → Extract/normalize data into a standard JSON shape
  → POST to Python API: /api/intake/new
  → Python agent runs its loop
  → Agent responds with actions to execute
  → n8n routes actions:
      - "send_sms" → Twilio node
      - "create_task" → Asana/project management API
      - "schedule_consult" → Google Calendar node
      - "send_email" → Gmail/SMTP node
```

#### Workflow B: "Stale Case Follow-Up" (Cron)
```
Trigger: Every 6 hours
  → GET from Python API: /api/cases/stale
  → For each stale case:
      → POST to Python API: /api/intake/{case_id}/follow-up
      → Agent decides what follow-up is needed
      → Route the follow-up action (usually Twilio SMS)
```

#### Workflow C: "Twilio Reply Handler"
```
Trigger: Twilio webhook (client replied to an SMS)
  → Parse the reply
  → POST to Python API: /api/intake/{case_id}/client-reply
  → Agent processes the reply:
      - If it contains missing info → update case, advance state
      - If it is a confirmation → finalize scheduling
      - If it is a question → generate response, send via Twilio
```

### 3. Twilio (client communication layer)

Twilio handles three things:

#### Outbound SMS sequences

```python
# Example: the agent decides to request documents
async def send_doc_request(case: Case, missing_docs: list[str]):
    doc_list = "\n".join(f"- {doc}" for doc in missing_docs)
    message = (
        f"Hi {case.client_first_name}, this is {FIRM_NAME}. "
        f"To prepare for your consultation on {case.consult_date}, "
        f"we need the following:\n{doc_list}\n\n"
        f"You can reply to this message or email them to {INTAKE_EMAIL}."
    )
    twilio_client.messages.create(
        body=message,
        from_=TWILIO_PHONE,
        to=case.client_phone,
        status_callback=f"{BASE_URL}/webhooks/twilio/status",
    )
```

#### Inbound SMS processing

When the client replies, Twilio POSTs to your n8n webhook, which forwards to Python. The agent uses Claude to understand the reply in context:

- "Yes Tuesday works" → confirm the consultation slot
- "I don't have the police report yet" → update missing docs, schedule another follow-up
- "Actually I want to cancel" → flag for attorney review, do not auto-cancel

#### Appointment reminders

n8n cron triggers a check 24 hours before each consultation. If the client has not confirmed, the agent sends a reminder SMS with a confirmation prompt.

---

## Data Model

```sql
-- Core tables for the Python agent

CREATE TABLE cases (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'NEW',
    -- Client info
    client_name TEXT,
    client_email TEXT,
    client_phone TEXT,
    -- Classification
    case_type TEXT,
    urgency TEXT,
    jurisdiction TEXT,
    complexity TEXT,
    -- Routing
    assigned_attorney_id TEXT,
    consult_datetime TEXT,
    -- Raw intake
    intake_source TEXT,       -- 'web_form', 'email', 'sms', 'referral'
    raw_intake_text TEXT,
    -- Tracking
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    last_client_contact_at TEXT,
    follow_up_count INTEGER DEFAULT 0
);

CREATE TABLE case_parties (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    party_name TEXT NOT NULL,
    party_role TEXT NOT NULL,   -- 'client', 'adverse', 'witness', 'co-counsel'
    normalized_name TEXT        -- lowercase, stripped, for conflict matching
);

CREATE TABLE attorneys (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    practice_areas TEXT,        -- JSON array
    bar_admissions TEXT,        -- JSON array of states
    max_active_cases INTEGER DEFAULT 25,
    current_active_cases INTEGER DEFAULT 0
);

CREATE TABLE missing_documents (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    document_type TEXT,         -- 'police_report', 'medical_records', 'contract', etc.
    requested_at TEXT,
    received_at TEXT,
    follow_up_count INTEGER DEFAULT 0
);

CREATE TABLE audit_log (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    timestamp TEXT DEFAULT (datetime('now')),
    agent_observation TEXT,     -- what the agent saw
    agent_reasoning TEXT,       -- why it chose this action
    action_taken TEXT,          -- what it did
    action_result TEXT          -- what happened
);
```

---

## Three Real Workflows (End to End)

### Workflow 1: "New PI Lead from Web Form to Scheduled Consultation"

```
1. Client fills out web intake form (name, phone, email, brief description)
2. Form POSTs to n8n webhook
3. n8n normalizes the data, POSTs to Python /api/intake/new
4. Agent loop starts:
   a. CLASSIFY: Claude reads the description, identifies "personal injury,
      car accident, standard urgency, county X"
   b. CONFLICT CHECK: searches case_parties for the adverse driver's name
      and insurance company — no conflicts found
   c. ROUTE: finds attorney Sarah Chen (PI specialist, admitted in this
      state, 18/25 active cases, has availability Thursday PM)
   d. SCHEDULE: checks Sarah's Google Calendar, finds 2:00 PM Thursday open,
      creates a calendar event with Zoom link
   e. NOTIFY: sends SMS to client via Twilio:
      "Hi Alex, thanks for contacting [Firm]. You have a consultation
       scheduled with Sarah Chen on Thursday at 2:00 PM via Zoom.
       Please reply YES to confirm."
   f. CREATE TASK: creates an Asana task in the "New Intakes" project
      assigned to Sarah with all case details in the description
5. Agent sets status to SCHEDULING, waits for client confirmation
6. Client replies "YES" via SMS
7. Twilio webhook → n8n → Python /api/intake/{id}/client-reply
8. Agent confirms, advances to AWAITING_DOCS
9. Agent sends follow-up SMS requesting medical records and police report
10. Status: AWAITING_DOCS with two items in missing_documents table
```

### Workflow 2: "Stale Follow-Up — Client Went Dark"

```
1. n8n cron runs every 6 hours
2. Calls Python /api/cases/stale — returns cases with no client contact
   in 48+ hours that are in AWAITING_DOCS or SCHEDULING status
3. For case #C-2024-0847 (3 days since last contact, 1 prior follow-up):
   a. Agent observes: still missing police report, client confirmed consult
      but has not sent docs, consult is in 2 days
   b. Agent reasons: second follow-up is appropriate, tone should be
      warm but add mild urgency since consult is soon
   c. Agent acts: sends SMS via Twilio:
      "Hi Alex, just a reminder that your consultation with Sarah Chen
       is this Thursday at 2:00 PM. If you can, please bring or send
       your police report beforehand so we can make the most of your
       time. You can photograph it and text it to this number."
   d. Agent updates: follow_up_count = 2, last_client_contact_at = now
4. If after 3 follow-ups and 7 days the client still has not responded:
   a. Agent flags the case as BLOCKED
   b. Creates an Asana task for the intake coordinator to do a manual
      phone call
   c. Stops automated follow-ups to avoid annoying the client
```

### Workflow 3: "Conflict Detected — Human in the Loop"

```
1. New intake arrives: divorce case, client is Jamie Torres
2. Agent classifies: family law, standard urgency
3. Conflict check runs:
   a. Exact match on "Torres" — finds 3 existing clients named Torres
   b. Fuzzy match on adverse party "Morgan Ellis" — finds a "Morgan L.
      Ellis" who is a current client in an employment matter
   c. Agent calls Claude to evaluate: "Morgan L. Ellis is a current
      client. The new intake names Morgan Ellis as the adverse spouse.
      These are likely the same person. This is a direct conflict."
4. Agent sets status to CONFLICT_FLAGGED
5. Agent actions:
   a. Creates HIGH PRIORITY Asana task assigned to the managing partner:
      "Potential conflict: new divorce intake (Jamie Torres) names
       adverse party Morgan Ellis, who matches current client
       Morgan L. Ellis (matter #E-2024-0312). Agent confidence: 94%.
       Please review and clear or reject."
   b. Sends internal email via n8n Gmail node to the managing partner
   c. Does NOT contact the prospective client yet
   d. Does NOT schedule a consultation
6. Managing partner reviews, confirms conflict, marks task as resolved
7. n8n detects the task status change, POSTs to Python
8. Agent sends a polite declination SMS to the prospective client:
   "Hi Jamie, thank you for contacting [Firm]. Unfortunately, we are
    unable to represent you in this matter due to a conflict of
    interest. We recommend contacting the State Bar referral service
    at [number]. We wish you the best."
9. Case status: REJECTED, full audit trail preserved
```

---

## Project Structure for Claude Code

```
legal-intake-agent/
├── pyproject.toml
├── .env.example
├── README.md
├── alembic/                     # DB migrations
│   └── versions/
├── src/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # env vars, Twilio/Calendar credentials
│   ├── models/
│   │   ├── case.py              # Pydantic models for case state
│   │   ├── attorney.py
│   │   └── audit.py
│   ├── agent/
│   │   ├── orchestrator.py      # The agentic loop
│   │   ├── classifier.py        # Case classification via Claude
│   │   ├── conflict_checker.py  # Conflict of interest detection
│   │   ├── router.py            # Attorney matching logic
│   │   ├── doc_generator.py     # Engagement letters, questionnaires
│   │   ├── follow_up.py         # Stale case follow-up logic
│   │   └── prompts/
│   │       ├── classifier.txt
│   │       ├── conflict_eval.txt
│   │       ├── reply_parser.txt
│   │       └── follow_up.txt
│   ├── integrations/
│   │   ├── twilio_client.py     # Send/receive SMS
│   │   ├── calendar_client.py   # Google Calendar API
│   │   └── asana_client.py      # Task creation (or any PM tool)
│   ├── api/
│   │   ├── intake.py            # POST /api/intake/new, etc.
│   │   ├── webhooks.py          # Twilio + n8n webhook handlers
│   │   └── internal.py          # /api/cases/stale, admin endpoints
│   └── db/
│       ├── database.py          # SQLite connection
│       ├── queries.py           # SQL queries
│       └── seed.py              # Seed attorneys, practice areas
├── n8n-workflows/
│   ├── new-intake-ingestion.json
│   ├── stale-case-followup.json
│   └── twilio-reply-handler.json
├── tests/
│   ├── test_classifier.py
│   ├── test_conflict_checker.py
│   ├── test_orchestrator.py
│   └── fixtures/
│       ├── sample_intakes.json
│       └── sample_conflicts.json
└── docs/
    ├── architecture.md          # (this document)
    ├── n8n-setup.md
    └── twilio-setup.md
```

---

## Build Order (for Claude Code sessions)

The recommended sequence, each step being roughly one Claude Code session:

**Phase 1 — Core agent without integrations**

1. Set up FastAPI project skeleton, SQLite database, Pydantic models
2. Build the classifier (Claude API call with structured output)
3. Build the conflict checker (fuzzy search + Claude evaluation)
4. Build the attorney router (simple scoring algorithm)
5. Build the orchestrator loop tying steps 2-4 together
6. Write tests using fixture data

**Phase 2 — Integrations**

7. Twilio integration (send SMS, receive webhook)
8. Google Calendar integration (check availability, create events)
9. Asana/task board integration (create tasks, update status)
10. Wire integrations into the orchestrator's action execution

**Phase 3 — n8n orchestration**

11. Set up n8n (Docker), build the intake ingestion workflow
12. Build the stale case cron workflow
13. Build the Twilio reply handler workflow
14. End-to-end testing with all three systems running

**Phase 4 — Polish**

15. Audit log viewer (simple web UI or CLI)
16. Document generation (engagement letters via templates)
17. Error handling, retry logic, rate limiting
18. Security review (PII handling, encryption at rest)

---

## Key Design Decisions to Make Early

**Synchronous vs. async agent loop**: The agent loop should be async. When a new intake arrives, the API endpoint should enqueue the case and return immediately, then the agent processes it in the background. Use Python's `asyncio` or a task queue like `arq` (lightweight, Redis-backed). Do not make the web form wait for the entire agent loop to finish.

**How much autonomy**: Start conservative. The agent should auto-classify and auto-check conflicts, but flag edge cases for human review. It should propose a consultation time but let the client confirm via SMS before finalizing. It should never auto-reject a case without a human confirming the conflict. You can increase autonomy later as you build trust in the system.

**Prompt versioning**: Store your prompts as text files (see `agent/prompts/`), not inline strings. This lets you iterate on prompts without changing code, and you can version them in git to track what changed when classification quality shifts.

**Twilio compliance**: Legal SMS has specific rules. You need proper opt-in language on the intake form. Keep messages under 160 chars when possible to avoid splitting. Include opt-out instructions ("Reply STOP to unsubscribe") in the first message. Check your state bar's rules on automated client communication.

**n8n vs. doing it all in Python**: You could skip n8n entirely and handle all the webhook routing and cron jobs in Python. The reason to use n8n is visibility. When an attorney asks "what happened with the Johnson intake?", you can pull up the n8n execution log and see every step visually. That transparency matters in a legal context where people need to trust the system.
