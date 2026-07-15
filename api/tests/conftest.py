import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app import db as db_module
from app.main import app


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
