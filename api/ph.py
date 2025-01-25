from flask import Blueprint, jsonify
from services.ph_service import get_latest_ph_reading, calibrate_ph

ph_blueprint = Blueprint('ph', __name__)

@ph_blueprint.route('/', methods=['GET'])
def ph_reading():
    """Get the current pH value."""
    ph_value = get_ph_reading()

    if ph_value is None:
        # Handle cases where no device is assigned or there's an error
        return jsonify({
            "status": "error",
            "error": "No pH reading available. Check if a pH probe is assigned and connected."
        }), 400

    return jsonify({
        "status": "success",
        "ph": ph_value
    })

@ph_blueprint.route('/calibrate/<level>', methods=['POST'])
def ph_calibration(level):
    """Calibrate the pH sensor at a specific level (low/mid/high)."""
    success = calibrate_ph(level)

    if success:
        return jsonify({"status": "success"})
    
    return jsonify({
        "status": "failure",
        "error": "Invalid level or no pH probe assigned."
    }), 400
