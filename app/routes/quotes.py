from pathlib import Path
import json

from fastapi import APIRouter, Depends, HTTPException

from app.agents.lead import PRICEBOOK_CACHE, load_pricebook
from app.pricebook.schema import PriceBook
from app.routes.deps import get_tenant
from app.schemas import PricebookResponse, PricebookUpdateRequest

router = APIRouter(prefix="/v1/pricebook", tags=["pricebook"])


@router.get("/{tenant_id}", response_model=PricebookResponse)
def get_pricebook(tenant_id: int, tenant=Depends(get_tenant)) -> PricebookResponse:
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    book = load_pricebook(tenant_id)
    return PricebookResponse(tenant_id=tenant_id, pricebook=book.model_dump())


@router.post("/{tenant_id}", response_model=PricebookResponse)
def update_pricebook(tenant_id: int, payload: PricebookUpdateRequest, tenant=Depends(get_tenant)) -> PricebookResponse:
    if tenant.id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    path = Path("pricebook/construction_pricebook.json")
    path.write_text(json.dumps(payload.pricebook, indent=2))
    PRICEBOOK_CACHE[tenant_id] = PriceBook(**payload.pricebook)
    return PricebookResponse(tenant_id=tenant_id, pricebook=payload.pricebook)
