import os
import sys
import tempfile
import pytest

# Ensure the project root is on the path so `src` imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Provide stub env vars so config loads without a real .env during tests
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+10000000000")
os.environ.setdefault("FIRM_NAME", "Test Firm")
os.environ.setdefault("INTAKE_EMAIL", "test@testfirm.com")
os.environ.setdefault("MANAGING_PARTNER_EMAIL", "partner@testfirm.com")
os.environ.setdefault("ASANA_ACCESS_TOKEN", "")
os.environ.setdefault("ASANA_WORKSPACE_GID", "")
os.environ.setdefault("ASANA_PROJECT_GID", "")


@pytest.fixture(autouse=True)
async def tmp_db(tmp_path):
    """Point the DB at a fresh temp file for each test, then init schema."""
    import src.db.database as db_module
    import src.db.queries as queries_module

    db_file = str(tmp_path / "test.db")
    db_module._DB_PATH = db_file

    # Patch DATABASE_URL on settings too
    from src.config import settings
    settings.database_url = db_file

    await db_module.init_db()
    yield

    # Reset rate-limit windows so burst tests don't affect subsequent tests
    from src.middleware.rate_limit import reset_windows
    reset_windows()
