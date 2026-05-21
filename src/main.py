from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.db.database import init_db
from src.api.intake import router as intake_router
from src.api.webhooks import router as webhooks_router
from src.api.internal import router as internal_router
from src.api.admin import router as admin_router
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.middleware.rate_limit import RateLimitMiddleware

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Intake Genius", version="0.4.0", lifespan=lifespan)

# Security headers on every response
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting on public endpoints
app.add_middleware(RateLimitMiddleware)

# CORS: allow the intake form origin and localhost in dev; tighten via env in prod
_cors_origins = (
    settings.allowed_origins.split(",")
    if getattr(settings, "allowed_origins", None)
    else ["http://localhost:5678", "http://localhost:3000", "http://localhost:8000"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(intake_router)
app.include_router(webhooks_router)
app.include_router(internal_router)
app.include_router(admin_router)

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root():
    form = _STATIC_DIR / "intake-form.html"
    if form.exists():
        return FileResponse(str(form))
    return {"name": "Intake Genius", "status": "running"}


@app.get("/form", include_in_schema=False)
async def intake_form():
    return FileResponse(str(_STATIC_DIR / "intake-form.html"))
