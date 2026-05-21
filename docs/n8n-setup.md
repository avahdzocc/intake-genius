# n8n Setup Guide

## Overview

n8n sits between external triggers (web form, Twilio SMS) and the FastAPI
agent core. It provides visual execution logs for every workflow run, which
is critical for attorney-facing transparency — "what happened with the
Johnson intake?" has a one-click answer in n8n's execution history.

```
Twilio SMS ──────────────────────────────────────────────────────────────┐
Web Form ──→ n8n webhook ──→ normalize ──→ POST /api/intake/new          │
                                                    │                     │
                                              FastAPI Agent               │
                                                    │                     │
                          n8n cron ──→ GET /cases/stale ──→ follow-up    │
                          Twilio reply ←────────────────────────────────┘
```

---

## Option A: Docker Compose (recommended)

Runs n8n and FastAPI together in a pre-configured network.

```bash
# 1. Copy and fill in credentials
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY

# 2. Start both services
docker compose up -d

# 3. Open n8n
open http://localhost:5678
# Default login: admin / intake-genius-admin
```

Within the Docker network, n8n reaches FastAPI at `http://intake-genius:8000`.
The workflow JSONs are pre-configured for this address.

---

## Option B: n8n standalone (without Docker)

```bash
docker run -d \
  --name intake-genius-n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  -e GENERIC_TIMEZONE="America/Los_Angeles" \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=intake-genius-admin \
  n8nio/n8n
```

Then start FastAPI separately:
```bash
uvicorn src.main:app --reload
```

When running n8n standalone alongside a local FastAPI server, use
`http://host.docker.internal:8000` instead of `http://intake-genius:8000`
in all workflow HTTP Request nodes.

---

## Importing the Workflows

1. Open n8n at `http://localhost:5678`
2. Go to **Workflows** (left sidebar) → **+ New** → **Import from File**
3. Import these three files from `n8n-workflows/`:
   - `new-intake-ingestion.json`
   - `stale-case-followup.json`
   - `twilio-reply-handler.json`
4. For each workflow, click **Activate** (toggle in top-right corner)

### Adjusting the FastAPI URL

If you're not using Docker Compose, open each workflow and change
`http://intake-genius:8000` in the HTTP Request nodes to your FastAPI
address (`http://localhost:8000` or `http://host.docker.internal:8000`).

---

## Workflow A: New Intake Ingestion

**Webhook URL after activating:**
```
http://localhost:5678/webhook/intake-new
```

**To wire up the intake form:**

Option 1 — Update the form to submit to the n8n webhook instead of FastAPI:
```html
<!-- In src/static/intake-form.html, add before </script>: -->
<script>window.INTAKE_WEBHOOK_URL = 'http://localhost:5678/webhook/intake-new';</script>
```

Option 2 — For production with a public domain, set `WEBHOOK_URL` in
docker-compose.yml to your public n8n URL and point the form there.

**Testing manually:**
```bash
curl -X POST http://localhost:5678/webhook/intake-new \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Test","client_phone":"+15550001234","description":"Car accident."}'
```

---

## Workflow B: Stale Case Follow-Up (Cron)

Runs automatically every 6 hours once activated. No setup needed beyond
activation.

**Test manually in n8n:**
1. Open the workflow
2. Click **Test workflow** (top-right)
3. Check the **Executions** tab to see which cases (if any) got follow-ups

**Adjust the cron interval:**
Open the "Every 6 Hours" node → change `hoursInterval` to your preference.

---

## Workflow C: Twilio Reply Handler

**Webhook URL after activating:**
```
http://localhost:5678/webhook/twilio-reply
```

**Twilio console setup:**
1. Go to [Twilio Console](https://console.twilio.com) → Phone Numbers → Manage → Active Numbers
2. Click your intake phone number
3. Under **Messaging** → "A Message Comes In":
   - Set to **Webhook**
   - URL: `https://your-public-n8n-domain.com/webhook/twilio-reply`
   - HTTP Method: **POST**
4. Save

> **Local dev note:** Twilio cannot reach `localhost`. Use
> [ngrok](https://ngrok.com) to expose n8n: `ngrok http 5678`.
> Your Twilio webhook URL becomes `https://xxxx.ngrok.io/webhook/twilio-reply`.

---

## Execution Logs

Every workflow run is visible in n8n → **Executions** (left sidebar).
Each execution shows:
- Input/output data at each node
- Timing
- Errors (if any)

This is the primary debugging tool for "why didn't the Johnson intake send an SMS?"

---

## Production Checklist

- [ ] Set `WEBHOOK_URL` to your public n8n domain in docker-compose.yml
- [ ] Use a strong `N8N_BASIC_AUTH_PASSWORD` (not the default)
- [ ] Enable HTTPS — put n8n behind nginx or Caddy with SSL
- [ ] Update Twilio webhook URL to the public n8n URL
- [ ] Update the intake form action to the public n8n webhook URL
- [ ] Set `saveDataSuccessExecution: none` on the stale-case workflow to avoid
      storing large execution logs (the data is already in FastAPI's audit_log)
- [ ] Set up n8n's built-in error email notifications for failed executions

---

## Troubleshooting

**"Cannot connect to intake-genius:8000" in n8n**
→ FastAPI isn't running or isn't on the Docker network. Run `docker compose ps`
and check that the `intake-genius` service is healthy.

**Workflow shows "Webhook URL not registered"**
→ The workflow isn't activated. Click the toggle in the top-right of the workflow editor.

**Twilio inbound SMS not triggering the workflow**
→ Check that the Twilio webhook URL points to your n8n host (not localhost)
and that the workflow is active.

**"Execution failed" on the stale-case cron**
→ Usually means FastAPI is down or returned an error. Check FastAPI logs:
`docker compose logs intake-genius`.
