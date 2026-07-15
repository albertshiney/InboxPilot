from fastapi import Depends, FastAPI

from app.deps import workspace_id_dep
from app.routers import health

app = FastAPI(title="InboxPilot API")

app.include_router(health.router)


@app.get("/internal/whoami")
async def whoami(workspace_id: str = Depends(workspace_id_dep)) -> dict:
    """Tiny protected probe route used to exercise workspace_id_dep."""
    return {"workspaceId": workspace_id}
