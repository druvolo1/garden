# File: api/ph.py

from flask import Blueprint, jsonify, request
from services.ph_service import enqueue_calibration, get_latest_ph_reading
from utils.settings_utils import load_settings, save_settings

ph_blueprint = Blueprint('ph', __name__)

@ph_blueprint.route('/', methods=['GET'])
def ph_reading():
    """
    Get the current pH value.
    """
    ph_value = get_latest_ph_reading()
    if ph_value is None:
        return jsonify({
            "status": "error",
            "message": "No pH reading available. Check if a pH probe is assigned and connected."
        }), 404

    return jsonify({
        "status": "success",
        "ph": ph_value
    })

@ph_blueprint.route('/calibrate/<level>', methods=['POST'])
def ph_calibration(level):
    """
    Calibrate the pH sensor at a specific level (low, mid, high, or clear).
    """
    response = enqueue_calibration(level)
    if response["status"] == "success":
        return jsonify(response)
    return jsonify(response), 400

@ph_blueprint.route('/latest', methods=['GET'])
def latest_ph():
    """API endpoint to get the latest pH value."""
    ph_value = get_latest_ph_reading()
    if ph_value is not None:
        return jsonify({'ph': ph_value}), 200
    return jsonify({'error': 'No pH reading available'}), 404


# NEW ENDPOINT for storing user-selected calibration date
@ph_blueprint.route('/calibration_date', methods=['POST'])
def set_ph_calibration_date():
    """
    Allows the user to pick a date from the UI and store it in settings["calibration"]["ph_probe"]["manual_cal_date"].
    JSON input example: { "date": "2025-03-15" }
    """
    data = request.get_json() or {}
    chosen_date = data.get("date")

    if not chosen_date:
        return jsonify({"status": "failure", "error": "No date provided"}), 400

    # Save to settings
    s = load_settings()
    if "calibration" not in s:
        s["calibration"] = {}
    if "ph_probe" not in s["calibration"]:
        s["calibration"]["ph_probe"] = {}

    # We'll just store it as a string. If you want to parse/validate further, you can do so here.
    s["calibration"]["ph_probe"]["manual_cal_date"] = chosen_date

    save_settings(s)

    return jsonify({"status": "success", "date": chosen_date})
