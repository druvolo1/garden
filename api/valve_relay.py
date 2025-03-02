from flask import Blueprint, request, jsonify
from services.valve_relay_service import (
    turn_on_valve, turn_off_valve, get_valve_status
)
from utils.settings_utils import load_settings, save_settings
# NEW: Import emit_status_update
from status_namespace import emit_status_update

valve_relay_blueprint = Blueprint('valve_relay', __name__)

# -------------------------
# Numeric ID-based control
# -------------------------
@valve_relay_blueprint.route('/<int:valve_id>/on', methods=['POST'])
def valve_on(valve_id):
    try:
        turn_on_valve(valve_id)
        # Emit status_update so clients see changes immediately
        emit_status_update()
        return jsonify({"status": "success", "valve_id": valve_id, "action": "on"})
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@valve_relay_blueprint.route('/<int:valve_id>/off', methods=['POST'])
def valve_off(valve_id):
    try:
        turn_off_valve(valve_id)
        emit_status_update()
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
    """
    1) Try to handle valve locally. 
    2) If no local valve found, pass through to remote water_valve_ip, if assigned.
    """
    settings = load_settings()
    local_id = get_valve_id_by_name(valve_name)

    if local_id is not None:
        # We have a local valve. Turn it on as usual.
        try:
            turn_on_valve(local_id)
            emit_status_update()
            return jsonify({"status": "success", "valve_name": valve_name, "action": "on"})
        except Exception as e:
            return jsonify({"status": "failure", "error": str(e)}), 500

    # No local valve found => check if we have remote water_valve_ip assigned
    remote_ip = settings.get("water_valve_ip")
    if not remote_ip:
        # No local valve, no remote IP => can't handle
        return jsonify({"status": "failure", 
                        "error": f"No local valve named '{valve_name}', and no water_valve_ip configured."}), 404

    # We do have remote_ip => forward the request
    try:
        remote_url = f"http://{remote_ip}:8000/api/valve_relay/{valve_name}/on"
        resp = requests.post(remote_url)
        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "success":
            # Optionally emit_status_update here, if you want local clients 
            # to learn about remote changes
            emit_status_update()
            return jsonify(data), 200
        else:
            # forward the error from remote
            return jsonify({"status":"failure",
                            "error": data.get("error", "Remote call failed")}), resp.status_code
    except Exception as e:
        return jsonify({"status":"failure","error":str(e)}), 500


@valve_relay_blueprint.route('/<string:valve_name>/off', methods=['POST'])
def valve_off_by_name(valve_name):
    """
    1) Try to handle valve locally. 
    2) If no local valve found, pass through to remote water_valve_ip, if assigned.
    """
    settings = load_settings()
    local_id = get_valve_id_by_name(valve_name)

    if local_id is not None:
        # Local valve
        try:
            turn_off_valve(local_id)
            emit_status_update()
            return jsonify({"status": "success", "valve_name": valve_name, "action": "off"})
        except Exception as e:
            return jsonify({"status": "failure", "error": str(e)}), 500

    # No local valve => attempt pass-through
    remote_ip = settings.get("water_valve_ip")
    if not remote_ip:
        return jsonify({"status": "failure", 
                        "error": f"No local valve named '{valve_name}', and no water_valve_ip configured."}), 404

    try:
        remote_url = f"http://{remote_ip}:8000/api/valve_relay/{valve_name}/off"
        resp = requests.post(remote_url)
        data = resp.json()
        if resp.status_code == 200 and data.get("status") == "success":
            emit_status_update()
            return jsonify(data), 200
        else:
            return jsonify({"status":"failure",
                            "error": data.get("error","Remote call failed")}), resp.status_code
    except Exception as e:
        return jsonify({"status":"failure","error":str(e)}), 500

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
    Returns a dictionary of all valves (1..8) with label + status.
    Example:
      {
        "status": "success",
        "valves": {
          "1": {"label": "Fill Valve", "status": "on"},
          "2": {"label": "Drain Valve", "status": "off"},
          ...
          "8": {"label": "", "status": "off"}
        }
      }
    """
    settings = load_settings()
    valve_labels = settings.get("valve_labels", {})  # e.g. {"1":"Fill","2":"Drain"}
    result = {}

    # Always include valves 1..8
    for i in range(1, 9):
        valve_id_str = str(i)
        label = valve_labels.get(valve_id_str, "")
        status = get_valve_status(i)   # e.g. "on" or "off"
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
# New API: List Valve Names
# -------------------------
@valve_relay_blueprint.route('/list_names', methods=['GET'])
def list_valve_names():
    """
    Returns a list of all valve names/labels.
    Example:
      {
        "status": "success",
        "valve_names": ["Fill Valve", "Drain Valve", ...]
      }
    """
    settings = load_settings()
    valve_labels = settings.get("valve_labels", {})  # e.g. {"1": "Fill", "2": "Drain"}
    valve_names = list(valve_labels.values())  # Extract the names/labels

    return jsonify({"status": "success", "valve_names": valve_names})

# -------------------------
# Helpers
# -------------------------
def get_valve_id_by_name(valve_name):
    """
    If the label is found in local settings["valve_labels"], return numeric ID.
    Otherwise return None.
    """
    settings = load_settings()
    labels = settings.get("valve_labels", {})
    for valve_id_str, label in labels.items():
        if label.lower() == valve_name.lower():
            return int(valve_id_str)
    return None
