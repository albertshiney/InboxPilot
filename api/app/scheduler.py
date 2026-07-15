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
from app.db import get_db
from app.routers import webhooks_composio

FALLBACK_SYNC_LOOKBACK = timedelta(minutes=45)

scheduler = AsyncIOScheduler()


async def fallback_sync() -> None:
    """Poll every active Gmail connection for messages the webhook may have
    missed, ingesting each via the same `ingest_message` entry point the
    webhook uses."""
    from app.ingest import ingest_message

    db = get_db()
    since = datetime.now(timezone.utc) - FALLBACK_SYNC_LOOKBACK

    async for connection in db.connections.find({"status": "active"}):
        connection_id = connection.get("composioConnectionId")
        if not connection_id:
            continue
        workspace_id = connection["workspaceId"]
        connected_email = connection.get("emailAddress")

        raw_messages = composio_client.fetch_recent_messages(connection_id, since)
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


def start_scheduler() -> None:
    """Start the scheduler unless explicitly disabled (`ENABLE_SCHEDULER=0`,
    set by the test conftest)."""
    if os.environ.get("ENABLE_SCHEDULER", "1") == "0":
        return
    register_jobs()
    scheduler.start()
