"""Index bootstrap and small collection-access helpers.

Workspace `_id`s originate as NextAuth-inserted Mongo ObjectIds, but every
request only ever carries the workspace id as a plain string (the
`X-Workspace-Id` header). Every collection *other* than `workspaces` stores
`workspaceId` as that plain string, so no translation is needed there. The
`workspaces` collection itself, however, must be queried by matching either
representation of `_id` — as an `ObjectId` when the string parses as one,
else as the literal string (this also covers tests, which use opaque ids
like "ws1").
"""

from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

EVENTS_TTL = timedelta(days=180)
"""Dashboard stats only ever look back 30 days; 180 keeps a comfortable
audit window while stopping the events log from growing forever."""

STRIPE_EVENTS_TTL = timedelta(days=30)
"""Stripe webhook idempotency markers (see routers/webhooks_stripe.py)
otherwise grow one doc per event forever. Stripe never redelivers events
older than a few days, so 30 days of replay protection is ample."""


def workspace_filter(workspace_id: str) -> dict:
    """Build a `{"_id": ...}` filter for the `workspaces` collection that
    matches a workspace id regardless of whether it's stored as an
    `ObjectId` or a plain string."""
    try:
        return {"_id": ObjectId(workspace_id)}
    except (InvalidId, TypeError):
        return {"_id": workspace_id}


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all indexes required by the data layer. Safe to call on every
    startup — `create_index` is idempotent."""
    await db.messages.create_index([("workspaceId", 1), ("gmailMessageId", 1)], unique=True)
    await db.threads.create_index([("workspaceId", 1), ("status", 1), ("lastMessageAt", 1)])
    await db.threads.create_index([("workspaceId", 1), ("gmailThreadId", 1)], unique=True)
    await db.kb_chunks.create_index([("workspaceId", 1), ("documentId", 1)])
    await db.events.create_index([("workspaceId", 1), ("ts", 1)])
    await db.connections.create_index("workspaceId")

    # Hot read paths that were previously full collection scans: thread
    # detail loads messages by threadId, the inbox list and dashboard load
    # the latest draft per thread, and the KB routes list/count documents
    # per workspace.
    await db.messages.create_index([("threadId", 1), ("receivedAt", 1)])
    await db.drafts.create_index([("threadId", 1), ("createdAt", -1)])
    await db.kb_documents.create_index([("workspaceId", 1), ("createdAt", -1)])

    # TTLs on append-only log collections so they don't grow unboundedly,
    # and on the per-day ingest counters (expiresAt is stamped at insert).
    await db.events.create_index(
        "ts", expireAfterSeconds=int(EVENTS_TTL.total_seconds())
    )
    await db.stripe_events.create_index(
        "at", expireAfterSeconds=int(STRIPE_EVENTS_TTL.total_seconds())
    )
    await db.ingest_counters.create_index("expiresAt", expireAfterSeconds=0)

    # Auth/ownership uniqueness (H6): these collections are populated by the
    # NextAuth Mongo adapter and the app's workspace bootstrap, neither of
    # which creates these indexes — the API owns them at startup.
    await db.users.create_index("email", unique=True)
    await db.sessions.create_index("sessionToken", unique=True)
    await db.accounts.create_index(
        [("provider", 1), ("providerAccountId", 1)], unique=True
    )
    await db.workspaces.create_index(
        "ownerId",
        unique=True,
        partialFilterExpression={"ownerId": {"$type": "string"}},
    )
