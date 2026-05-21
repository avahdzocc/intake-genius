"""PII redaction helpers for safe logging.

Masks phone numbers and email addresses so they never appear in plain-text
log lines. Use `redact(text)` before passing untrusted strings to logger.
"""
import re

_PHONE_RE = re.compile(
    r"""
    (?<!\d)                 # not preceded by a digit
    (\+?1[-.\s]?)?          # optional country code
    \(?(\d{3})\)?           # area code
    [-.\s]?
    (\d{3})
    [-.\s]?
    (\d{4})
    (?!\d)                  # not followed by a digit
    """,
    re.VERBOSE,
)

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)


def redact(text: str) -> str:
    """Return `text` with phone numbers and email addresses masked."""
    text = _PHONE_RE.sub(lambda m: m.group(0)[:3] + "***-****", text)
    text = _EMAIL_RE.sub(lambda m: m.group(0).split("@")[0][:2] + "***@***", text)
    return text


def redact_phone(phone: str) -> str:
    """Mask all but the last 4 digits of a phone number."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) >= 4:
        return "***-" + digits[-4:]
    return "****"
