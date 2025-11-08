"""Agentuity entry point for the ScottyLabs CRM orchestrator."""

from __future__ import annotations

import json
from typing import Any, Dict

from agentuity import AgentContext, AgentRequest, AgentResponse

from backend.config import get_settings
from backend.agents.orchestrator import AgentOrchestrator
from backend.repositories.memory import CRMRepository
from backend.services.agentuity_client import AgentuityClient
from backend.services.openrouter_client import OpenRouterClient
from backend.services.rag_service import RAGService
from backend.services.scheduler import CalendarService


# Instantiate shared orchestrator once per container lifecycle.
_settings = get_settings()
_repository = CRMRepository(_settings.base_data_dir / "crm_state.json")
_openrouter_client = OpenRouterClient(_settings.openrouter_api_key, _settings.openrouter_base_url)
_agentuity_client = AgentuityClient(_settings.agentuity_api_key, _settings.agentuity_base_url)
_calendar_service = CalendarService(_settings.calendar_provider, _settings.calendar_credentials_path)
_rag_service = RAGService(
    persist_path=_settings.chroma_persist_path,
    embedder_model=_settings.embedder_model,
    chunk_size=_settings.chunk_size,
    chunk_overlap=_settings.chunk_overlap,
)
_orchestrator = AgentOrchestrator(
    repository=_repository,
    openrouter=_openrouter_client,
    agentuity=_agentuity_client,
    calendar=_calendar_service,
    rag=_rag_service,
    settings=_settings,
)


def _json_response(response: AgentResponse, payload: Dict[str, Any], status_code: int = 200):
    return response.json(payload, status_code=status_code)


async def run(request: AgentRequest, response: AgentResponse, context: AgentContext):
    try:
        body_text = await request.data.text()
    except AttributeError:
        body_text = await request.text()

    payload = json.loads(body_text) if body_text else {}
    action = payload.get("action")
    data = payload.get("data", {})

    try:
        if action == "start_onboarding":
            result = _orchestrator.start_onboarding(data)
            return _json_response(response, result)
        if action == "answer_onboarding":
            session_id = data.get("session_id")
            answer = data.get("answer")
            if not session_id or answer is None:
                return _json_response(response, {"error": "session_id and answer required"}, status_code=400)
            result = _orchestrator.answer_onboarding(session_id, answer)
            return _json_response(response, result)
        if action == "handle_lead":
            result = _orchestrator.handle_inbound_message(data)
            return _json_response(response, result)
        if action == "knowledge_sections":
            company_id = data.get("company_id")
            if not company_id:
                return _json_response(response, {"error": "company_id required"}, status_code=400)
            result = _orchestrator.generate_knowledge_sections(company_id)
            return _json_response(response, result)
        if action == "update_visibility":
            company_id = data.get("company_id")
            internal_only = data.get("internal_only", [])
            if not company_id:
                return _json_response(response, {"error": "company_id required"}, status_code=400)
            result = _orchestrator.update_knowledge_visibility(company_id, [str(title) for title in internal_only])
            return _json_response(response, result)
        if action == "list_groups":
            company_id = data.get("company_id")
            result = _orchestrator.list_student_groups(company_id)
            return _json_response(response, {"student_groups": result})
        if action == "list_leads":
            company_id = data.get("company_id")
            result = _orchestrator.list_leads(company_id)
            return _json_response(response, result)
        return _json_response(response, {"error": f"Unknown action '{action}'"}, status_code=400)
    except Exception as exc:  # pragma: no cover - defensive logging in production
        context.logger.error("Agentuity orchestrator error: %s", exc, exc_info=True)
        return _json_response(response, {"error": str(exc)}, status_code=500)
