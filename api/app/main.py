import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import composio_client
from app.collections import ensure_indexes
from app.config import get_settings
from app.db import get_db
from app.deps import workspace_id_dep
from app.routers import (
    billing,
    composio_connect,
    dashboard,
    health,
    kb,
    settings,
    threads,
    webhooks_composio,
    webhooks_stripe,
)
from app.scheduler import scheduler, start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes(get_db())
    start_scheduler()
    # Same guard as the scheduler: skipped under test (ENABLE_SCHEDULER=0),
    # and must never crash startup — a Composio outage or misconfiguration
    # here shouldn't take the whole API down.
    if os.environ.get("ENABLE_SCHEDULER", "1") != "0":
        try:
            await composio_client.ensure_webhook_subscription()
        except Exception:
            logger.exception("Failed to auto-register the Composio webhook subscription")
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


# Disable the interactive docs / OpenAPI schema in production so the API's
# route surface isn't publicly enumerable (M5).
_docs_disabled = get_settings().environment == "production"
app = FastAPI(
    title="InboxPilot API",
    lifespan=lifespan,
    docs_url=None if _docs_disabled else "/docs",
    redoc_url=None if _docs_disabled else "/redoc",
    openapi_url=None if _docs_disabled else "/openapi.json",
)

app.include_router(health.router)
app.include_router(settings.router)
app.include_router(composio_connect.router)
app.include_router(webhooks_composio.router)
app.include_router(billing.router)
app.include_router(webhooks_stripe.router)
app.include_router(kb.router)
app.include_router(threads.router)
app.include_router(dashboard.router)


@app.get("/internal/whoami")
async def whoami(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Tiny protected probe route used to exercise workspace_id_dep."""
    return {"workspaceId": workspace_id}
