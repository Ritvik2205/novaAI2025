from fastapi import APIRouter, Depends

from app.routes.deps import get_tenant

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/ping")
def auth_ping(tenant=Depends(get_tenant)) -> dict[str, str]:
    return {"status": "ok", "tenant": tenant.name}
