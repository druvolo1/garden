# File: api/dosing.py

import time
from flask import Blueprint, request, jsonify
from services.dosage_service import manual_dispense
from services.pump_service import run_pump
from api.settings import load_settings

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
    dispense_type = data.get("type")  # "up" or "down"
    amount_ml = data.get("amount", 0.0)

    if dispense_type not in ["up", "down"]:
        return jsonify({"status": "failure", "error": "Invalid dispense type"}), 400

    # 1. Load settings to get pump calibration
    settings = load_settings()
    pump_calibration = settings.get("pump_calibration", {})
    # For now, pH Up => pump1, pH Down => pump2
    if dispense_type == "up":
        calibration_value = pump_calibration.get("pump1", 1.0)  # Default to 1.0 if missing
        pump_id = "ph_up"  # The ID used in pump_service's PUMP_GPIO_PINS
    else:
        calibration_value = pump_calibration.get("pump2", 1.0)
        pump_id = "ph_down"

    # 2. Calculate how long to run the pump in seconds
    duration_sec = amount_ml * calibration_value

    # 3. Run the pump
    success = run_pump(pump_id, duration_sec)

    # 4. Print to terminal
    print(f"[Manual Dispense] Type={dispense_type}, Amount={amount_ml} ml, "
          f"Calibration={calibration_value}, Duration={duration_sec:.2f} sec")

    if success:
        # Optionally log via your dosage_service
        manual_dispense(dispense_type, amount_ml)
        return jsonify({
            "status": "success",
            "message": f"Dispensed {amount_ml:.2f} ml pH {dispense_type} over {duration_sec:.2f} seconds."
        })
    else:
        return jsonify({"status": "failure", "error": "Pump error occurred"}), 500
