import base64
import logging

import httpx

from src.config import settings
from src.utils.retry import retry_async

logger = logging.getLogger(__name__)

_TWILIO_BASE = "https://api.twilio.com/2010-04-01"


def _is_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_number)


def _auth_header() -> str:
    raw = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}"
    return "Basic " + base64.b64encode(raw.encode()).decode()


async def _send_sms_once(to: str, body: str) -> dict:
    url = f"{_TWILIO_BASE}/Accounts/{settings.twilio_account_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            headers={"Authorization": _auth_header()},
            data={
                "From": settings.twilio_phone_number,
                "To": to,
                "Body": body,
                "StatusCallback": f"{settings.base_url}/webhooks/twilio/status",
            },
        )
    resp.raise_for_status()
    data = resp.json()
    logger.info("SMS sent: sid=%s status=%s to=%s", data.get("sid"), data.get("status"), to)
    return {"sid": data["sid"], "status": data["status"]}


async def send_sms(to: str, body: str) -> dict:
    """Send an SMS via Twilio REST API. Falls back to console log if not configured."""
    if not _is_configured():
        logger.warning("[TWILIO STUB] to=%s\n%s", to, body)
        return {"sid": "STUB", "status": "queued"}

    try:
        return await retry_async(_send_sms_once, to, body, label="twilio.send_sms")
    except Exception as exc:
        logger.error("Twilio send_sms failed after retries: %s", exc)
        return {"sid": None, "status": "failed", "error": str(exc)}


def parse_inbound(form_data: dict) -> dict:
    """Extract the useful fields from a Twilio inbound webhook form payload."""
    return {
        "from": form_data.get("From", ""),
        "to": form_data.get("To", ""),
        "body": (form_data.get("Body") or "").strip(),
        "message_sid": form_data.get("MessageSid", ""),
        "num_media": int(form_data.get("NumMedia", 0)),
    }
