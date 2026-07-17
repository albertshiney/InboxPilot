"""APScheduler jobs: fallback Gmail sync + monthly usage reset.

Started from `main.py`'s lifespan, guarded by env `ENABLE_SCHEDULER`
(default on; tests set it to `"0"` so no background jobs run during the
test suite)."""

import inspect
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app import composio_client
from app.collections import workspace_filter
from app.db import get_db
from app.events import log_event
from app.routers import webhooks_composio

FALLBACK_SYNC_LOOKBACK = timedelta(minutes=45)

# How long a connected-but-unsubscribed workspace keeps its Composio
# connected account before it's pruned. Long enough to finish onboarding
# (connect Gmail, then start the trial) with lots of slack; short enough
# that abandoned/never-subscribed connections don't fire (and meter)
# Composio trigger deliveries forever.
UNSUBSCRIBED_CONNECTION_GRACE = timedelta(days=14)

scheduler = AsyncIOScheduler()


def _as_utc(value: datetime) -> datetime:
    """Mongo returns naive UTC datetimes — normalize for comparison."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def fallback_sync() -> None:
    """Poll active Gmail connections of subscribed workspaces for messages
    the webhook may have missed, ingesting each via the same
    `ingest_message` entry point the webhook uses.

    Composio spend gating: each pass costs two metered Composio operations
    per connection (trigger re-assert + `GMAIL_FETCH_EMAILS`), so
    connections whose workspace has no active/trialing subscription are
    skipped entirely — the pipeline would refuse to process their messages
    anyway (`process_inbound`'s subscription gate). Connections that have
    been active without a subscription for longer than
    `UNSUBSCRIBED_CONNECTION_GRACE` are pruned: the Composio connected
    account is deleted (stopping its per-email trigger deliveries) and the
    local doc flipped to disconnected, so reconnecting goes back through
    the normal connect flow."""
    from app.ingest import ingest_message
    from app.stripe_sync import ACTIVE_SUBSCRIPTION_STATUSES

    db = get_db()
    now = datetime.now(timezone.utc)
    since = now - FALLBACK_SYNC_LOOKBACK

    async for connection in db.connections.find({"status": "active"}):
        connection_id = connection.get("composioConnectionId")
        if not connection_id:
            continue
        workspace_id = connection["workspaceId"]
        connected_email = connection.get("emailAddress")

        workspace = await db.workspaces.find_one(workspace_filter(workspace_id))
        subscription_status = (workspace or {}).get("subscriptionStatus") or "none"
        if subscription_status not in ACTIVE_SUBSCRIPTION_STATUSES:
            connected_at = connection.get("connectedAt")
            if (
                connected_at is not None
                and now - _as_utc(connected_at) > UNSUBSCRIBED_CONNECTION_GRACE
            ):
                await composio_client.delete_connected_account(connection_id)
                await db.connections.update_one(
                    {"_id": connection["_id"]},
                    {
                        "$set": {"status": "disconnected", "disconnectedAt": now},
                        "$unset": {"composioConnectionId": ""},
                    },
                )
                await log_event(db, workspace_id, "connection.pruned_unsubscribed")
            continue

        # Self-heal: re-assert the Gmail trigger for every active connection
        # on each fallback pass. `ensure_gmail_trigger` is upsert semantics
        # (cheap, idempotent) and already swallows its own exceptions, so an
        # active connection whose trigger was somehow disabled/dropped gets
        # it re-enabled without any extra error handling here.
        ensure_trigger_result = composio_client.ensure_gmail_trigger(connection_id)
        if inspect.isawaitable(ensure_trigger_result):
            await ensure_trigger_result

        raw_messages = composio_client.fetch_recent_messages(connection_id, workspace_id, since)
        if inspect.isawaitable(raw_messages):
            raw_messages = await raw_messages
        for raw in raw_messages:
            message_id = await ingest_message(db, workspace_id, raw, connected_email)
            if message_id is not None:
                await webhooks_composio.pipeline_hook(workspace_id, message_id)


async def reset_monthly_usage() -> None:
    """Cron job: first of the month, 00:00 UTC — zero every workspace's
    `usage.emailsProcessedThisMonth` counter."""
    db = get_db()
    await db.workspaces.update_many({}, {"$set": {"usage.emailsProcessedThisMonth": 0}})


async def reconcile_active_subscriptions() -> None:
    """Cron job: daily — re-verify every active/trialing workspace against
    Stripe. Webhooks are the normal writer of `subscriptionStatus`, but a
    missed `customer.subscription.deleted`/`updated` would otherwise leave a
    canceled customer with free access forever: the read-time reconcile in
    `/settings` only heals the inactive→active direction. `sync_subscription_
    from_stripe` swallows per-customer Stripe failures (returns the doc
    unchanged), so one bad customer never aborts the sweep."""
    from app.stripe_sync import ACTIVE_SUBSCRIPTION_STATUSES, sync_subscription_from_stripe

    db = get_db()
    async for workspace in db.workspaces.find(
        {
            "subscriptionStatus": {"$in": sorted(ACTIVE_SUBSCRIPTION_STATUSES)},
            "stripeCustomerId": {"$nin": [None, ""]},
        }
    ):
        await sync_subscription_from_stripe(db, str(workspace["_id"]), workspace)


def register_jobs() -> None:
    scheduler.add_job(
        fallback_sync,
        trigger=IntervalTrigger(minutes=10),
        id="fallback_sync",
        replace_existing=True,
    )
    scheduler.add_job(
        reset_monthly_usage,
        trigger=CronTrigger(day=1, hour=0, minute=0, timezone=timezone.utc),
        id="reset_monthly_usage",
        replace_existing=True,
    )
    scheduler.add_job(
        reconcile_active_subscriptions,
        trigger=CronTrigger(hour=3, minute=0, timezone=timezone.utc),
        id="reconcile_active_subscriptions",
        replace_existing=True,
    )


def start_scheduler() -> None:
    """Start the scheduler unless explicitly disabled (`ENABLE_SCHEDULER=0`,
    set by the test conftest)."""
    if os.environ.get("ENABLE_SCHEDULER", "1") == "0":
        return
    register_jobs()
    scheduler.start()
