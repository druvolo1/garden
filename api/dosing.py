# File: api/dosing.py

import time
import eventlet
from datetime import datetime
from flask import Blueprint, request, jsonify
from api.settings import load_settings
from services.auto_dose_state import auto_dose_state
from services.relay_service import turn_on_relay, turn_off_relay
from services.dosage_service import manual_dispense, get_dosage_info

dosing_blueprint = Blueprint('dosing', __name__)

@dosing_blueprint.route('/info', methods=['GET'])
def get_current_dosage_info():
    """
    Returns the latest dosage info (pH up/down amounts, current pH, etc.)
    and also includes auto-dosing fields like last_dose_time, next_dose_time.
    """
    dosage_data = get_dosage_info()

    # Merge auto_dose_state just like app.py
    if auto_dose_state["last_dose_time"]:
        dosage_data["last_dose_time"] = auto_dose_state["last_dose_time"].strftime("%Y-%m-%d %H:%M:%S")
    else:
        dosage_data["last_dose_time"] = "Never"

    dosage_data["last_dose_type"] = auto_dose_state["last_dose_type"] or "N/A"
    dosage_data["last_dose_amount"] = auto_dose_state["last_dose_amount"]

    if auto_dose_state["next_dose_time"]:
        dosage_data["next_dose_time"] = auto_dose_state["next_dose_time"].strftime("%Y-%m-%d %H:%M:%S")
    else:
        dosage_data["next_dose_time"] = "Not Scheduled"

    return jsonify(dosage_data)

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

    settings = load_settings()
    max_dosing = settings.get("max_dosing_amount", 0)
    if max_dosing > 0 and amount_ml > max_dosing:
        amount_ml = max_dosing

    pump_calibration = settings.get("pump_calibration", {})
    relay_ports = settings.get("relay_ports", {"ph_up": 1, "ph_down": 2})

    if dispense_type == "up":
        calibration_value = pump_calibration.get("pump1", 1.0)
        relay_port = relay_ports["ph_up"]
    else:
        calibration_value = pump_calibration.get("pump2", 1.0)
        relay_port = relay_ports["ph_down"]

    duration_sec = amount_ml * calibration_value
    if duration_sec <= 0:
        return jsonify({"status": "failure", "error": "Calculated run time is 0 or negative."}), 400

    turn_on_relay(relay_port)
    print(f"[Manual Dispense] Turning ON Relay {relay_port} for {duration_sec:.2f} seconds...")
    eventlet.sleep(duration_sec)
    turn_off_relay(relay_port)
    print(f"[Manual Dispense] Turning OFF Relay {relay_port} after {duration_sec:.2f} seconds.")

    manual_dispense(dispense_type, amount_ml)

    return jsonify({
        "status": "success",
        "message": f"Dispensed {amount_ml:.2f} ml of pH {dispense_type} over {duration_sec:.2f} seconds."
    })
