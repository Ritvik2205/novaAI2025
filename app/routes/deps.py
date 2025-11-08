from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from app.db import Tenant, fetch_tenant_by_key, get_session


def get_db_session():
    yield from get_session()


def get_tenant(api_key: str = Header(..., alias="X-API-Key"), session: Session = Depends(get_db_session)) -> Tenant:
    tenant = fetch_tenant_by_key(session, api_key)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return tenant
