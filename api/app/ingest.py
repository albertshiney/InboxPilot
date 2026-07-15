"""Single ingestion entry point for inbound Gmail messages.

Both the Composio webhook route and the fallback-sync scheduler job call
`ingest_message` — it is the only code path that writes to `threads` /
`messages` / `events` for incoming mail, so dedupe and thread bookkeeping
live in exactly one place.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.composio_client import RawGmailMessage
from app.events import log_event

SNIPPET_LENGTH = 140


async def ingest_message(
    db: AsyncIOMotorDatabase, workspace_id: str, raw: RawGmailMessage
) -> str | None:
    """Persist one inbound Gmail message, returning the new `messages._id`
    (as a string) or `None` if it was skipped/already seen."""

    existing = await db.messages.find_one({"gmailMessageId": raw["gmailMessageId"]})
    if existing is not None:
        return None

    if raw.get("isOutbound"):
        return None

    connection = await db.connections.find_one(
        {"workspaceId": workspace_id, "provider": "gmail"}
    )
    connected_address = (connection or {}).get("emailAddress")
    if connected_address and raw["fromEmail"].lower() == connected_address.lower():
        return None

    snippet = raw["bodyText"][:SNIPPET_LENGTH]
    thread = await db.threads.find_one_and_update(
        {"workspaceId": workspace_id, "gmailThreadId": raw["gmailThreadId"]},
        {
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
        },
        upsert=True,
        return_document=True,
    )

    message_doc = {
        "threadId": str(thread["_id"]),
        "gmailMessageId": raw["gmailMessageId"],
        "direction": "inbound",
        "from": raw["fromEmail"],
        "to": raw["toEmail"],
        "bodyText": raw["bodyText"],
        "bodyHtml": raw.get("bodyHtml"),
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
