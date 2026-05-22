"""Authentication middleware for internal and admin endpoints.

Requires a valid Bearer token matching INTERNAL_API_KEY for protected routes.
The health endpoint and the public intake form remain open.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings

_PUBLIC_PATHS = frozenset({
    "/",
    "/form",
    "/api/intake/new",
    "/api/internal/health",
    "/docs",
    "/openapi.json",
})

_PUBLIC_PREFIXES = (
    "/static/",
    "/webhooks/",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in _PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.internal_api_key:
            return await call_next(request)

        path = request.url.path.rstrip("/") or "/"

        if _is_public(path):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if auth == f"Bearer {settings.internal_api_key}":
            return await call_next(request)

        return JSONResponse(
            {"detail": "Authentication required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
