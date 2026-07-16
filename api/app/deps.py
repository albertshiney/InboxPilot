import hmac

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def workspace_id_dep(
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
) -> str:
    """Guard used by every non-webhook route: validates the shared internal
    key and returns the caller's workspace id."""
    settings = get_settings()

    if not x_internal_key or not hmac.compare_digest(
        x_internal_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal key")

    if not x_workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing workspace id")

    return x_workspace_id
