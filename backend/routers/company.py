"""
Company onboarding and knowledge endpoints.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

company_bp = Blueprint("company", __name__)


def _orchestrator():
    return current_app.config["orchestrator"]


@company_bp.get("")
def list_companies():
    orchestrator = _orchestrator()
    companies = orchestrator.repository.list_companies()
    return jsonify([company.model_dump(mode="json") for company in companies])


@company_bp.post("/session")
def start_onboarding():
    payload = request.json or {}
    required_fields = {"name"}
    missing = required_fields - payload.keys()
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    result = _orchestrator().start_onboarding(payload)
    return jsonify(result), 201


@company_bp.post("/session/<session_id>/answer")
def answer_onboarding(session_id: str):
    payload = request.json or {}
    answer = payload.get("answer")
    if not answer:
        return jsonify({"error": "Answer field is required."}), 400

    try:
        result = _orchestrator().answer_onboarding(session_id, answer)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@company_bp.post("/<company_id>/documents")
def upload_documents(company_id: str):
    files = request.files.getlist("documents")
    if not files:
        return jsonify({"error": "No documents provided."}), 400
    try:
        result = _orchestrator().ingest_uploaded_files(company_id, files)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result), 201


@company_bp.get("/<company_id>/documents")
def list_documents(company_id: str):
    try:
        documents = _orchestrator().list_company_documents(company_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"documents": documents})


@company_bp.post("/<company_id>/urls")
def ingest_urls(company_id: str):
    payload = request.json or {}
    urls = payload.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided."}), 400
    try:
        result = _orchestrator().ingest_urls(company_id, urls)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@company_bp.get("/<company_id>/knowledge")
def query_knowledge(company_id: str):
    question = request.args.get("q")
    if not question:
        return jsonify({"error": "Query parameter 'q' is required."}), 400
    try:
        result = _orchestrator().query_knowledge(company_id, question)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@company_bp.get("/<company_id>")
def get_company(company_id: str):
    orchestrator = _orchestrator()
    company = orchestrator.repository.get_company(company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404
    return jsonify(company.model_dump(mode="json"))


@company_bp.get("/<company_id>/groups")
def list_groups(company_id: str):
    try:
        groups = _orchestrator().list_student_groups(company_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"student_groups": groups})


@company_bp.get("/<company_id>/knowledge/sections")
def knowledge_sections(company_id: str):
    try:
        result = _orchestrator().generate_knowledge_sections(company_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@company_bp.post("/<company_id>/knowledge/visibility")
def update_visibility(company_id: str):
    payload = request.json or {}
    internal_only = payload.get("internal_only", [])
    if not isinstance(internal_only, list):
        return jsonify({"error": "internal_only must be an array of section titles"}), 400
    try:
        result = _orchestrator().update_knowledge_visibility(
            company_id, [str(title) for title in internal_only]
        )
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)

