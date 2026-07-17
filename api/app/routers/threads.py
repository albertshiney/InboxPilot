"""Threads API: list (inbox tabs), detail (two-pane view), and the three
draft actions — approve (send), regenerate, discard.

Follows the same import pattern as `pipeline.py`: `reply_to_thread`,
`retrieve`, and `generate_draft` are imported by name into this module so
tests can monkeypatch `threads.reply_to_thread` etc. directly.
"""

import inspect
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.composio_client import reply_to_thread
from app.db import get_db
from app.deps import workspace_id_dep
from app.draft import MAX_BODY_CHARS, generate_draft
from app.events import log_event
from app.kb import retrieve
from app.pipeline import THREAD_HISTORY_CAP, USAGE_LIMIT

router = APIRouter(prefix="/threads", tags=["threads"])

PAGE_SIZE = 25
MAX_PAGE = 1000

# Per-workspace regeneration throttle: at most REGEN_MAX_PER_WINDOW
# regenerations per REGEN_WINDOW_SECONDS. Regeneration triggers an LLM call
# (real AI spend), so a client hammering the button must be bounded
# independently of the monthly usage cap. In-process sliding window keyed by
# workspace id, mirroring app/ratelimit.py. Safe under asyncio: the
# check-and-record below has no awaits between reading the deque and
# appending to it, so no two coroutines can interleave mid-decision.
REGEN_WINDOW_SECONDS = 60
REGEN_MAX_PER_WINDOW = 5
_regen_hits: dict[str, deque] = defaultdict(deque)


def reset_regen_throttle() -> None:
    """Test-only hook: clears all regeneration throttle state so tests don't
    leak hit counts into each other."""
    _regen_hits.clear()


def _check_regen_throttle(workspace_id: str) -> None:
    """Raise 429 once a workspace exceeds REGEN_MAX_PER_WINDOW regenerations
    within a trailing REGEN_WINDOW_SECONDS window; otherwise record this
    regeneration. No awaits between the check and the append."""
    now = time.monotonic()
    hits = _regen_hits[workspace_id]

    while hits and now - hits[0] > REGEN_WINDOW_SECONDS:
        hits.popleft()

    if len(hits) >= REGEN_MAX_PER_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many regenerations, slow down",
        )

    hits.append(now)


def _object_id(value: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_thread(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "workspaceId": doc["workspaceId"],
        "gmailThreadId": doc["gmailThreadId"],
        "subject": doc.get("subject", ""),
        "customerEmail": doc.get("customerEmail"),
        "customerName": doc.get("customerName"),
        "status": doc.get("status"),
        "category": doc.get("category"),
        "lastMessageAt": _iso(doc.get("lastMessageAt")),
        "snippet": doc.get("snippet", ""),
    }


def _serialize_message(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "threadId": doc["threadId"],
        "gmailMessageId": doc.get("gmailMessageId"),
        "direction": doc.get("direction"),
        "from": doc.get("from"),
        "to": doc.get("to"),
        "bodyText": doc.get("bodyText", ""),
        "bodyHtml": doc.get("bodyHtml"),
        "sentBy": doc.get("sentBy"),
        "receivedAt": _iso(doc.get("receivedAt")),
    }


def _serialize_draft(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    return {
        "id": str(doc["_id"]),
        "threadId": doc["threadId"],
        "messageId": doc.get("messageId"),
        "reply": doc.get("reply", ""),
        "confidence": doc.get("confidence"),
        "category": doc.get("category"),
        "requiresHuman": doc.get("requiresHuman"),
        "reasoning": doc.get("reasoning", ""),
        "sourcesUsed": doc.get("sourcesUsed", []),
        "status": doc.get("status"),
        "editedReply": doc.get("editedReply"),
        "createdAt": _iso(doc.get("createdAt")),
        "resolvedAt": _iso(doc.get("resolvedAt")),
        "resolvedBy": doc.get("resolvedBy"),
    }


async def _latest_draft(db: AsyncIOMotorDatabase, thread_id: str) -> dict | None:
    drafts = (
        await db.drafts.find({"threadId": thread_id}).sort("createdAt", -1).to_list(1)
    )
    return drafts[0] if drafts else None


async def _get_thread_or_404(db: AsyncIOMotorDatabase, workspace_id: str, thread_id: str) -> dict:
    thread = await db.threads.find_one(
        {"_id": _object_id(thread_id), "workspaceId": workspace_id}
    )
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    return thread


@router.get("")
async def list_threads(
    status_: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=MAX_PAGE),
    workspace_id: str = Depends(workspace_id_dep),
) -> dict:
    db = get_db()
    query: dict = {"workspaceId": workspace_id}
    if status_:
        query["status"] = status_

    total = await db.threads.count_documents(query)
    skip = (page - 1) * PAGE_SIZE
    docs = (
        await db.threads.find(query)
        .sort("lastMessageAt", -1)
        .skip(skip)
        .limit(PAGE_SIZE)
        .to_list(PAGE_SIZE)
    )

    items = []
    for doc in docs:
        row = _serialize_thread(doc)
        draft = await _latest_draft(db, str(doc["_id"]))
        row["confidence"] = draft.get("confidence") if draft else None
        row["category"] = draft.get("category") if draft else None
        items.append(row)

    return {"items": items, "total": total, "page": page}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, workspace_id: str = Depends(workspace_id_dep)) -> dict:
    db = get_db()
    thread = await _get_thread_or_404(db, workspace_id, thread_id)

    messages = (
        await db.messages.find({"threadId": thread_id}).sort("receivedAt", 1).to_list(None)
    )
    draft = await _latest_draft(db, thread_id)

    data = _serialize_thread(thread)
    data["messages"] = [_serialize_message(m) for m in messages]
    data["draft"] = _serialize_draft(draft)
    return data


