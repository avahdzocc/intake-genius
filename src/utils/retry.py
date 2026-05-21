"""Async retry with exponential backoff for transient external-API failures."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Errors that are worth retrying (transient network / server issues)
_RETRYABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)


def _is_retryable_status(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


async def retry_async(
    fn: Callable[..., Awaitable[T]],
    *args,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    label: str = "",
    **kwargs,
) -> T:
    """Call `fn(*args, **kwargs)` up to `max_attempts` times.

    Backs off exponentially: 1 s, 2 s, 4 s … between attempts.
    Retries on connection errors, timeouts, and 429/5xx HTTP status errors.
    Raises the last exception if all attempts fail.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except BaseException as exc:
            if not (isinstance(exc, _RETRYABLE) or _is_retryable_status(exc)):
                raise
            last_exc = exc
            if attempt < max_attempts:
                wait = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "retry %s attempt %d/%d failed (%s), retrying in %.1fs",
                    label or fn.__name__,
                    attempt,
                    max_attempts,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "retry %s exhausted %d attempts, giving up: %s",
                    label or fn.__name__,
                    max_attempts,
                    exc,
                )
    raise last_exc  # type: ignore[misc]
