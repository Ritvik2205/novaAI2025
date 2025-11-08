"""
Scheduling and availability endpoints.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

scheduler_bp = Blueprint("scheduler", __name__)


def _orchestrator():
    return current_app.config["orchestrator"]


@scheduler_bp.post("/<company_id>/availability")
def set_availability(company_id: str):
    payload = request.json or {}
    windows = payload.get("windows", [])
    if not isinstance(windows, list):
        return jsonify({"error": "windows must be a list of start/end dicts"}), 400
    _orchestrator().set_availability(company_id, windows)
    return jsonify({"status": "ok"})


@scheduler_bp.get("/<company_id>/availability")
def get_availability(company_id: str):
    availability = _orchestrator().calendar.get_availability(company_id)
    return jsonify({"windows": availability})

