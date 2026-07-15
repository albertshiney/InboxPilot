"""Stripe checkout + customer-portal routes.

Both routes sit behind `workspace_id_dep` (same internal-key + workspace-id
guard as every other non-webhook route). Stripe calls are made through the
module-level `stripe.*` API (rather than an instantiated client) and
`stripe.api_key` is (re)assigned from settings on every request — this keeps
the calls monkeypatch-friendly for tests (`monkeypatch.setattr(stripe.Customer,
"create", ...)`) and cheap enough for MVP traffic that a sync call inline in
an async route is acceptable.
"""

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.collections import workspace_filter
from app.config import get_settings
from app.db import get_db
from app.deps import workspace_id_dep

router = APIRouter()


async def _get_workspace(db: AsyncIOMotorDatabase, workspace_id: str) -> dict:
    return await db.workspaces.find_one(workspace_filter(workspace_id)) or {}


async def _get_or_create_customer_id(
    db: AsyncIOMotorDatabase, workspace_id: str, workspace: dict
) -> str:
    customer_id = workspace.get("stripeCustomerId")
    if customer_id:
        return customer_id

    customer = stripe.Customer.create(metadata={"workspaceId": workspace_id})
    customer_id = customer["id"]
    await db.workspaces.update_one(
        workspace_filter(workspace_id),
        {"$set": {"stripeCustomerId": customer_id}},
        upsert=True,
    )
    return customer_id


@router.post("/billing/checkout")
async def create_checkout_session(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    db = get_db()
    workspace = await _get_workspace(db, workspace_id)
    customer_id = await _get_or_create_customer_id(db, workspace_id, workspace)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        subscription_data={"trial_period_days": 7},
        payment_method_collection="always",
        success_url=f"{settings.frontend_url}/settings?billing=success",
        cancel_url=f"{settings.frontend_url}/settings?billing=cancelled",
    )
    return {"url": session["url"]}


@router.post("/billing/portal")
async def create_portal_session(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    db = get_db()
    workspace = await _get_workspace(db, workspace_id)
    customer_id = workspace.get("stripeCustomerId")
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="no stripe customer for workspace"
        )

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.frontend_url}/settings",
    )
    return {"url": session["url"]}
