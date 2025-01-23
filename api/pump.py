from flask import Blueprint, jsonify, request
from services.pump_service import run_pump

pump_blueprint = Blueprint('pump', __name__)

@pump_blueprint.route('/run', methods=['POST'])
def run_pump_endpoint():
    """Run a pump for a specific amount of time."""
    data = request.json
    pump = data.get("pump")
    time_sec = data.get("time_sec")

    if run_pump(pump, time_sec):
        return jsonify({"status": "success"})
    return jsonify({"status": "failure"}), 400
