from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.agents.qna import QnAAgent
from app.agents.router import heuristic_intent
from app.routes.deps import get_db_session, get_tenant
from app.schemas import QueryRequest, QueryResponse
from app.search.retrieval import HybridRetriever

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(payload: QueryRequest, tenant=Depends(get_tenant), session: Session = Depends(get_db_session)) -> QueryResponse:
    intent = heuristic_intent(payload.query)
    if intent == "lead_quote":
        return QueryResponse(
            answer="It sounds like you need a quote. Please continue via /v1/lead/ask so we can capture project details.",
            citations=[],
            retrieved=[],
        )
    retriever = HybridRetriever(session)
    agent = QnAAgent(retriever)
    response = await agent.answer(tenant.id, payload.query, payload.top_k, payload.rerank)
    return response
