# Google Calendar Setup Guide

## Overview

The calendar integration finds attorney availability and creates consultation
events. It supports two credential types:

| Method | Best for | Setup complexity |
|---|---|---|
| Service account + domain-wide delegation | Production (G Suite / Google Workspace) | Medium |
| OAuth 2.0 token | Development / single-user | Low |

If neither is configured, the agent falls back to proposing the next
business-day morning slot (no event is created, but SMS still goes out).

---

## Option A: Service Account (Production)

This lets the agent impersonate attorney email addresses to read and write
their calendars — no individual login required.

### 1. Create a service account

1. Go to [Google Cloud Console](https://console.cloud.google.com) → your project
2. **IAM & Admin** → **Service Accounts** → **Create Service Account**
3. Name it `intake-genius-calendar`
4. No roles needed at the project level — skip
5. Click the service account → **Keys** → **Add Key** → **JSON**
6. Download the JSON key file

### 2. Enable domain-wide delegation

1. In the service account details, click **Show Domain-Wide Delegation**
2. Check **Enable Google Workspace Domain-Wide Delegation**
3. Note the **Client ID** shown

### 3. Grant calendar access in Google Workspace Admin

1. Go to [admin.google.com](https://admin.google.com) → **Security** → **API Controls** →
   **Domain-wide Delegation** → **Add New**
2. Client ID: paste from step 2
3. OAuth scopes: `https://www.googleapis.com/auth/calendar`
4. **Authorize**

### 4. Configure the integration

```bash
mkdir -p credentials
# Move your downloaded key file:
mv ~/Downloads/intake-genius-calendar-*.json credentials/google_calendar.json
```

In `.env`:
```
GOOGLE_CALENDAR_CREDENTIALS_PATH=./credentials/google_calendar.json
```

The agent will now impersonate each attorney's email to check their calendar.
Make sure the attorney email addresses in the `attorneys` database table match
their Google Workspace accounts.

---

## Option B: OAuth 2.0 Token (Development)

Simpler but requires logging in manually and refreshing tokens.

### 1. Create OAuth credentials

1. [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services** →
   **Credentials** → **Create Credentials** → **OAuth client ID**
2. Application type: **Desktop app**
3. Download the JSON as `credentials/google_calendar.json`

### 2. Enable the Calendar API

In Cloud Console → **APIs & Services** → **Library** → search "Google Calendar API" → Enable.

### 3. Generate the token

```bash
cd /path/to/intake-genius
source .venv/bin/activate
python -c "from src.integrations.calendar_client import run_oauth_flow; run_oauth_flow()"
```

A browser window opens. Log in as the attorney and grant access. The token is
saved to `credentials/token.json`.

> **Note:** OAuth tokens expire. The integration auto-refreshes them, but if
> the refresh token expires, you'll need to re-run `run_oauth_flow()`. For
> production, use Service Account instead.

---

## Testing the Integration

```python
# Quick test in a Python shell (with your .env loaded):
import asyncio
from src.integrations.calendar_client import find_next_available_slot, create_event
from datetime import datetime

async def test():
    slot = await find_next_available_slot("attorney@yourfirm.com")
    print(f"Next available slot: {slot}")
    event = await create_event("attorney@yourfirm.com", "Test Client", slot, "test-case-id")
    print(f"Event created: {event}")

asyncio.run(test())
```

---

## Fallback Behavior

If credentials are missing or the API call fails, the agent:
1. Logs a warning (check `uvicorn` logs)
2. Uses the next business-day 9 AM slot as the proposed time
3. Still sends the SMS and creates the Asana task
4. Sets `calendar_event_id = "STUB"` in the database

The consultation can be manually scheduled and the case can still progress.
