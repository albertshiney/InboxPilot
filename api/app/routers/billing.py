"""Stripe checkout + customer-portal routes.

Both routes sit behind `workspace_id_dep` (same internal-key + workspace-id
guard as every other non-webhook route). Stripe calls are made through the
module-level `stripe.*` API (rather than an instantiated client) and
`stripe.api_key` is (re)assigned from settings on every request — this keeps
the calls monkeypatch-friendly for tests (`monkeypatch.setattr(stripe.Customer,
"create", ...)`) and cheap enough for MVP traffic that a sync call inline in
an async route is acceptable.
"""

import asyncio

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.collections import workspace_filter
from app.config import get_settings
from app.db import get_db
from app.deps import workspace_id_dep

router = APIRouter()


async def _get_workspace_or_404(db: AsyncIOMotorDatabase, workspace_id: str) -> dict:
    workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found"
        )
    return workspace


async def _get_or_create_customer_id(
    db: AsyncIOMotorDatabase, workspace_id: str, workspace: dict
) -> str:
    customer_id = workspace.get("stripeCustomerId")
    if customer_id:
        return customer_id

    customer = await asyncio.to_thread(
        stripe.Customer.create, metadata={"workspaceId": workspace_id}
    )
    candidate_id = customer["id"]

    # Claim the candidate atomically: only set it if no other concurrent
    # request has already won the race and set one first. If the filter
    # doesn't match (someone else won), fall back to whatever id they
    # stored rather than handing back our orphaned candidate customer.
    claim_filter = {
        **workspace_filter(workspace_id),
        "$or": [
            {"stripeCustomerId": {"$exists": False}},
            {"stripeCustomerId": None},
        ],
    }
    claimed = await db.workspaces.find_one_and_update(
        claim_filter,
        {"$set": {"stripeCustomerId": candidate_id}},
        return_document=ReturnDocument.AFTER,
    )
    if claimed is not None:
        return candidate_id

    winner = await db.workspaces.find_one(workspace_filter(workspace_id))
    return (winner or {}).get("stripeCustomerId") or candidate_id


@router.post("/billing/checkout")
async def create_checkout_session(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    db = get_db()
    workspace = await _get_workspace_or_404(db, workspace_id)

    # Guard against re-grant / duplicate subscriptions: an already-active or
    # trialing workspace must not be able to open a second checkout (which
    # would re-grant a free trial or stack a second Stripe subscription).
    current_status = workspace.get("subscriptionStatus")
    if current_status in ("active", "trialing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="already subscribed"
        )

    # Only grant the 7-day trial to workspaces that have never had one. A prior
    # trial is anything with `trialEndsAt` set, or a subscriptionStatus that's
    # ever been something other than None/"none".
    had_trial = bool(workspace.get("trialEndsAt")) or current_status not in (None, "none")
    subscription_data = {} if had_trial else {"trial_period_days": 7}

    customer_id = await _get_or_create_customer_id(db, workspace_id, workspace)

    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        subscription_data=subscription_data,
        payment_method_collection="always",
        success_url=f"{settings.frontend_url}/settings?billing=success",
        cancel_url=f"{settings.frontend_url}/settings?billing=cancelled",
        metadata={"workspaceId": workspace_id},
    )
    return {"url": session["url"]}


@router.post("/billing/portal")
async def create_portal_session(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    db = get_db()
    workspace = await _get_workspace_or_404(db, workspace_id)
    customer_id = workspace.get("stripeCustomerId")
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no stripe customer for workspace"
        )

    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=f"{settings.frontend_url}/settings",
    )
    return {"url": session["url"]}
