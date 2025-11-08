import secrets

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import Tenant, get_session, hash_api_key
from app.schemas import TenantCreate, TenantResponse

router = APIRouter(prefix="/v1/tenants", tags=["tenant"])


def get_db():
    yield from get_session()


@router.post("", response_model=TenantResponse)
def create_tenant(payload: TenantCreate, session: Session = Depends(get_db)) -> TenantResponse:
    api_key = secrets.token_hex(16)
    tenant = Tenant(name=payload.name, region=payload.region, api_key_hash=hash_api_key(api_key))
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return TenantResponse(tenant_id=tenant.id, api_key=api_key)
