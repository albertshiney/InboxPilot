"""Tests for /webhooks/stripe."""
from datetime import datetime, timezone

import stripe

from app.config import get_settings

from .conftest import HEADERS  # noqa: F401  (unused here, kept for parity)

WEBHOOK_PATH = "/webhooks/stripe"


def _set_stripe_settings(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    get_settings.cache_clear()


async def _post(client, body: bytes = b"{}", signature: str = "sig_ok"):
    headers = {"content-type": "application/json", "stripe-signature": signature}
    return await client.post(WEBHOOK_PATH, content=body, headers=headers)


async def test_webhook_rejects_bad_signature(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)

    def fake_construct_event(payload, sig_header, secret):
        raise stripe.error.SignatureVerificationError("bad sig", sig_header)

    monkeypatch.setattr(stripe.Webhook, "construct_event", fake_construct_event)

    r = await _post(client)

    assert r.status_code == 400


async def test_webhook_unknown_event_type_returns_200_ignored(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)

    event = {"type": "some.unhandled.event", "data": {"object": {}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    assert r.json()["ignored"] is True


async def test_checkout_session_completed_sets_plan_and_trial(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_1"})

    trial_end_ts = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_1",
                "subscription": {
                    "id": "sub_1",
                    "status": "trialing",
                    "trial_end": trial_end_ts,
                },
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["plan"] == "pro"
    assert workspace["subscriptionStatus"] == "trialing"
    assert workspace["trialEndsAt"].replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 1, tzinfo=timezone.utc
    )


async def test_checkout_session_completed_fetches_subscription_when_id_only(
    client, mock_db, monkeypatch
):
    """Real Stripe payloads carry `subscription` as a bare id string unless
    expansions are configured on the webhook destination."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_1"})

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"customer": "cus_1", "subscription": "sub_1"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)
    monkeypatch.setattr(
        stripe.Subscription,
        "retrieve",
        lambda sub_id: {"id": sub_id, "status": "active", "trial_end": None},
    )

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["plan"] == "pro"
    assert workspace["subscriptionStatus"] == "active"
    assert workspace["trialEndsAt"] is None


async def test_customer_subscription_updated_syncs_status(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "plan": "pro", "subscriptionStatus": "trialing"}
    )

    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {"customer": "cus_1", "status": "active"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["subscriptionStatus"] == "active"


async def test_customer_subscription_deleted_clears_plan(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "plan": "pro", "subscriptionStatus": "active"}
    )

    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_1"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["plan"] is None
    assert workspace["subscriptionStatus"] == "canceled"


async def test_invoice_payment_failed_sets_past_due(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "plan": "pro", "subscriptionStatus": "active"}
    )

    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_1"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["subscriptionStatus"] == "past_due"


async def test_checkout_session_completed_falls_back_to_metadata_workspace_id(
    client, mock_db, monkeypatch
):
    """Belt-and-braces fallback: if the customer id on the event doesn't
    match any workspace (e.g. the checkout-time atomic claim raced and
    lost), resolve the workspace via `metadata.workspaceId` on the Checkout
    Session and still activate it, backfilling stripeCustomerId too."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1"})

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_unknown",
                "metadata": {"workspaceId": "ws1"},
                "subscription": {
                    "id": "sub_1",
                    "status": "trialing",
                    "trial_end": None,
                },
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["plan"] == "pro"
    assert workspace["subscriptionStatus"] == "trialing"
    assert workspace["stripeCustomerId"] == "cus_unknown"


async def test_checkout_session_completed_missing_status_logs_anomaly_and_keeps_status(
    client, mock_db, monkeypatch
):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "subscriptionStatus": "trialing"}
    )

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_1",
                "subscription": {"id": "sub_1", "trial_end": None},
            }
        },
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    # Status is untouched since Stripe didn't send one - never silently
    # defaulted to "active".
    assert workspace["subscriptionStatus"] == "trialing"

    events = await mock_db.events.find({"type": "stripe_webhook_anomaly"}).to_list(None)
    assert len(events) == 1
    assert events[0]["meta"]["eventType"] == "checkout.session.completed"


async def test_webhook_unknown_customer_returns_200_and_no_op(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)

    event = {
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_does_not_exist"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
