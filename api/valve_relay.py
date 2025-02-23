# File: api/valve_relay.py

from flask import Blueprint, request, jsonify
from services.valve_relay_service import (
    turn_on_valve, turn_off_valve, get_valve_status
)
from utils.settings_utils import load_settings, save_settings

valve_relay_blueprint = Blueprint('valve_relay', __name__)

# -------------------------
# Numeric ID-based control
# -------------------------
@valve_relay_blueprint.route('/<int:valve_id>/on', methods=['POST'])
def valve_on(valve_id):
    try:
        turn_on_valve(valve_id)
        return jsonify({"status": "success", "valve_id": valve_id, "action": "on"})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@valve_relay_blueprint.route('/<int:valve_id>/off', methods=['POST'])
def valve_off(valve_id):
    try:
        turn_off_valve(valve_id)
        return jsonify({"status": "success", "valve_id": valve_id, "action": "off"})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@valve_relay_blueprint.route('/<int:valve_id>/status', methods=['GET'])
def valve_status(valve_id):
    try:
        status = get_valve_status(valve_id)
        return jsonify({"status": "success", "valve_id": valve_id, "valve_status": status})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

# -------------------------
# Name-based control
# -------------------------
@valve_relay_blueprint.route('/<string:valve_name>/on', methods=['POST'])
def valve_on_by_name(valve_name):
    try:
        valve_id = get_valve_id_by_name(valve_name)
        if valve_id is None:
            return jsonify({"status": "failure", "error": f"No valve found with name '{valve_name}'"}), 404
        turn_on_valve(valve_id)
        return jsonify({"status": "success", "valve_name": valve_name, "action": "on"})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@valve_relay_blueprint.route('/<string:valve_name>/off', methods=['POST'])
def valve_off_by_name(valve_name):
    try:
        valve_id = get_valve_id_by_name(valve_name)
        if valve_id is None:
            return jsonify({"status": "failure", "error": f"No valve found with name '{valve_name}'"}), 404
        turn_off_valve(valve_id)
        return jsonify({"status": "success", "valve_name": valve_name, "action": "off"})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@valve_relay_blueprint.route('/<string:valve_name>/status', methods=['GET'])
def valve_status_by_name(valve_name):
    try:
        valve_id = get_valve_id_by_name(valve_name)
        if valve_id is None:
            return jsonify({"status": "failure", "error": f"No valve found with name '{valve_name}'"}), 404
        status = get_valve_status(valve_id)
        return jsonify({"status": "success", "valve_name": valve_name, "valve_status": status})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

# -------------------------
# Label Management & Status
# -------------------------
@valve_relay_blueprint.route('/all_status', methods=['GET'])
def all_valve_status():
    """
    Returns a dictionary of all valve IDs + labels + statuses.
    Example:
      {
        "status": "success",
        "valves": {
          "1": {"label": "Fill Valve", "status": "on"},
          "2": {"label": "Drain Valve", "status": "off"},
          ...
        }
      }
    """
    settings = load_settings()
    valve_labels = settings.get("valve_labels", {})  # e.g. {"1": "Fill", "2": "Drain"}
    result = {}

    # We have up to 8 valves, but you can adjust if you want more or fewer
    for valve_id_str in valve_labels:
        valve_id = int(valve_id_str)
        label = valve_labels[valve_id_str]
        status = get_valve_status(valve_id)
        result[valve_id_str] = {"label": label, "status": status}

    return jsonify({"status": "success", "valves": result})

@valve_relay_blueprint.route('/label/<int:valve_id>', methods=['POST'])
def set_valve_label(valve_id):
    """
    Assigns a custom name/label to the given valve ID.
    JSON payload: {"label": "Fill Valve"}
    """
    data = request.get_json() or {}
    new_label = data.get("label")
    if not new_label:
        return jsonify({"status": "failure", "error": "No label provided"}), 400

    try:
        settings = load_settings()
        if "valve_labels" not in settings:
            settings["valve_labels"] = {}
        # Store as a string
        settings["valve_labels"][str(valve_id)] = new_label
        save_settings(settings)
        return jsonify({"status": "success", "valve_id": valve_id, "label": new_label})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

# -------------------------
# Helpers
# -------------------------
def get_valve_id_by_name(valve_name):
    """
    Look up the numeric valve ID by its name/label in settings["valve_labels"].
    Returns None if no match is found.
    """
    settings = load_settings()
    labels = settings.get("valve_labels", {})
    for valve_id_str, label in labels.items():
        if label.lower() == valve_name.lower():
            return int(valve_id_str)
    return None
