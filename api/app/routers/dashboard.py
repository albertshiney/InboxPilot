"""Dashboard stats: period-windowed event counts plus the live
needs-review attention list."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_db
from app.deps import workspace_id_dep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ATTENTION_LIMIT = 10


def _period_start(period: str, now: datetime) -> datetime:
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    # "30d"
    return now - timedelta(days=30)


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _count_events(db: AsyncIOMotorDatabase, workspace_id: str, type_: str, since: datetime) -> int:
    return await db.events.count_documents(
        {"workspaceId": workspace_id, "type": type_, "ts": {"$gte": since}}
    )


async def _latest_draft(db: AsyncIOMotorDatabase, thread_id: str) -> dict | None:
    drafts = (
        await db.drafts.find({"threadId": thread_id}).sort("createdAt", -1).to_list(1)
    )
    return drafts[0] if drafts else None


@router.get("/stats")
async def get_stats(
    period: str = Query(default="today"),
    workspace_id: str = Depends(workspace_id_dep),
) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    since = _period_start(period, now)

    emails_received = await _count_events(db, workspace_id, "email_received", since)
    drafts_created = await _count_events(db, workspace_id, "draft_created", since)
    auto_sent = await _count_events(db, workspace_id, "auto_sent", since)

    auto_sent_pct = round((auto_sent / emails_received) * 100) if emails_received else 0

    needs_review = await db.threads.count_documents(
        {"workspaceId": workspace_id, "status": "needs_review"}
    )

    attention_docs = (
        await db.threads.find({"workspaceId": workspace_id, "status": "needs_review"})
        .sort("lastMessageAt", 1)
        .limit(ATTENTION_LIMIT)
        .to_list(ATTENTION_LIMIT)
    )

    attention = []
    for doc in attention_docs:
        draft = await _latest_draft(db, str(doc["_id"]))
        attention.append(
            {
                "id": str(doc["_id"]),
                "customerEmail": doc.get("customerEmail"),
                "subject": doc.get("subject", ""),
                "category": draft.get("category") if draft else None,
                "confidence": draft.get("confidence") if draft else None,
                "waitingSinceIso": _iso(doc.get("lastMessageAt")),
            }
        )

    return {
        "needsReview": needs_review,
        "emailsReceived": emails_received,
        "draftsCreated": drafts_created,
        "autoSent": auto_sent,
        "autoSentPct": auto_sent_pct,
        "attention": attention,
    }