class ApproveBody(BaseModel):
    # Bounded like the settings fields: the edited reply is stored in
    # `messages.bodyText` and sent as a real email, so it must not be
    # allowed to carry megabytes.
    body: str | None = Field(default=None, max_length=100_000)


@router.post("/{thread_id}/approve")
async def approve_thread(
    thread_id: str, payload: ApproveBody, workspace_id: str = Depends(workspace_id_dep)
) -> dict:
    db = get_db()
    thread = await _get_thread_or_404(db, workspace_id, thread_id)

    # Sending is a paid feature like drafting: a lapsed workspace must not
    # keep approving/sending leftover pending drafts after cancellation.
    # Same gate as regenerate/kb (active or trialing, checked in the db).
    from app.collections import workspace_filter

    workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
    subscription_status = (workspace or {}).get("subscriptionStatus") or "none"
    if subscription_status not in ("active", "trialing"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Subscription required"
        )

    draft = await db.drafts.find_one({"threadId": thread_id, "status": "pending"})
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no pending draft for this thread"
        )

    edited_body = payload.body
    has_edit = edited_body is not None
    if has_edit and not edited_body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body must not be empty",
        )
    text = edited_body if has_edit else draft.get("reply", "")

    connection = await db.connections.find_one(
        {"workspaceId": workspace_id, "provider": "gmail"}
    )
    connection_id = (connection or {}).get("composioConnectionId")

    send_result = reply_to_thread(
        connection_id,
        workspace_id,
        thread["gmailThreadId"],
        thread.get("customerEmail", ""),
        text,
    )
    if inspect.isawaitable(send_result):
        send_result = await send_result

    now = datetime.now(timezone.utc)
    await db.messages.insert_one(
        {
            "threadId": thread_id,
            "gmailMessageId": (send_result or {}).get("gmailMessageId"),
            "direction": "outbound",
            "from": (connection or {}).get("emailAddress", ""),
            "to": thread.get("customerEmail", ""),
            "bodyText": text,
            "bodyHtml": None,
            "sentBy": "human_approved",
            "receivedAt": now,
        }
    )

    new_draft_status = "edited_sent" if has_edit else "approved_sent"
    await db.drafts.update_one(
        {"_id": draft["_id"]},
        {
            "$set": {
                "status": new_draft_status,
                "editedReply": edited_body,
                "resolvedAt": now,
                "resolvedBy": "human",
            }
        },
    )
    await db.threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "sent"}})
    await log_event(
        db,
        workspace_id,
        "approved",
        meta={"draftId": str(draft["_id"]), "threadId": thread_id},
    )

    updated_draft = await db.drafts.find_one({"_id": draft["_id"]})
    return _serialize_draft(updated_draft)


