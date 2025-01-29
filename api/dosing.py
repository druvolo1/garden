# File: api/dosing.py

import time
from flask import Blueprint, request, jsonify
from api.settings import load_settings
from services.relay_service import turn_on_relay, turn_off_relay
from services.dosage_service import manual_dispense

dosing_blueprint = Blueprint('dosing', __name__)

@dosing_blueprint.route('/manual', methods=['POST'])
def manual_dosage():
    """
    Handle manual dosing requests, e.g.:
    POST /api/dosage/manual
    {
      "type": "down",   # or "up"
      "amount": 5.0     # ml to dispense
    }
    """
    data = request.get_json()
    dispense_type = data.get("type")  # 'up' or 'down'
    amount_ml = data.get("amount", 0.0)

    if dispense_type not in ["up", "down"]:
        return jsonify({"status": "failure", "error": "Invalid dispense type"}), 400

    # 1. Load settings for pump calibration & relay port
    settings = load_settings()
    pump_calibration = settings.get("pump_calibration", {})
    # Decide which calibration and which relay port to use
    if dispense_type == "up":
        calibration_value = pump_calibration.get("pump1", 1.0)   # e.g. seconds/ml
        relay_port = 1  # for example, if pH Up uses Relay #1
    else:
        calibration_value = pump_calibration.get("pump2", 1.0)
        relay_port = 2  # pH Down uses Relay #2

    # OPTIONAL: If you store ports in settings["relay_ports"] e.g. {"ph_up":1,"ph_down":2}:
    # relay_ports = settings.get("relay_ports", {"ph_up":1,"ph_down":2})
    # relay_port = relay_ports["ph_up"] if dispense_type == "up" else relay_ports["ph_down"]

    # 2. Calculate how many seconds to run
    duration_sec = amount_ml * calibration_value
    if duration_sec <= 0:
        return jsonify({"status": "failure", "error": "Calculated run time is 0 or negative."}), 400

    # 3. Turn on the relay
    turn_on_relay(relay_port)
    print(f"[Manual Dispense] Turning ON Relay {relay_port} for {duration_sec:.2f} seconds...")

    # 4. Wait the required duration
    time.sleep(duration_sec)

    # 5. Turn off the relay
    turn_off_relay(relay_port)
    print(f"[Manual Dispense] Turning OFF Relay {relay_port} after {duration_sec:.2f} seconds.")

    # Optionally log via dosage_service
    manual_dispense(dispense_type, amount_ml)

    return jsonify({
        "status": "success",
        "message": f"Dispensed {amount_ml:.2f} ml of pH {dispense_type} over {duration_sec:.2f} seconds."
    })
