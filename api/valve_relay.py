# File: api/valve_relay.py

from flask import Blueprint, request, jsonify
from services.valve_relay_service import turn_on_valve, turn_off_valve, get_valve_status

valve_relay_blueprint = Blueprint('valve_relay', __name__)

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