class RegenerateBody(BaseModel):
    # Appended verbatim to the drafting system prompt — capped like every
    # other client-supplied prompt input (see SettingsPatchFields) so a
    # single request can't inflate per-call token spend.
    instruction: str | None = Field(default=None, max_length=2_000)


@router.post("/{thread_id}/regenerate")
async def regenerate_draft(
    thread_id: str, payload: RegenerateBody, workspace_id: str = Depends(workspace_id_dep)
) -> dict:
    db = get_db()
    thread = await _get_thread_or_404(db, workspace_id, thread_id)

    existing = await db.drafts.find_one({"threadId": thread_id, "status": "pending"})
    if thread.get("status") != "needs_review" and existing is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="thread is not awaiting review and has no pending draft",
        )

    from app.collections import workspace_filter

    workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

    subscription_status = workspace.get("subscriptionStatus") or "none"
    if subscription_status not in ("active", "trialing"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Subscription required"
        )

    # Per-workspace burst throttle (raises 429 on exceed). Checked before
    # the credit reservation below so a throttled request never consumes a
    # monthly usage credit.
    _check_regen_throttle(workspace_id)

    # Regeneration spends real AI budget, so it counts against the same
    # monthly cap as the pipeline's own drafting. Reserve the credit
    # atomically BEFORE the LLM call — the $inc applies only while the
    # counter is still under the cap (missing counter counts as 0), same
    # guard as pipeline.process_inbound, so concurrent regenerations can't
    # race past USAGE_LIMIT.
    reserve = await db.workspaces.update_one(
        {
            **workspace_filter(workspace_id),
            "$or": [
                {"usage.emailsProcessedThisMonth": {"$lt": USAGE_LIMIT}},
                {"usage.emailsProcessedThisMonth": {"$exists": False}},
            ],
        },
        {"$inc": {"usage.emailsProcessedThisMonth": 1}},
    )
    if reserve.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="monthly usage limit reached",
        )

    thread_messages = (
        await db.messages.find({"threadId": thread_id}).sort("receivedAt", 1).to_list(None)
    )
    last_customer_message = ""
    for m in reversed(thread_messages):
        if m.get("sentBy") == "customer":
            last_customer_message = m.get("bodyText", "")
            break

    query = f"{thread.get('subject', '')}\n{last_customer_message[:MAX_BODY_CHARS]}"
    kb_chunks = await retrieve(db, workspace_id, query)

    draft_result = await generate_draft(
        workspace,
        thread_messages[-THREAD_HISTORY_CAP:],
        kb_chunks,
        extra_instruction=payload.instruction,
    )

    now = datetime.now(timezone.utc)

    new_doc = {
        "threadId": thread_id,
        "messageId": existing.get("messageId") if existing else None,
        "reply": draft_result.reply,
        "confidence": draft_result.confidence,
        "category": draft_result.category,
        "requiresHuman": draft_result.requires_human,
        "reasoning": draft_result.reasoning,
        "sourcesUsed": draft_result.sources_used,
        "status": "pending",
        "editedReply": None,
        "createdAt": now,
        "resolvedAt": None,
        "resolvedBy": None,
    }

    if existing is not None:
        await db.drafts.replace_one({"_id": existing["_id"]}, new_doc)
        new_doc["_id"] = existing["_id"]
    else:
        result = await db.drafts.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id

    await log_event(
        db,
        workspace_id,
        "regenerated",
        meta={"threadId": thread_id, "instruction": payload.instruction},
    )

    return _serialize_draft(new_doc)


@router.post("/{thread_id}/discard")
async def discard_thread(thread_id: str, workspace_id: str = Depends(workspace_id_dep)) -> dict:
    db = get_db()
    thread = await _get_thread_or_404(db, workspace_id, thread_id)

    draft = await db.drafts.find_one({"threadId": thread_id, "status": "pending"})
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no pending draft for this thread"
        )

    now = datetime.now(timezone.utc)
    await db.drafts.update_one(
        {"_id": draft["_id"]},
        {"$set": {"status": "discarded", "resolvedAt": now, "resolvedBy": "human"}},
    )

    await db.threads.update_one({"_id": thread["_id"]}, {"$set": {"status": "ignored"}})
    await log_event(
        db,
        workspace_id,
        "discarded",
        meta={"threadId": thread_id, "draftId": str(draft["_id"])},
    )

    return {"ok": True}
