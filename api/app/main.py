from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.collections import ensure_indexes
from app.db import get_db
from app.deps import workspace_id_dep
from app.routers import health, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes(get_db())
    yield


app = FastAPI(title="InboxPilot API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(settings.router)


@app.get("/internal/whoami")
async def whoami(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Tiny protected probe route used to exercise workspace_id_dep."""
    return {"workspaceId": workspace_id}
