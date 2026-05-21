# Security Guide

## Overview

Intake Genius handles personal injury details, family matters, and other
sensitive legal information. This document describes the security controls
in place and the hardening steps required before a production deployment.

---

## Controls Already Implemented

### Transport & Headers

| Header | Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Prevents MIME sniffing |
| `X-Frame-Options` | `DENY` | Blocks clickjacking via iframes |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS filter (defence-in-depth) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer leakage |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Blocks sensor APIs |

Add `Strict-Transport-Security` (HSTS) at the reverse-proxy layer, not here,
so it only fires over real TLS.

### Rate Limiting

`POST /api/intake/new` is limited to **10 requests per 60 seconds** per client
IP. This uses an in-process sliding window — for multi-worker deployments,
replace `_windows` in `src/middleware/rate_limit.py` with a Redis-backed
counter.

### CORS

`allow_origins=["*"]` has been replaced with explicit origins. Set the
`ALLOWED_ORIGINS` environment variable to a comma-separated list:

```
ALLOWED_ORIGINS=https://yourfirm.com,https://intake.yourfirm.com
```

### PII in Logs

`src/utils/pii.py` provides `redact(text)` which masks phone numbers and
email addresses before they reach log lines. Apply it to any user-supplied
string passed to `logger.*()` calls.

```python
from src.utils.pii import redact
logger.info("Processing intake for %s", redact(case.client_phone))
```

---

## Production Hardening Checklist

### Infrastructure

- [ ] Deploy behind nginx or Caddy with TLS (Let's Encrypt)
- [ ] Set `HSTS: max-age=31536000; includeSubDomains` at the proxy
- [ ] Use a non-root user inside the Docker container (already: `python:3.12-slim` default)
- [ ] Mount the database volume as read-write only from the app container

### Authentication

- [ ] Set a strong `INTERNAL_API_KEY` and validate it on `/api/internal/*`
  endpoints before exposing them to the network.

  Add to `src/api/internal.py`:
  ```python
  from fastapi import Header, HTTPException
  from src.config import settings

  async def verify_api_key(x_api_key: str = Header(...)):
      if settings.internal_api_key and x_api_key != settings.internal_api_key:
          raise HTTPException(status_code=403, detail="Forbidden")
  ```
  Then add `dependencies=[Depends(verify_api_key)]` to each internal route.

- [ ] Put the admin dashboard (`/admin`) behind HTTP Basic Auth or SSO —
  it exposes client names and case details without authentication in the
  current implementation.

- [ ] Rotate the n8n basic-auth password from the default (`intake-genius-admin`)

### Data

- [ ] Enable SQLite WAL mode for safe concurrent access:
  ```python
  await db.execute("PRAGMA journal_mode=WAL")
  ```
- [ ] Back up the SQLite file (or migrate to PostgreSQL) with point-in-time
  recovery before going live.
- [ ] Encrypt the database volume at rest using your cloud provider's
  volume encryption (e.g., AWS EBS encryption, GCP Persistent Disk).
- [ ] Do not log raw intake text (`raw_intake_text`) at INFO level —
  it can contain sensitive facts about the legal matter.

### Secrets

- [ ] Store `ANTHROPIC_API_KEY`, `TWILIO_AUTH_TOKEN`, and other credentials
  in a secret manager (AWS Secrets Manager, GCP Secret Manager, or
  Doppler) rather than plain `.env` files on disk.
- [ ] Rotate all API keys before going live.
- [ ] Never commit `.env` to version control (already in `.gitignore`).

### SMS Compliance (TCPA)

- [ ] Ensure the intake form obtains explicit written consent for SMS
  before storing a client phone number. The current form includes
  opt-in text — confirm your legal team has approved the language.
- [ ] Honor `STOP` replies: when a client texts STOP, set a
  `sms_opted_out` flag on the case and never send further SMS to that
  number. Wire this into `handle_client_confirmed` and `handle_follow_up`.
- [ ] Include `Reply STOP to unsubscribe` in every outbound SMS (already
  present in the document-request message).

### Third-party Security

| Service | Action |
|---|---|
| Twilio | Enable webhook signature validation (`X-Twilio-Signature`) in `src/api/webhooks.py` |
| Google Calendar | Prefer service account + domain-wide delegation over OAuth tokens in prod |
| Asana | Use a workspace-scoped PAT, not a user PAT |
| n8n | Enable HTTPS + strong auth; do not expose n8n's port publicly |

---

## Twilio Webhook Signature Validation

Twilio signs every inbound webhook. Validate it to prevent spoofed requests:

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(settings.twilio_auth_token)

@router.post("/webhooks/twilio/inbound")
async def twilio_inbound(request: Request):
    url = str(request.url)
    form = dict(await request.form())
    sig = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(url, form, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    # … rest of handler
```

This requires the Twilio SDK (`twilio` package, already a dependency).

---

## Incident Response

If a data incident occurs:

1. Rotate all API keys immediately
2. Check `audit_log` for any unexpected agent actions
3. Review `uvicorn` / Docker logs for abnormal request patterns
4. Notify affected clients per your jurisdiction's breach notification laws
5. Contact Twilio and Google if you suspect third-party credential compromise
