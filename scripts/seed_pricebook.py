from __future__ import annotations

import json
import sys

from sqlmodel import Session, select

from app.db import Tenant, session_scope


def seed(tenant_name: str, pricebook_path: str) -> None:
    data = json.loads(open(pricebook_path).read())
    with session_scope() as session:
        tenant = session.exec(select(Tenant).where(Tenant.name == tenant_name)).first()
        if not tenant:
            tenant = Tenant(name=tenant_name, region="west", api_key_hash="seed")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
        tenant.settings_json = tenant.settings_json or {}
        tenant.settings_json["pricebook"] = data
        session.add(tenant)
        session.commit()
    print(f"seeded pricebook for {tenant_name}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/seed_pricebook.py <tenant-name> <pricebook.json>")
    seed(sys.argv[1], sys.argv[2])
