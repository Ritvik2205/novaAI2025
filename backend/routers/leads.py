"""
Lead lifecycle endpoints.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

leads_bp = Blueprint("leads", __name__)


def _orchestrator():
    return current_app.config["orchestrator"]


@leads_bp.post("/message")
def inbound_message():
    payload = request.json or {}
    required = {"message"}
    missing = {field for field in required if not payload.get(field)}
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        result = _orchestrator().handle_inbound_message(payload)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@leads_bp.get("")
def list_leads():
    company_id = request.args.get("company_id")
    result = _orchestrator().list_leads(company_id)
    return jsonify(result)


@leads_bp.get("/<lead_id>")
def get_lead(lead_id: str):
    try:
        result = _orchestrator().get_lead(lead_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(result)


@leads_bp.post("/<lead_id>/handoff")
def handoff_lead(lead_id: str):
    payload = request.json or {}
    decision = payload.get("decision")
    group_id = payload.get("group_id")
    try:
        result = _orchestrator().handoff_lead(lead_id, group_id, decision)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)

