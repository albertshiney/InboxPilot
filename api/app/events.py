from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def log_event(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    type: str,
    meta: dict[str, Any] | None = None,
) -> dict:
    """Insert an audit-log style event: `{workspaceId, type, meta, ts}`."""
    doc = {
        "workspaceId": workspace_id,
        "type": type,
        "meta": meta,
        "ts": datetime.now(timezone.utc),
    }
    await db.events.insert_one(doc)
    return doc
