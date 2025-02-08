# File: api/ph.py

from flask import Blueprint, jsonify
from services.ph_service import enqueue_calibration, get_latest_ph_reading

# Create a Blueprint for the pH API
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
