"""
Ad-hoc knowledge assistant endpoints.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

chat_bp = Blueprint("chat", __name__)


def _orchestrator():
    return current_app.config["orchestrator"]


@chat_bp.post("/company/<company_id>")
def ask_company_agent(company_id: str):
    payload = request.json or {}
    question = payload.get("question")
    if not question:
        return jsonify({"error": "Question is required."}), 400
    try:
        result = _orchestrator().answer_company_question(company_id, question)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)

