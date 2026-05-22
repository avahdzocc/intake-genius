"""Simple sliding-window rate limiter for the public intake endpoint.

Keyed by client IP. Stored entirely in-process (resets on restart).
For multi-worker deployments, replace with Redis-backed counting.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths to rate-limit and their per-IP limits: (max_requests, window_seconds)
_LIMITS: dict[str, tuple[int, int]] = {
    "/api/intake/new": (10, 60),
    "/webhooks/twilio/inbound": (30, 60),
    "/webhooks/twilio/status": (30, 60),
    "/webhooks/n8n/conflict-resolved": (10, 60),
}

# Prefix-based limits for groups of endpoints
_PREFIX_LIMITS: list[tuple[str, int, int]] = [
    ("/admin/", 60, 60),
    ("/api/internal/", 30, 60),
    ("/api/intake/", 20, 60),
]


# Module-level so tests can reset it without access to the middleware instance
_windows: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))


def reset_windows() -> None:
    """Clear all rate-limit counters. Call from test fixtures to ensure isolation."""
    _windows.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path in _LIMITS:
            limit, window_seconds = _LIMITS[path]
        else:
            match = next(
                ((pfx, l, w) for pfx, l, w in _PREFIX_LIMITS if path.startswith(pfx)),
                None,
            )
            if match:
                _, limit, window_seconds = match
            else:
                return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _windows[path][ip]

        # Evict timestamps outside the window
        while bucket and bucket[0] < now - window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            return JSONResponse(
                {"detail": "Too many requests. Please try again later."},
                status_code=429,
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)
        response = await call_next(request)
        return response
