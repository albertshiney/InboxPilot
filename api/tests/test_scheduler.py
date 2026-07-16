from datetime import datetime, timezone

from app import composio_client
from app.collections import ensure_indexes
from app.routers import webhooks_composio
from app.scheduler import fallback_sync


def _raw_message(**overrides) -> dict:
    base = {
        "gmailMessageId": "gm-seen",
        "gmailThreadId": "gt-1",
        "subject": "Where is my order?",
        "fromEmail": "customer@example.com",
        "fromName": "Cus Tomer",
        "toEmail": "support@ourcompany.com",
        "bodyText": "Hi, I never received my order.",
        "bodyHtml": "<p>Hi</p>",
        "receivedAt": datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
        "isOutbound": False,
    }
    base.update(overrides)
    return base


async def test_fallback_sync_only_calls_pipeline_hook_for_new_message(mock_db, monkeypatch):
    await ensure_indexes(mock_db)

    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "emailAddress": "support@ourcompany.com",
            "status": "active",
        }
    )
    # Already-seen message: pre-existing in `messages`, so ingest_message
    # will dedupe it and return None.
    await mock_db.messages.insert_one(
        {
            "workspaceId": "ws1",
            "threadId": "thread-existing",
            "gmailMessageId": "gm-seen",
            "direction": "inbound",
            "from": "customer@example.com",
            "to": "support@ourcompany.com",
            "bodyText": "already seen",
            "bodyHtml": None,
            "sentBy": "customer",
            "receivedAt": datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc),
        }
    )

    seen_message = _raw_message(gmailMessageId="gm-seen")
    new_message = _raw_message(gmailMessageId="gm-new", gmailThreadId="gt-2")

    def fake_fetch_recent_messages(connection_id, user_id, since_dt):
        assert connection_id == "conn_123"
        assert user_id == "ws1"
        return [seen_message, new_message]

    monkeypatch.setattr(composio_client, "fetch_recent_messages", fake_fetch_recent_messages)

    calls = []

    async def fake_pipeline_hook(workspace_id, message_id):
        calls.append((workspace_id, message_id))

    monkeypatch.setattr(webhooks_composio, "pipeline_hook", fake_pipeline_hook)

    await fallback_sync()

    assert len(calls) == 1
    workspace_id, message_id = calls[0]
    assert workspace_id == "ws1"

    new_message_doc = await mock_db.messages.find_one({"gmailMessageId": "gm-new"})
    assert new_message_doc is not None
    assert message_id == str(new_message_doc["_id"])
