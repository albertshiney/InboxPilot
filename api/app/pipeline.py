"""Drafting pipeline orchestration: classify -> retrieve -> draft ->
guardrails/autopilot -> send-or-review.

`process_inbound` is invoked as a `BackgroundTasks` job (from the Composio
webhook route and the fallback-sync scheduler job), so it must open its own
db handle via `get_db()` (never accept one as a parameter — there is no
request-scoped connection to reuse from a background task) and it must
never raise: a bug here must degrade to "thread needs review", never to a
silently dropped email. That contract is enforced by wrapping the entire
body in one try/except that logs a `pipeline_error` event and marks the
thread `needs_review` on any exception.

Names imported directly (rather than via `import app.classify` etc.) so
tests can monkeypatch `pipeline.classify_email`, `pipeline.retrieve`,
`pipeline.generate_draft`, `pipeline.reply_to_thread` without reaching into
other modules — the same pattern `classify.py` uses for `get_anthropic`.
"""

import inspect
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from . import guardrails
from .classify import classify_email
from .collections import workspace_filter
from .composio_client import reply_to_thread
from .draft import generate_draft
from .events import log_event
from .kb import retrieve

USAGE_LIMIT = 500
THREAD_HISTORY_CAP = 20
"""Long-running threads must not pass unbounded history into the drafting
prompt — cap to the most recent messages (thread_messages is sorted oldest
first, so this keeps the tail)."""
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def _object_id(value: str):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


async def process_inbound(workspace_id: str, message_id: str) -> None:
    """Run the full drafting pipeline for one freshly-ingested inbound
    message. Always returns `None`; never raises."""
    from .db import get_db

    db = get_db()
    thread = None

    try:
        workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
        message = await db.messages.find_one({"_id": _object_id(message_id)})
        if workspace is None or message is None:
            return

        thread = await db.threads.find_one({"_id": _object_id(message["threadId"])})
        if thread is None:
            return

        settings = workspace.get("settings") or {}
        usage = workspace.get("usage") or {}
        subscription_status = workspace.get("subscriptionStatus") or "none"

        # Email processing requires an active or trialing subscription (card
        # collected at onboarding, task 15) — a workspace that has never
        # subscribed, or whose subscription lapsed, must not consume AI spend.
        # Emails still land (ingestion already happened above this point);
        # they just wait in needs_review until the workspace subscribes.
        if subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
            await log_event(
                db,
                workspace_id,
                "subscription_required",
                meta={
                    "threadId": str(thread["_id"]),
                    "messageId": message_id,
                    "subscriptionStatus": subscription_status,
                },
            )
            await db.threads.update_one(
                {"_id": thread["_id"]}, {"$set": {"status": "needs_review"}}
            )
            return

        if usage.get("emailsProcessedThisMonth", 0) >= USAGE_LIMIT:
            await log_event(
                db,
                workspace_id,
                "usage_limit_hit",
                meta={"threadId": str(thread["_id"]), "messageId": message_id},
            )
            await db.threads.update_one(
                {"_id": thread["_id"]}, {"$set": {"status": "needs_review"}}
            )
            return

        category = await classify_email(thread.get("subject", ""), message.get("bodyText", ""))
        if category != "support_request":
            await db.threads.update_one(
                {"_id": thread["_id"]},
                {"$set": {"status": "ignored", "category": category}},
            )
            await log_event(
                db,
                workspace_id,
                "thread_ignored",
                meta={"threadId": str(thread["_id"]), "category": category},
            )
            return

        query = f"{thread.get('subject', '')}\n{message.get('bodyText', '')}"
        kb_chunks = await retrieve(db, workspace_id, query)

        thread_messages = await (
            db.messages.find({"threadId": str(thread["_id"])}).sort("receivedAt", 1).to_list(None)
        )

        draft_result = await generate_draft(
            workspace, thread_messages[-THREAD_HISTORY_CAP:], kb_chunks
        )

        now = datetime.now(timezone.utc)
        draft_doc = {
            "threadId": str(thread["_id"]),
            "messageId": message_id,
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
        insert_result = await db.drafts.insert_one(draft_doc)
        draft_id = insert_result.inserted_id

        await db.workspaces.update_one(
            workspace_filter(workspace_id),
            {"$inc": {"usage.emailsProcessedThisMonth": 1}},
        )
        await log_event(
            db,
            workspace_id,
            "draft_created",
            meta={
                "draftId": str(draft_id),
                "threadId": str(thread["_id"]),
                "confidence": draft_result.confidence,
                "category": draft_result.category,
            },
        )

        prior_ai_reply_in_thread = any(m.get("sentBy") == "ai_auto" for m in thread_messages)
        blocked_senders = settings.get("blockedSenders", [])

        violations = guardrails.check(
            draft_result,
            settings=settings,
            chunks_found=bool(kb_chunks),
            inbound_text=message.get("bodyText", ""),
            prior_ai_reply_in_thread=prior_ai_reply_in_thread,
            sender=message.get("from", ""),
            blocked_senders=blocked_senders,
        )

        autopilot = settings.get("autopilot", False)
        confidence_threshold = settings.get("confidenceThreshold", 85)

        if autopilot and draft_result.confidence >= confidence_threshold and not violations:
            connection = await db.connections.find_one(
                {"workspaceId": workspace_id, "provider": "gmail"}
            )
            connection_id = (connection or {}).get("composioConnectionId")

            send_result = reply_to_thread(connection_id, thread["gmailThreadId"], draft_result.reply)
            if inspect.isawaitable(send_result):
                send_result = await send_result

            await db.messages.insert_one(
                {
                    "threadId": str(thread["_id"]),
                    "gmailMessageId": (send_result or {}).get("gmailMessageId"),
                    "direction": "outbound",
                    "from": (connection or {}).get("emailAddress", ""),
                    "to": message.get("from", ""),
                    "bodyText": draft_result.reply,
                    "bodyHtml": None,
                    "sentBy": "ai_auto",
                    "receivedAt": now,
                }
            )

            await db.drafts.update_one(
                {"_id": draft_id},
                {"$set": {"status": "auto_sent", "resolvedAt": now, "resolvedBy": "ai_auto"}},
            )
            await db.threads.update_one(
                {"_id": thread["_id"]}, {"$set": {"status": "auto_sent"}}
            )
            await log_event(
                db,
                workspace_id,
                "auto_sent",
                meta={"draftId": str(draft_id), "threadId": str(thread["_id"])},
            )
        else:
            await db.threads.update_one(
                {"_id": thread["_id"]}, {"$set": {"status": "needs_review"}}
            )

    except Exception as exc:  # noqa: BLE001 - a pipeline bug must never lose an email
        try:
            await log_event(
                db,
                workspace_id,
                "pipeline_error",
                meta={"error": str(exc), "messageId": message_id},
            )
        except Exception:
            pass

        if thread is not None:
            try:
                await db.threads.update_one(
                    {"_id": thread["_id"]}, {"$set": {"status": "needs_review"}}
                )
            except Exception:
                pass
