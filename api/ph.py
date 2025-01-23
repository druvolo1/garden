from flask import Blueprint, jsonify
from services.ph_service import get_ph_reading, calibrate_ph

ph_blueprint = Blueprint('ph', __name__)

@ph_blueprint.route('/', methods=['GET'])
def ph_reading():
    """Get the current pH value."""
    return jsonify({"ph": get_ph_reading()})

@ph_blueprint.route('/calibrate/<level>', methods=['POST'])
def ph_calibration(level):
    """Calibrate the pH sensor at a specific level (low/mid/high)."""
    if calibrate_ph(level):
        return jsonify({"status": "success"})
    return jsonify({"status": "failure", "error": "Invalid level"}), 400
