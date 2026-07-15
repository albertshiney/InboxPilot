from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_test_db: AsyncIOMotorDatabase | None = None
_client: AsyncIOMotorClient | None = None


def set_db_for_testing(db: AsyncIOMotorDatabase | None) -> None:
    """Override hook for tests: inject a mock database (or clear the override)."""
    global _test_db
    _test_db = db


def get_db() -> AsyncIOMotorDatabase:
    global _client

    if _test_db is not None:
        return _test_db

    if _client is None:
        _client = AsyncIOMotorClient(get_settings().mongodb_uri)

    return _client["inboxpilot"]
