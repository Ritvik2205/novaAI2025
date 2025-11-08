from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from app.db import Tenant
from app.main import app
from app.routes.deps import get_db_session
from app.routes.tenant import get_db as tenant_get_db


def test_tenant_and_auth_flow(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[Tenant.__table__])

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[tenant_get_db] = session_override

    client = TestClient(app)
    resp = client.post("/v1/tenants", json={"name": "Test", "region": "west"})
    assert resp.status_code == 200
    api_key = resp.json()["api_key"]

    resp = client.get("/v1/auth/ping", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    app.dependency_overrides.clear()
