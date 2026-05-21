"""Google Calendar integration.

Auth: expects a service account JSON key at GOOGLE_CALENDAR_CREDENTIALS_PATH
with domain-wide delegation, OR an OAuth token file generated via
`google-auth-oauthlib`. If credentials are missing, methods fall back
gracefully so the rest of the agent pipeline still runs.

Service account setup (production):
  1. Create service account in GCP console
  2. Enable domain-wide delegation
  3. Grant the service account the Google Calendar scope in Google Workspace admin
  4. Download the JSON key and set GOOGLE_CALENDAR_CREDENTIALS_PATH

OAuth setup (development):
  1. Create OAuth app in GCP console, download credentials.json
  2. Run: python -c "from src.integrations.calendar_client import run_oauth_flow; run_oauth_flow()"
  3. Token saved to ./credentials/token.json
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
from typing import Optional

from src.config import settings
from src.utils.retry import retry_async

logger = logging.getLogger(__name__)


def _load_credentials():
    """Load Google credentials from file. Returns None if not available."""
    creds_path = Path(settings.google_calendar_credentials_path)
    token_path = creds_path.parent / "token.json"

    try:
        from google.oauth2 import service_account
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        scopes = [settings.google_calendar_scopes]

        # Try service account first
        if creds_path.exists():
            info = __import__("json").loads(creds_path.read_text())
            if info.get("type") == "service_account":
                return service_account.Credentials.from_service_account_file(
                    str(creds_path), scopes=scopes
                )

        # Fall back to OAuth token
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
            if creds and creds.valid:
                return creds
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                token_path.write_text(creds.to_json())
                return creds

    except Exception as exc:
        logger.warning("Google Calendar credentials unavailable: %s", exc)

    return None


def _build_service(credentials):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _next_business_slot(from_dt: Optional[datetime] = None) -> datetime:
    """Return the next 9 AM on a weekday from now."""
    now = from_dt or datetime.now(timezone.utc)
    candidate = now.replace(hour=settings.business_hours_start, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # Saturday=5, Sunday=6
        candidate += timedelta(days=1)
    return candidate


async def find_next_available_slot(
    attorney_email: str,
    duration_minutes: Optional[int] = None,
) -> datetime:
    """Find the next open slot on the attorney's calendar.

    Uses the FreeBusy API to check the next 7 business days, then picks
    the first slot of `duration_minutes` that falls within business hours
    and is not blocked by an existing event.

    Falls back to next-business-day-at-9am if credentials are missing.
    """
    duration = duration_minutes or settings.consultation_duration_minutes

    def _sync_find():
        creds = _load_credentials()
        if creds is None:
            return _next_business_slot()

        # If service account, impersonate the attorney
        if hasattr(creds, "with_subject"):
            creds = creds.with_subject(attorney_email)

        service = _build_service(creds)

        now = datetime.now(timezone.utc)
        search_end = now + timedelta(days=7)

        body = {
            "timeMin": now.isoformat(),
            "timeMax": search_end.isoformat(),
            "items": [{"id": attorney_email}],
        }
        result = service.freebusy().query(body=body).execute()
        busy_slots = result.get("calendars", {}).get(attorney_email, {}).get("busy", [])

        busy_ranges = [
            (
                datetime.fromisoformat(s["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(s["end"].replace("Z", "+00:00")),
            )
            for s in busy_slots
        ]

        # Walk candidate slots in business hours over the next 7 days
        candidate = _next_business_slot(now)
        for _ in range(7 * 8):  # up to 7 days × 8 slots/day
            slot_end = candidate + timedelta(minutes=duration)
            day_end = candidate.replace(hour=settings.business_hours_end, minute=0, second=0, microsecond=0)

            if slot_end > day_end:
                # Move to next day
                candidate = _next_business_slot(candidate.replace(
                    hour=settings.business_hours_end, minute=0
                ))
                continue

            # Check against busy ranges
            conflict = any(
                not (slot_end <= busy_start or candidate >= busy_end)
                for busy_start, busy_end in busy_ranges
            )
            if not conflict:
                return candidate

            candidate += timedelta(minutes=duration)

        return _next_business_slot()

    async def _do_find() -> datetime:
        return await asyncio.get_event_loop().run_in_executor(None, _sync_find)

    try:
        return await retry_async(_do_find, label="calendar.find_slot")
    except Exception as exc:
        logger.error("Calendar find_slot failed after retries: %s — using fallback", exc)
        return _next_business_slot()


async def create_event(
    attorney_email: str,
    client_name: str,
    dt: datetime,
    case_id: str,
    zoom_link: str = "",
) -> dict:
    """Create a consultation event on the attorney's calendar.

    Returns event dict with 'event_id' key. Falls back to stub if not configured.
    """
    duration = settings.consultation_duration_minutes

    def _sync_create():
        creds = _load_credentials()
        if creds is None:
            logger.warning("[CALENDAR STUB] Would create event for %s at %s", client_name, dt)
            return {"event_id": "STUB", "datetime": dt.isoformat(), "html_link": ""}

        if hasattr(creds, "with_subject"):
            creds = creds.with_subject(attorney_email)

        service = _build_service(creds)

        end_dt = dt + timedelta(minutes=duration)
        body = {
            "summary": f"Consultation — {client_name}",
            "description": (
                f"Case ID: {case_id}\n"
                f"Client: {client_name}\n"
                f"{('Zoom: ' + zoom_link) if zoom_link else ''}"
            ).strip(),
            "start": {"dateTime": dt.isoformat(), "timeZone": settings.timezone},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": settings.timezone},
            "attendees": [{"email": attorney_email}],
            "reminders": {"useDefault": True},
        }
        if zoom_link:
            body["location"] = zoom_link

        event = service.events().insert(calendarId=attorney_email, body=body).execute()
        return {
            "event_id": event["id"],
            "datetime": dt.isoformat(),
            "html_link": event.get("htmlLink", ""),
        }

    async def _do_create() -> dict:
        return await asyncio.get_event_loop().run_in_executor(None, _sync_create)

    try:
        return await retry_async(_do_create, label="calendar.create_event")
    except Exception as exc:
        logger.error("Calendar create_event failed after retries: %s — using stub", exc)
        return {"event_id": "STUB", "datetime": dt.isoformat(), "html_link": ""}


def run_oauth_flow() -> None:
    """One-time helper to generate OAuth token.json for development use."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds_path = Path(settings.google_calendar_credentials_path)
    token_path = creds_path.parent / "token.json"
    scopes = [settings.google_calendar_scopes]

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    print(f"Token saved to {token_path}")
