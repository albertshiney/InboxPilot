"""Single ingestion entry point for inbound Gmail messages.

Both the Composio webhook route and the fallback-sync scheduler job call
`ingest_message` — it is the only code path that writes to `threads` /
`messages` / `events` for incoming mail, so dedupe and thread bookkeeping
live in exactly one place.
"""

import html
import re
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.collections import workspace_filter
from app.composio_client import RawGmailMessage
from app.events import log_event

SNIPPET_LENGTH = 140

MAX_STORED_BODY_CHARS = 200_000
"""Stored `bodyText`/`bodyHtml` are truncated to this — a single giant email
must not bloat the messages collection."""

DAILY_INGEST_CAP_SUBSCRIBED = 1_000
DAILY_INGEST_CAP_UNSUBSCRIBED = 50
"""Per-workspace daily ingest caps. Ingestion is the one write path an
outsider can drive (by emailing a connected inbox), so it must be bounded
independently of the AI-spend caps. Unsubscribed workspaces get a strict
cap: enough for the onboarding window (Gmail connects before the trial
starts), nowhere near enough to use InboxPilot as free email storage."""

_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


async def _consume_ingest_budget(db: AsyncIOMotorDatabase, workspace_id: str) -> bool:
    """Count this ingest against the workspace's daily cap, returning False
    once the cap is exceeded. Uses an atomic `$inc` on one counter doc per
    workspace per UTC day (TTL-reaped via `expiresAt`), so concurrent
    ingests can't race past the limit. Logs a single `ingest_cap_hit` event
    at the moment the cap is first crossed — never one per rejected message,
    or a sustained flood would just flood `events` instead."""
    workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
    subscribed = (workspace or {}).get("subscriptionStatus") in _ACTIVE_SUBSCRIPTION_STATUSES
    cap = DAILY_INGEST_CAP_SUBSCRIBED if subscribed else DAILY_INGEST_CAP_UNSUBSCRIBED

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    counter = await db.ingest_counters.find_one_and_update(
        {"_id": f"{workspace_id}:{day_start.date().isoformat()}"},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "workspaceId": workspace_id,
                "expiresAt": day_start + timedelta(days=2),
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    if counter["count"] <= cap:
        return True
    if counter["count"] == cap + 1:
        await log_event(db, workspace_id, "ingest_cap_hit", meta={"cap": cap})
    return False

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
# Malformed/truncated HTML can have an opening `<script>`/`<style>` tag with
# no matching close tag at all — the regex above only matches balanced
# pairs, so without this a truncated `<script>` would leave its raw JS
# leaking into the derived text as if it were message body. This second
# pass runs after the balanced-pair pass and strips any remaining
# unclosed script/style tag through to the end of the string.
_UNCLOSED_SCRIPT_STYLE_RE = re.compile(r"<(?:script|style)\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _derive_body_text_from_html(html_body: str) -> str:
    """HTML-only email fallback: Gmail sometimes delivers a message with no
    `bodyText` (just `bodyHtml`) — strip `<script>`/`<style>` blocks first
    (their contents aren't visible text, and a second pass also catches an
    unclosed script/style tag through end-of-string), then strip remaining
    tags, collapse whitespace, and unescape HTML entities (e.g. `&amp;`,
    `&#39;`) so classification/drafting/snippets get readable text instead
    of raw markup or an empty string."""
    without_script_style = _SCRIPT_STYLE_RE.sub(" ", html_body)
    without_unclosed_script_style = _UNCLOSED_SCRIPT_STYLE_RE.sub(" ", without_script_style)
    without_tags = _TAG_RE.sub(" ", without_unclosed_script_style)
    collapsed = _WHITESPACE_RE.sub(" ", without_tags).strip()
    return html.unescape(collapsed)


async def ingest_message(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    raw: RawGmailMessage,
    connected_email: str | None = None,
) -> str | None:
    """Persist one inbound Gmail message, returning the new `messages._id`
    (as a string) or `None` if it was skipped/already seen.

    `connected_email` lets callers that already hold the workspace's
    `connections` doc (the webhook route, the fallback-sync job) pass its
    `emailAddress` directly and skip the extra lookup below. When omitted,
    it's looked up the same way it always was."""

    existing = await db.messages.find_one(
        {"workspaceId": workspace_id, "gmailMessageId": raw["gmailMessageId"]}
    )
    if existing is not None:
        return None

    if raw.get("isOutbound"):
        return None

    if connected_email is None:
        connection = await db.connections.find_one(
            {"workspaceId": workspace_id, "provider": "gmail"}
        )
        connected_email = (connection or {}).get("emailAddress")
    if connected_email and raw["fromEmail"].lower() == connected_email.lower():
        return None

    if not await _consume_ingest_budget(db, workspace_id):
        return None

    body_text = raw["bodyText"]
    if not body_text and raw.get("bodyHtml"):
        body_text = _derive_body_text_from_html(raw["bodyHtml"])
    body_text = body_text[:MAX_STORED_BODY_CHARS]
    body_html = raw.get("bodyHtml")
    if body_html is not None:
        body_html = body_html[:MAX_STORED_BODY_CHARS]

    snippet = body_text[:SNIPPET_LENGTH]
    thread_filter = {"workspaceId": workspace_id, "gmailThreadId": raw["gmailThreadId"]}
    thread_update = {
        "$set": {
            "subject": raw["subject"],
            "customerEmail": raw["fromEmail"],
            "customerName": raw.get("fromName"),
            "snippet": snippet,
            "lastMessageAt": raw["receivedAt"],
        },
        "$setOnInsert": {
            "workspaceId": workspace_id,
            "gmailThreadId": raw["gmailThreadId"],
            "status": "needs_review",
            "category": None,
        },
    }
    try:
        thread = await db.threads.find_one_and_update(
            thread_filter,
            thread_update,
            upsert=True,
            return_document=True,
        )
    except DuplicateKeyError:
        # Another concurrent ingest already inserted the thread between our
        # upsert's "not found" check and its insert — the unique
        # (workspaceId, gmailThreadId) index caught it. The doc now exists,
        # so retrying without upsert semantics just updates it and wins.
        thread = await db.threads.find_one_and_update(
            thread_filter,
            thread_update,
            upsert=False,
            return_document=True,
        )

    message_doc = {
        "workspaceId": workspace_id,
        "threadId": str(thread["_id"]),
        "gmailMessageId": raw["gmailMessageId"],
        "direction": "inbound",
        "from": raw["fromEmail"],
        "to": raw["toEmail"],
        "bodyText": body_text,
        "bodyHtml": body_html,
        "sentBy": "customer",
        "receivedAt": raw["receivedAt"],
    }

    try:
        result = await db.messages.insert_one(message_doc)
    except DuplicateKeyError:
        return None

    await log_event(
        db,
        workspace_id,
        "email_received",
        meta={"threadId": str(thread["_id"]), "gmailMessageId": raw["gmailMessageId"]},
    )

    return str(result.inserted_id)
