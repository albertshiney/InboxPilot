from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.collections import ensure_indexes
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes(get_db())
    start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="InboxPilot API", lifespan=lifespan)

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
