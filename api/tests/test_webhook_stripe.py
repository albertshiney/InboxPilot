"""Tests for /webhooks/stripe."""
from datetime import datetime, timezone

import stripe

from app import ratelimit
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

    event = {"id": "evt_unknown", "type": "some.unhandled.event", "data": {"object": {}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    assert r.json()["ignored"] is True


async def test_checkout_session_completed_sets_plan_and_trial(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_1"})

    trial_end_ts = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    event = {
        "id": "evt_checkout_trial",
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


async def test_checkout_session_completed_with_real_stripe_event_object(
    client, mock_db, monkeypatch
):
    """construct_event returns StripeObjects, not dicts — they have no .get()
    since stripe-python v13, so handlers must not receive them raw."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_1"})

    trial_end_ts = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    event = stripe.Event.construct_from(
        {
            "id": "evt_1",
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "object": "checkout.session",
                    "customer": "cus_1",
                    "subscription": {
                        "id": "sub_1",
                        "object": "subscription",
                        "status": "trialing",
                        "trial_end": trial_end_ts,
                    },
                }
            },
        },
        "sk_test_123",
    )
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["plan"] == "pro"
    assert workspace["subscriptionStatus"] == "trialing"


async def test_checkout_session_completed_fetches_subscription_when_id_only(
    client, mock_db, monkeypatch
):
    """Real Stripe payloads carry `subscription` as a bare id string unless
    expansions are configured on the webhook destination."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_1"})

    event = {
        "id": "evt_checkout_idonly",
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
        "id": "evt_sub_updated",
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
        "id": "evt_sub_deleted",
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
        "id": "evt_invoice_failed",
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
        "id": "evt_checkout_metadata",
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
        "id": "evt_checkout_nostatus",
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
        "id": "evt_unknown_customer",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_does_not_exist"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r = await _post(client)

    assert r.status_code == 200


async def test_webhook_fails_closed_when_signing_secret_unset(client, mock_db, monkeypatch):
    """M1: without a signing secret Stripe cannot be authenticated, so the
    handler must fail closed with 500 rather than trust the payload."""
    _set_stripe_settings(monkeypatch)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
    get_settings.cache_clear()

    constructed = []

    def fake_construct_event(*a, **k):
        constructed.append(True)
        return {"id": "evt_x", "type": "invoice.payment_failed", "data": {"object": {}}}

    monkeypatch.setattr(stripe.Webhook, "construct_event", fake_construct_event)

    r = await _post(client)

    assert r.status_code == 500
    # Fail-closed: signature verification is never even attempted.
    assert constructed == []


async def test_webhook_replayed_event_is_ignored_as_duplicate(client, mock_db, monkeypatch):
    """M2: a redelivered event (same id) must be recorded once and
    short-circuited on replay so its side effects don't run twice."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "plan": "pro", "subscriptionStatus": "active"}
    )

    event = {
        "id": "evt_replay_1",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_1"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    r1 = await _post(client)
    assert r1.status_code == 200
    assert r1.json() == {"ok": True}

    r2 = await _post(client)
    assert r2.status_code == 200
    assert r2.json() == {"ok": True, "duplicate": True}

    # Only one record of the event id was persisted.
    recorded = await mock_db.stripe_events.find({"_id": "evt_replay_1"}).to_list(None)
    assert len(recorded) == 1


async def test_webhook_rate_limited_after_120_requests_per_minute(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)

    event = {
        "id": "evt_rate_limited",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_does_not_exist"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    for _ in range(ratelimit.MAX_REQUESTS_PER_MINUTE):
        r = await _post(client)
        assert r.status_code == 200

    r = await _post(client)
    assert r.status_code == 429


async def test_webhook_failed_handler_releases_idempotency_marker_so_retry_succeeds(
    client, mock_db, monkeypatch
):
    """A handler crash must not eat the event: the idempotency marker is
    removed so Stripe's retry is processed instead of short-circuited as a
    duplicate (otherwise e.g. a missed subscription.deleted would leave a
    canceled workspace active forever)."""
    import pytest

    from app.routers import webhooks_stripe

    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {"_id": "ws1", "stripeCustomerId": "cus_1", "plan": "pro", "subscriptionStatus": "active"}
    )

    event = {
        "id": "evt_retry_1",
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_1"}},
    }
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)

    async def failing_handler(db, obj):
        raise RuntimeError("transient failure")

    monkeypatch.setitem(
        webhooks_stripe._HANDLERS, "customer.subscription.deleted", failing_handler
    )

    # First delivery: handler blows up; the error propagates (Stripe sees a
    # 5xx and will retry) and the idempotency marker must be gone.
    with pytest.raises(RuntimeError):
        await _post(client)
    assert await mock_db.stripe_events.find({"_id": "evt_retry_1"}).to_list(None) == []

    # Retry with the handler healthy: processed as a fresh event, not a
    # duplicate — the workspace is actually canceled.
    monkeypatch.setitem(
        webhooks_stripe._HANDLERS,
        "customer.subscription.deleted",
        webhooks_stripe._handle_subscription_deleted,
    )
    r = await _post(client)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["subscriptionStatus"] == "canceled"
    assert workspace["plan"] is None
