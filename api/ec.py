# File: api/ec.py

from flask import Blueprint, jsonify
from services.ec_service import get_latest_ec_reading, enqueue_calibration_command

ec_blueprint = Blueprint('ec', __name__)

@ec_blueprint.route('/', methods=['GET'])
def ec_reading():
    """
    Get the current EC value (just for debugging).
    """
    ec_value = get_latest_ec_reading()

    if ec_value is None:
        return jsonify({
            "status": "error",
            "message": "No EC reading available. Check if an EC meter is assigned and connected."
        }), 404

    return jsonify({
        "status": "success",
        "ec": ec_value
    })

@ec_blueprint.route('/calibrate/<level>', methods=['POST'])
def ec_calibration(level):
    """
    Calibrate the EC sensor.
    Valid levels: "dry", "low", "high", "clear"
    """
    response = enqueue_calibration_command(level)
    if response["status"] == "success":
        return jsonify(response)
    return jsonify(response), 400

@ec_blueprint.route('/latest', methods=['GET'])
def latest_ec():
    """
    API endpoint to get the latest EC value.
    """
    ec_value = get_latest_ec_reading()
    if ec_value is not None:
        return jsonify({'ec': ec_value}), 200
    return jsonify({'error': 'No EC reading available'}), 404
