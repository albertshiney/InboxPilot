"""Shared Stripe -> workspace subscription reconciliation.

`/webhooks/stripe` is the normal writer of `subscriptionStatus`, but webhook
delivery is not guaranteed (local dev without `stripe listen`, delivery
outages, a handler crash). This module holds the single "ask Stripe and
persist what it says" primitive used by every self-heal path:

- `GET /settings` calls it when the stored status is *inactive*, so a missed
  `checkout.session.completed` doesn't leave a paying customer locked out.
- The daily scheduler job calls it for every *active/trialing* workspace, so
  a missed `customer.subscription.deleted` doesn't leave a canceled customer
  with free access forever.
- `POST /billing/checkout` calls it before opening a checkout for an existing
  customer, so a stale "none" can't grant a duplicate subscription.

Any Stripe failure falls through to the stored doc — callers must never
break because reconciliation hiccuped.
"""

import asyncio
from datetime import datetime, timezone

import stripe
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.collections import workspace_filter
from app.config import get_settings
from app.events import log_event

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


async def sync_subscription_from_stripe(
    db: AsyncIOMotorDatabase, workspace_id: str, doc: dict
) -> dict:
    """Fetch the customer's most recent subscription from Stripe and persist
    any status change onto the workspace. Returns the (possibly updated)
    workspace doc; on any Stripe failure returns the stored doc unchanged."""
    customer_id = doc.get("stripeCustomerId")
    settings = get_settings()
    if not customer_id or not settings.stripe_secret_key:
        return doc

    stripe.api_key = settings.stripe_secret_key
    try:
        subscriptions = await asyncio.to_thread(
            stripe.Subscription.list, customer=customer_id, status="all", limit=1
        )
    except Exception:
        return doc

    # Stripe objects don't support dict-style .get() (stripe-python >= 13);
    # subscript + `in` work on both StripeObject and plain dicts.
    data = subscriptions["data"] if "data" in subscriptions else []
    if not data:
        return doc

    subscription = data[0]
    new_status = subscription["status"] if "status" in subscription else None
    status_value = doc.get("subscriptionStatus", "none")
    if not new_status or new_status == status_value:
        return doc

    trial_end = subscription["trial_end"] if "trial_end" in subscription else None
    update = {
        "subscriptionStatus": new_status,
        "plan": None if new_status == "canceled" else "pro",
        "trialEndsAt": (
            datetime.fromtimestamp(trial_end, tz=timezone.utc) if trial_end else None
        ),
    }
    await db.workspaces.update_one(workspace_filter(workspace_id), {"$set": update})
    await log_event(
        db,
        workspace_id,
        "subscription_reconciled",
        meta={"subscriptionStatus": new_status, "previous": status_value},
    )
    doc.update(update)
    return doc
