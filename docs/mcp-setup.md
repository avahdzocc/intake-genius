# MCP Server Setup Guide

## Overview

The Intake Genius MCP server exposes the legal intake pipeline as conversational
tools for Claude Desktop and Claude Code. Attorneys can ask natural-language
questions and trigger actions without leaving their chat interface.

**What you can do through Claude:**

| Ask Claude… | MCP tool called |
|---|---|
| "What's the status of the Garcia intake?" | `get_case` |
| "Show me all cases awaiting documents" | `list_cases` |
| "Find the intake for Maria Santos" | `search_cases` |
| "How many new intakes this week?" | `get_pipeline_stats` |
| "Walk me through what happened with the Johnson case" | `get_audit_trail` |
| "Submit an intake — walk-in, John Smith, car accident…" | `submit_intake` |
| "Follow up with the Chen family" | `trigger_follow_up` |
| "The conflict check cleared — resume the Martinez intake" | `resolve_conflict` |
| "What docs are still outstanding for case 3A4B?" | `get_missing_documents` |
| "The Garcias just dropped off their police report" | `mark_document_received` |
| "Show me the engagement letter for the Smith case" | `get_engagement_letter` |
| "Which cases need follow-up today?" | `list_stale_cases` |

---

## Prerequisites

- Intake Genius installed and `.env` configured (see main README)
- Python virtualenv at `intake-genius/.venv/`
- Claude Desktop installed ([download](https://claude.ai/download))

---

## Option A: Claude Desktop (stdio — recommended)

This runs the MCP server as a subprocess of Claude Desktop. No network port needed.

### 1. Find the config file

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

### 2. Add the server

```json
{
  "mcpServers": {
    "intake-genius": {
      "command": "/absolute/path/to/intake-genius/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/absolute/path/to/intake-genius"
    }
  }
}
```

Replace `/absolute/path/to/intake-genius` with the actual path on your machine.

**Quick way to get the paths on macOS:**

```bash
cd /Users/avaocchialini/intake-genius
echo "Python:  $(pwd)/.venv/bin/python"
echo "CWD:     $(pwd)"
```

### 3. Restart Claude Desktop

Quit and relaunch. You should see **Intake Genius** appear in the tools panel
(⚙️ icon in the chat input area).

### 4. Test it

Open a new conversation and type:

> "Use Intake Genius to show me the pipeline stats."

Claude will call `get_pipeline_stats` and report the results.

---

## Option B: SSE Transport (network / browser MCP clients)

Run the server over SSE so any MCP client on the network can connect.

```bash
cd /path/to/intake-genius
./scripts/mcp-server.sh --sse 8001
```

Or directly:

```bash
.venv/bin/fastmcp run src/mcp_server.py --transport sse --port 8001
```

The SSE endpoint is at `http://localhost:8001/sse`.

> **Note:** Secure SSE behind a reverse proxy with TLS before exposing it
> to a non-local network.

---

## Option C: Claude Code (in-session)

If you're working in Claude Code inside the `intake-genius` directory, the MCP
server can be registered in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "intake-genius": {
      "command": ".venv/bin/python",
      "args": ["-m", "src.mcp_server"]
    }
  }
}
```

---

## Tool Reference

### Case Lookup

#### `get_case(case_id)`
Full case detail including attorney name and outstanding document count.

#### `list_cases(status?, limit?)`
List cases, newest first. `status` must be one of: `NEW`, `CLASSIFYING`,
`CONFLICT_CHECK`, `ROUTING`, `SCHEDULING`, `AWAITING_DOCS`, `INTAKE_COMPLETE`,
`CONFLICT_FLAGGED`, `REJECTED`, `BLOCKED`.

#### `search_cases(query, limit?)`
Full-text search across client name, phone, and case type.

#### `get_pipeline_stats()`
Total cases, by-status breakdown, stale count, and 24h agent activity.

#### `get_audit_trail(case_id)`
Every agent decision recorded for a case, in order.

---

### Actions

#### `submit_intake(client_name, description, client_phone?, client_email?, intake_source?)`
Creates a new case and starts the agent pipeline. Returns `case_id`.

#### `trigger_follow_up(case_id)`
Sends a follow-up SMS to a stale case via Twilio.

#### `resolve_conflict(case_id, cleared, reason?)`
Clears (`cleared=true`) or rejects (`cleared=false`) a conflict-flagged case.
When cleared, the pipeline resumes. When rejected, the client receives a
polite declination SMS.

#### `update_case_status(case_id, new_status, note?)`
Manual status override. Logged in the audit trail. Use sparingly.

---

### Documents

#### `get_missing_documents(case_id)`
Outstanding and received documents with friendly names.

#### `mark_document_received(case_id, document_type)`
Mark one document as received. Automatically advances the case to
`INTAKE_COMPLETE` when all documents are in.

---

### Engagement Letter

#### `get_engagement_letter(case_id, regenerate?)`
Fetch the stored letter or generate a new one with Claude. Set
`regenerate=true` to force a fresh draft (e.g., after the consultation time
changes).

---

### Stale Cases

#### `list_stale_cases(hours?)`
Cases that haven't had client contact in `hours` hours (default 48).
Includes `hours_since_contact` for easy triage.

---

## Example Conversations

**Morning triage:**
> "Show me all stale cases and then trigger follow-ups for any that are in AWAITING_DOCS."

**New walk-in:**
> "Submit an intake for Carlos Mendez, phone +1 213 555 0192. He was injured in a slip-and-fall at a grocery store in Los Angeles last Tuesday and is seeking representation."

**Conflict resolution:**
> "The managing partner reviewed the Torres intake. There's no actual conflict — please clear it and resume the pipeline."

**Document tracking:**
> "What docs are still outstanding for the Chen case? … OK, they just emailed their tax returns. Mark that received."

**Engagement letter:**
> "Generate a fresh engagement letter for the Martinez case — the consultation time changed to next Thursday at 2pm."

---

## Troubleshooting

**"Intake Genius" doesn't appear in Claude Desktop**
→ Check that the `cwd` and `command` paths in `claude_desktop_config.json`
are absolute and correct. The Python binary must be the one in the virtualenv.
Restart Claude Desktop after any config change.

**"No module named src.mcp_server"**
→ The `cwd` in the config must be the project root (containing the `src/`
directory). Double-check the path.

**Tool calls return database errors**
→ The MCP server uses the same `DATABASE_URL` as the FastAPI app. Make sure
`.env` exists in the project root and `DATABASE_URL` points to the correct
SQLite file (or that the DB has been initialised with `uvicorn src.main:app`
at least once).

**"ANTHROPIC_API_KEY not set"**
→ The `.env` file must be in the project root (`intake-genius/.env`).
The server loads it automatically via `python-dotenv`.
