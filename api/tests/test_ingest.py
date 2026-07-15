from datetime import datetime, timezone

from app.collections import ensure_indexes
from app.ingest import ingest_message


def _raw(**overrides) -> dict:
    base = {
        "gmailMessageId": "gm-1",
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "fromEmail": "customer@example.com",
        "fromName": "Cus Tomer",
        "toEmail": "support@ourcompany.com",
        "bodyText": "Hi, I never received my order. " + ("x" * 200),
        "bodyHtml": "<p>Hi</p>",
        "receivedAt": datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        "isOutbound": False,
    }
    base.update(overrides)
    return base


async def test_ingest_message_inserts_thread_and_message_and_logs_event(mock_db):
    await ensure_indexes(mock_db)

    message_id = await ingest_message(mock_db, "ws1", _raw())

    assert message_id is not None

    message = await mock_db.messages.find_one({"gmailMessageId": "gm-1"})
    assert message is not None
    assert message["direction"] == "inbound"
    assert message["sentBy"] == "customer"
    assert message["from"] == "customer@example.com"
    assert message["to"] == "support@ourcompany.com"

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread is not None
    assert thread["subject"] == "Where is my order?"
    assert thread["customerEmail"] == "customer@example.com"
    assert thread["customerName"] == "Cus Tomer"
    assert len(thread["snippet"]) == 140
    assert str(message["threadId"]) == str(thread["_id"])

    event = await mock_db.events.find_one({"workspaceId": "ws1", "type": "email_received"})
    assert event is not None


async def test_ingest_message_dedupes_on_gmail_message_id(mock_db):
    await ensure_indexes(mock_db)

    first = await ingest_message(mock_db, "ws1", _raw())
    assert first is not None

    second = await ingest_message(mock_db, "ws1", _raw())
    assert second is None

    assert await mock_db.messages.count_documents({}) == 1
    assert await mock_db.threads.count_documents({}) == 1
    assert await mock_db.events.count_documents({"type": "email_received"}) == 1


async def test_ingest_message_skips_outbound(mock_db):
    await ensure_indexes(mock_db)

    result = await ingest_message(mock_db, "ws1", _raw(gmailMessageId="gm-out", isOutbound=True))

    assert result is None
    assert await mock_db.messages.count_documents({}) == 0
    assert await mock_db.threads.count_documents({}) == 0


async def test_ingest_message_skips_from_connected_support_address(mock_db):
    await ensure_indexes(mock_db)
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )

    result = await ingest_message(
        mock_db, "ws1", _raw(gmailMessageId="gm-self", fromEmail="support@ourcompany.com")
    )

    assert result is None
    assert await mock_db.messages.count_documents({}) == 0


async def test_ingest_message_same_thread_updates_last_message_at_and_snippet(mock_db):
    await ensure_indexes(mock_db)

    await ingest_message(mock_db, "ws1", _raw())
    await ingest_message(
        mock_db,
        "ws1",
        _raw(
            gmailMessageId="gm-2",
            bodyText="second message body",
            receivedAt=datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc),
        ),
    )

    assert await mock_db.threads.count_documents({}) == 1
    assert await mock_db.messages.count_documents({}) == 2

    thread = await mock_db.threads.find_one({"workspaceId": "ws1", "gmailThreadId": "gt-1"})
    assert thread["snippet"] == "second message body"
    # Mongo/BSON round-trips datetimes as naive UTC (matches existing driver
    # behavior elsewhere in this codebase).
    assert thread["lastMessageAt"] == datetime(2026, 7, 15, 13, 0)
