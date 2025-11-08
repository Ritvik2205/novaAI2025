"""
Flask application entry point for the agentic CRM backend.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from backend.config import get_settings
from backend.repositories.memory import CRMRepository
from backend.services.openrouter_client import OpenRouterClient
from backend.services.agentuity_client import AgentuityClient
from backend.services.scheduler import CalendarService
from backend.services.rag_service import RAGService
from backend.agents.orchestrator import AgentOrchestrator
from backend.routers.company import company_bp
from backend.routers.leads import leads_bp
from backend.routers.scheduler import scheduler_bp
from backend.routers.chat import chat_bp


def create_app() -> Flask:
    """Application factory used by gunicorn, flask CLI, or scripts."""

    settings = get_settings()

    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Configure logging early.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Wire core services.
    repository = CRMRepository(settings.base_data_dir / "crm_state.json")
    openrouter_client = OpenRouterClient(settings.openrouter_api_key, settings.openrouter_base_url)
    agentuity_client = AgentuityClient(settings.agentuity_api_key, settings.agentuity_base_url)
    calendar_service = CalendarService(settings.calendar_provider, settings.calendar_credentials_path)
    rag_service = RAGService(
        persist_path=Path(settings.chroma_persist_path),
        embedder_model=settings.embedder_model,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    orchestrator = AgentOrchestrator(
        repository=repository,
        openrouter=openrouter_client,
        agentuity=agentuity_client,
        calendar=calendar_service,
        rag=rag_service,
        settings=settings,
    )

    # Store orchestrator on the app for blueprint access.
    app.config["orchestrator"] = orchestrator

    # Register API blueprints.
    app.register_blueprint(company_bp, url_prefix="/api/company")
    app.register_blueprint(leads_bp, url_prefix="/api/leads")
    app.register_blueprint(scheduler_bp, url_prefix="/api/scheduler")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")

    @app.route("/health", methods=["GET"])
    def healthcheck():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=8000, debug=True)
