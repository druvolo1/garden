from flask import Blueprint, jsonify
from services.relay_service import turn_on_relay, turn_off_relay, get_relay_status

relay_blueprint = Blueprint('relay', __name__)

@relay_blueprint.route('/on', methods=['POST'])
def relay_on():
    """Turn on a specific relay."""
    data = request.json
    relay = data.get("relay")
    turn_on_relay(relay)
    return jsonify({"status": "success"})

@relay_blueprint.route('/off', methods=['POST'])
def relay_off():
    """Turn off a specific relay."""
    data = request.json
    relay = data.get("relay")
    turn_off_relay(relay)
    return jsonify({"status": "success"})

@relay_blueprint.route('/status', methods=['GET'])
def relay_status():
    """Get the status of all relays."""
    return jsonify(get_relay_status())
