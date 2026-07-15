import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app import db as db_module
from app import ratelimit
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # Webhook routes carry a process-global sliding-window rate limiter
    # (app/ratelimit.py); without resetting it between tests, the many
    # webhook tests in the full suite would accumulate hits against the
    # same test-client IP and eventually 429 each other.
    ratelimit.reset_rate_limiter()
    yield
    ratelimit.reset_rate_limiter()


@pytest.fixture()
def mock_db():
    client = AsyncMongoMockClient()
    database = client["inboxpilot_test"]
    db_module.set_db_for_testing(database)
    yield database
    db_module.set_db_for_testing(None)


@pytest.fixture()
async def client(mock_db, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "test-internal-key")
    monkeypatch.setenv("ENABLE_SCHEDULER", "0")
    from app.config import get_settings
    from app import llm

    get_settings.cache_clear()
    llm.reset_clients()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


HEADERS = {"X-Internal-Key": "test-internal-key", "X-Workspace-Id": "ws1"}
