"""Tests for /billing/checkout and /billing/portal."""
import stripe

from app.config import get_settings
from app.routers import billing

from .conftest import HEADERS


def _set_stripe_settings(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    get_settings.cache_clear()


async def test_checkout_creates_customer_and_returns_url(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1"})

    create_calls = []

    def fake_customer_create(**kwargs):
        create_calls.append(kwargs)
        return {"id": "cus_new123"}

    session_calls = []

    def fake_session_create(**kwargs):
        session_calls.append(kwargs)
        return {"id": "cs_1", "url": "https://checkout.stripe.com/cs_1"}

    monkeypatch.setattr(stripe.Customer, "create", fake_customer_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    r = await client.post("/billing/checkout", headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"url": "https://checkout.stripe.com/cs_1"}
    assert len(create_calls) == 1

    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["stripeCustomerId"] == "cus_new123"

    kwargs = session_calls[0]
    assert kwargs["customer"] == "cus_new123"
    assert kwargs["mode"] == "subscription"
    assert kwargs["line_items"] == [{"price": "price_123", "quantity": 1}]
    assert kwargs["subscription_data"] == {"trial_period_days": 7}
    assert kwargs["payment_method_collection"] == "always"
    assert kwargs["success_url"] == "https://app.example.com/settings?billing=success"
    assert kwargs["cancel_url"] == "https://app.example.com/settings?billing=cancelled"
    assert kwargs["metadata"] == {"workspaceId": "ws1"}


async def test_checkout_active_workspace_returns_409_and_no_stripe_calls(
    client, mock_db, monkeypatch
):
    """H5: an already-active workspace must not be able to open a second
    checkout (which would stack a duplicate subscription)."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "subscriptionStatus": "active"})

    create_calls = []
    session_calls = []

    monkeypatch.setattr(
        stripe.Customer, "create", lambda **k: create_calls.append(k) or {"id": "cus_x"}
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "create",
        lambda **k: session_calls.append(k) or {"id": "cs_x", "url": "u"},
    )

    r = await client.post("/billing/checkout", headers=HEADERS)

    assert r.status_code == 409
    assert create_calls == []
    assert session_calls == []


async def test_checkout_trialing_workspace_returns_409(client, mock_db, monkeypatch):
    """H5: a trialing workspace is also already subscribed."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "subscriptionStatus": "trialing"})

    r = await client.post("/billing/checkout", headers=HEADERS)

    assert r.status_code == 409


async def test_checkout_prior_trial_grants_no_trial_period(client, mock_db, monkeypatch):
    """H5: a workspace that already consumed a trial (canceled subscription
    with a trialEndsAt) must not be re-granted a free trial."""
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one(
        {
            "_id": "ws1",
            "stripeCustomerId": "cus_existing",
            "subscriptionStatus": "canceled",
            "trialEndsAt": "2026-01-01T00:00:00Z",
        }
    )

    session_calls = []

    def fake_session_create(**kwargs):
        session_calls.append(kwargs)
        return {"id": "cs_1", "url": "https://checkout.stripe.com/cs_1"}

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    r = await client.post("/billing/checkout", headers=HEADERS)

    assert r.status_code == 200
    assert session_calls[0]["subscription_data"] == {}
    assert "trial_period_days" not in session_calls[0]["subscription_data"]


async def test_checkout_unknown_workspace_returns_404_and_no_customer_created(
    client, mock_db, monkeypatch
):
    _set_stripe_settings(monkeypatch)

    create_calls = []

    def fake_customer_create(**kwargs):
        create_calls.append(kwargs)
        return {"id": "cus_new123"}

    monkeypatch.setattr(stripe.Customer, "create", fake_customer_create)

    r = await client.post("/billing/checkout", headers=HEADERS)

    assert r.status_code == 404
    assert create_calls == []


async def test_checkout_reuses_existing_customer_on_second_call(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1"})

    create_calls = []

    def fake_customer_create(**kwargs):
        create_calls.append(kwargs)
        return {"id": "cus_new123"}

    def fake_session_create(**kwargs):
        return {"id": "cs_1", "url": "https://checkout.stripe.com/cs_1"}

    monkeypatch.setattr(stripe.Customer, "create", fake_customer_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", fake_session_create)

    r1 = await client.post("/billing/checkout", headers=HEADERS)
    assert r1.status_code == 200

    r2 = await client.post("/billing/checkout", headers=HEADERS)
    assert r2.status_code == 200

    assert len(create_calls) == 1  # customer only created once


async def test_get_or_create_customer_id_loses_race_uses_winners_id(mock_db, monkeypatch):
    """Simulates a stale read: the in-memory `workspace` dict handed to
    `_get_or_create_customer_id` has no `stripeCustomerId` (as read at the
    top of the request), but by the time Stripe returns our new candidate
    customer, a concurrent request has already won and persisted its own
    customer id. The atomic claim must detect that loss and return the
    winner's id instead of orphaning our candidate."""
    await mock_db.workspaces.insert_one({"_id": "ws1"})
    stale_workspace = {"_id": "ws1"}  # no stripeCustomerId, as read before the race

    def fake_customer_create(**kwargs):
        return {"id": "cus_candidate"}

    monkeypatch.setattr(stripe.Customer, "create", fake_customer_create)

    # A concurrent request "wins" the race and persists its own customer id
    # between our stale read and our claim attempt.
    await mock_db.workspaces.update_one(
        {"_id": "ws1"}, {"$set": {"stripeCustomerId": "cus_winner"}}
    )

    result = await billing._get_or_create_customer_id(mock_db, "ws1", stale_workspace)

    assert result == "cus_winner"
    workspace = await mock_db.workspaces.find_one({"_id": "ws1"})
    assert workspace["stripeCustomerId"] == "cus_winner"


async def test_portal_unknown_workspace_returns_404(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)

    r = await client.post("/billing/portal", headers=HEADERS)

    assert r.status_code == 404


async def test_portal_without_customer_returns_409(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1"})

    r = await client.post("/billing/portal", headers=HEADERS)

    assert r.status_code == 409


async def test_portal_with_customer_returns_url(client, mock_db, monkeypatch):
    _set_stripe_settings(monkeypatch)
    await mock_db.workspaces.insert_one({"_id": "ws1", "stripeCustomerId": "cus_existing"})

    def fake_portal_create(**kwargs):
        assert kwargs["customer"] == "cus_existing"
        return {"id": "bps_1", "url": "https://billing.stripe.com/session/bps_1"}

    monkeypatch.setattr(stripe.billing_portal.Session, "create", fake_portal_create)

    r = await client.post("/billing/portal", headers=HEADERS)

    assert r.status_code == 200
    assert r.json() == {"url": "https://billing.stripe.com/session/bps_1"}
