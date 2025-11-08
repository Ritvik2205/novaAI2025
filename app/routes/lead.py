from fastapi import APIRouter, Depends

from app.agents.lead import LeadAgent
from app.routes.deps import get_tenant
from app.schemas import LeadAskRequest, LeadAskResponse, LeadDialogState, LeadQuoteRequest, LeadQuoteResponse

router = APIRouter(prefix="/v1/lead", tags=["lead"])


@router.post("/ask", response_model=LeadAskResponse)
async def lead_ask(payload: LeadAskRequest, tenant=Depends(get_tenant)) -> LeadAskResponse:
    agent = LeadAgent(tenant.id)
    dialog_state = payload.dialog_state.model_dump() if payload.dialog_state else None
    state, followup, quote = await agent.handle_turn(payload.text, dialog_state)
    return LeadAskResponse(dialog_state=LeadDialogState.model_validate(state), followup=followup, quote=quote)


@router.post("/quote", response_model=LeadQuoteResponse)
async def lead_quote(payload: LeadQuoteRequest, tenant=Depends(get_tenant)) -> LeadQuoteResponse:
    agent = LeadAgent(tenant.id)
    state, _, quote = await agent.handle_turn("finalize", payload.dialog_state.model_dump())
    pdf_url = quote.get("pdf_path") if quote else None
    return LeadQuoteResponse(dialog_state=LeadDialogState.model_validate(state), quote=quote or {}, pdf_url=pdf_url)
