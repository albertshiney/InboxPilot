from datetime import datetime, timedelta, timezone

from app import composio_client
from app.collections import ensure_indexes
from app.routers import webhooks_composio
from app.scheduler import UNSUBSCRIBED_CONNECTION_GRACE, fallback_sync


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

    # fallback_sync only polls Composio for subscribed workspaces.
    await mock_db.workspaces.insert_one({"_id": "ws1", "subscriptionStatus": "active"})
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


async def test_fallback_sync_skips_unsubscribed_workspace_without_composio_calls(
    mock_db, monkeypatch
):
    """A connected-but-unsubscribed workspace must not consume metered
    Composio operations (trigger re-assert + GMAIL_FETCH_EMAILS) on every
    fallback pass — the pipeline would refuse its messages anyway."""
    await ensure_indexes(mock_db)

    await mock_db.workspaces.insert_one({"_id": "ws1", "subscriptionStatus": "none"})
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "active",
            "connectedAt": datetime.now(timezone.utc),  # well within grace
        }
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Composio must not be called for unsubscribed workspaces")

    monkeypatch.setattr(composio_client, "fetch_recent_messages", fail_if_called)
    monkeypatch.setattr(composio_client, "ensure_gmail_trigger", fail_if_called)
    monkeypatch.setattr(composio_client, "delete_connected_account", fail_if_called)

    await fallback_sync()

    # Within the grace window the connection is left untouched.
    stored = await mock_db.connections.find_one({"workspaceId": "ws1"})
    assert stored["status"] == "active"


async def test_fallback_sync_prunes_unsubscribed_connection_past_grace(mock_db, monkeypatch):
    """Past the grace window, an unsubscribed workspace's Composio connected
    account is deleted (stopping its per-email trigger deliveries) and the
    local doc flipped to disconnected."""
    await ensure_indexes(mock_db)

    await mock_db.workspaces.insert_one({"_id": "ws1", "subscriptionStatus": "none"})
    await mock_db.connections.insert_one(
        {
            "workspaceId": "ws1",
            "provider": "gmail",
            "composioConnectionId": "conn_123",
            "status": "active",
            "connectedAt": datetime.now(timezone.utc)
            - UNSUBSCRIBED_CONNECTION_GRACE
            - timedelta(days=1),
        }
    )

    deleted = []

    async def fake_delete_connected_account(connection_id):
        deleted.append(connection_id)

    monkeypatch.setattr(
        composio_client, "delete_connected_account", fake_delete_connected_account
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("must not poll a pruned connection")

    monkeypatch.setattr(composio_client, "fetch_recent_messages", fail_if_called)
    monkeypatch.setattr(composio_client, "ensure_gmail_trigger", fail_if_called)

    await fallback_sync()

    assert deleted == ["conn_123"]
    stored = await mock_db.connections.find_one({"workspaceId": "ws1"})
    assert stored["status"] == "disconnected"
    assert "composioConnectionId" not in stored
    assert stored["disconnectedAt"] is not None


async def test_reconcile_active_subscriptions_downgrades_stale_active_workspace(
    mock_db, monkeypatch
):
    """A missed cancellation webhook leaves the db saying "active" while
    Stripe says "canceled" — the daily sweep must correct it (the /settings
    read-time reconcile only heals the inactive->active direction)."""
    import stripe

    from app.config import get_settings
    from app.scheduler import reconcile_active_subscriptions

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    get_settings.cache_clear()

    await mock_db.workspaces.insert_many(
        [
            {
                "_id": "ws_stale",
                "stripeCustomerId": "cus_stale",
                "plan": "pro",
                "subscriptionStatus": "active",
            },
            {
                "_id": "ws_fine",
                "stripeCustomerId": "cus_fine",
                "plan": "pro",
                "subscriptionStatus": "active",
            },
            # No customer id: must be skipped (nothing to ask Stripe about).
            {"_id": "ws_no_customer", "subscriptionStatus": "trialing"},
            # Inactive: not this job's concern.
            {"_id": "ws_none", "stripeCustomerId": "cus_none", "subscriptionStatus": "none"},
        ]
    )

    listed_customers = []

    def fake_sub_list(**kwargs):
        listed_customers.append(kwargs["customer"])
        if kwargs["customer"] == "cus_stale":
            return {"data": [{"status": "canceled", "trial_end": None}]}
        return {"data": [{"status": "active", "trial_end": None}]}

    monkeypatch.setattr(stripe.Subscription, "list", fake_sub_list)

    await reconcile_active_subscriptions()

    assert sorted(listed_customers) == ["cus_fine", "cus_stale"]

    stale = await mock_db.workspaces.find_one({"_id": "ws_stale"})
    assert stale["subscriptionStatus"] == "canceled"
    assert stale["plan"] is None

    fine = await mock_db.workspaces.find_one({"_id": "ws_fine"})
    assert fine["subscriptionStatus"] == "active"
    assert fine["plan"] == "pro"

    get_settings.cache_clear()
