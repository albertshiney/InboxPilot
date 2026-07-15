"""Stripe subscription webhook ingestion.

Mounted *outside* `workspace_id_dep` — Stripe calls this route directly, so
it authenticates via `stripe.Webhook.construct_event` signature verification
(like `/webhooks/composio` authenticates via HMAC) instead of the internal
API key / workspace header pair every other route uses. Workspaces are
resolved by `stripeCustomerId` rather than a workspace id header, since
Stripe has no notion of our workspace ids.
"""

from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, Request, Response

from app.collections import workspace_filter
from app.config import get_settings
from app.db import get_db
from app.events import log_event
from app.ratelimit import rate_limit_dependency

router = APIRouter()

SIGNATURE_HEADER = "stripe-signature"


def _unix_to_datetime(value) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


async def _find_workspace_by_customer(db, customer_id: str | None) -> dict | None:
    if not customer_id:
        return None
    return await db.workspaces.find_one({"stripeCustomerId": customer_id})


async def _handle_checkout_session_completed(db, obj: dict) -> None:
    customer_id = obj.get("customer")
    workspace = await _find_workspace_by_customer(db, customer_id)

    if workspace is None:
        # Belt-and-braces fallback: if the customer lookup misses (e.g. the
        # checkout-time claim raced and lost, or the customer id changed),
        # resolve the workspace via `metadata.workspaceId` — set both on the
        # Stripe Customer at creation time and on the Checkout Session
        # itself (see `billing.py`), so it rides along on this event either
        # way.
        metadata = obj.get("metadata") or {}
        workspace_id = metadata.get("workspaceId")
        if not workspace_id:
            return
        workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
        if workspace is None:
            return

    # Stripe's real `checkout.session.completed` payload carries
    # `subscription` as a bare id string (not expanded) unless the webhook
    # destination has expansions configured — so a string means we must
    # fetch the subscription ourselves to read its status/trial_end. Test
    # fixtures may pass the subscription inline as a dict to skip that
    # round trip.
    subscription = obj.get("subscription") or {}
    if isinstance(subscription, str):
        subscription = stripe.Subscription.retrieve(subscription)

    update: dict = {
        "plan": "pro",
        "trialEndsAt": _unix_to_datetime(subscription.get("trial_end")),
    }
    status_value = subscription.get("status")
    if status_value:
        update["subscriptionStatus"] = status_value
    else:
        await log_event(
            db,
            str(workspace["_id"]),
            "stripe_webhook_anomaly",
            meta={"eventType": "checkout.session.completed"},
        )
    if customer_id and workspace.get("stripeCustomerId") != customer_id:
        update["stripeCustomerId"] = customer_id

    await db.workspaces.update_one(workspace_filter(str(workspace["_id"])), {"$set": update})
    await log_event(
        db,
        str(workspace["_id"]),
        "checkout_completed",
        meta={"subscriptionStatus": update.get("subscriptionStatus", workspace.get("subscriptionStatus"))},
    )


async def _handle_subscription_updated(db, obj: dict) -> None:
    workspace = await _find_workspace_by_customer(db, obj.get("customer"))
    if workspace is None:
        return

    update: dict = {"subscriptionStatus": obj.get("status")}
    if "trial_end" in obj:
        update["trialEndsAt"] = _unix_to_datetime(obj.get("trial_end"))

    await db.workspaces.update_one(workspace_filter(str(workspace["_id"])), {"$set": update})
    await log_event(
        db,
        str(workspace["_id"]),
        "subscription_updated",
        meta={"subscriptionStatus": update["subscriptionStatus"]},
    )


async def _handle_subscription_deleted(db, obj: dict) -> None:
    workspace = await _find_workspace_by_customer(db, obj.get("customer"))
    if workspace is None:
        return

    await db.workspaces.update_one(
        workspace_filter(str(workspace["_id"])),
        {"$set": {"plan": None, "subscriptionStatus": "canceled"}},
    )
    await log_event(db, str(workspace["_id"]), "subscription_canceled")


async def _handle_invoice_payment_failed(db, obj: dict) -> None:
    workspace = await _find_workspace_by_customer(db, obj.get("customer"))
    if workspace is None:
        return

    await db.workspaces.update_one(
        workspace_filter(str(workspace["_id"])),
        {"$set": {"subscriptionStatus": "past_due"}},
    )
    await log_event(db, str(workspace["_id"]), "invoice_payment_failed")


_HANDLERS = {
    "checkout.session.completed": _handle_checkout_session_completed,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
    "invoice.payment_failed": _handle_invoice_payment_failed,
}


@router.post(
    "/webhooks/stripe", response_model=None, dependencies=[Depends(rate_limit_dependency)]
)
async def receive_stripe_webhook(request: Request) -> Response | dict:
    raw_body = await request.body()
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    try:
        event = stripe.Webhook.construct_event(
            raw_body, request.headers.get(SIGNATURE_HEADER), settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return Response(status_code=400, content="invalid signature or payload")

    event_type = event["type"]
    handler = _HANDLERS.get(event_type)
    if handler is None:
        return {"ok": True, "ignored": True}

    db = get_db()
    obj = event["data"]["object"]
    await handler(db, obj)

    return {"ok": True}
