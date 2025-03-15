# File: api/notifications.py

from flask import Blueprint, request, jsonify, render_template
from services.notification_service import (
    get_all_notifications,
    set_status,
    clear_status
)

notifications_blueprint = Blueprint("notifications", __name__)

@notifications_blueprint.route('/', methods=['GET'])
def get_notifications():
    """
    Returns all current notifications as JSON.
    """
    all_notes = get_all_notifications()
    return jsonify({"status": "success", "notifications": all_notes})

@notifications_blueprint.route('/set', methods=['POST'])
def api_set_status():
    """
    POST JSON like:
    {
      "device": "ph_probe",
      "key": "communication",
      "state": "error",
      "message": "unable to open port"
    }
    """
    data = request.get_json() or {}
    device = data.get("device", "").strip()
    key = data.get("key", "").strip()
    state = data.get("state", "").strip()
    message = data.get("message", "").strip()

    if not device or not key or not state:
        return jsonify({"status": "failure", "error": "device, key, and state are required"}), 400

    set_status(device, key, state, message)
    return jsonify({"status": "success"})

@notifications_blueprint.route('/clear', methods=['POST'])
def api_clear_status():
    """
    POST JSON like:
    {
      "device": "ph_probe",
      "key": "communication"
    }
    """
    data = request.get_json() or {}
    device = data.get("device", "").strip()
    key = data.get("key", "").strip()

    if not device or not key:
        return jsonify({"status": "failure", "error": "device and key are required"}), 400

    clear_status(device, key)
    return jsonify({"status": "success"})



