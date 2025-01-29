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
      "amount": 5.0     # ml to dispense (calculated by the UI)
    }

    If max_dosing_amount == 0 (or not set), we skip clamping entirely.
    If max_dosing_amount > 0 and amount_ml is larger, we clamp.
    """
    data = request.get_json()
    dispense_type = data.get("type")  # 'up' or 'down'
    amount_ml = data.get("amount", 0.0)

    if dispense_type not in ["up", "down"]:
        return jsonify({"status": "failure", "error": "Invalid dispense type"}), 400

    settings = load_settings()

    # 1. Check for a max dosing limit
    max_dosing = settings.get("max_dosing_amount", 0)

    # If we have a positive max_dosing, clamp the amount if it exceeds that.
    if max_dosing > 0 and amount_ml > max_dosing:
        print(f"[Dosing] Calculated amount ({amount_ml} ml) exceeds max ({max_dosing} ml). Clamping.")
        amount_ml = max_dosing
    else:
        # If max_dosing == 0 or amount_ml <= max_dosing, no clamping is applied
        pass

    # 2. Determine which pump calibration and relay port
    pump_calibration = settings.get("pump_calibration", {})
    if dispense_type == "up":
        calibration_value = pump_calibration.get("pump1", 1.0)  # seconds/ml
        relay_port = 1
    else:
        calibration_value = pump_calibration.get("pump2", 1.0)
        relay_port = 2

    # OPTIONAL: if using settings["relay_ports"], do:
    # relay_ports = settings.get("relay_ports", {"ph_up":1,"ph_down":2})
    # relay_port = relay_ports["ph_up"] if dispense_type == "up" else relay_ports["ph_down"]

    # 3. Calculate runtime in seconds
    duration_sec = amount_ml * calibration_value

    # If the user specified 0 ml, or the clamp set it to 0,
    # duration_sec could be 0 or negative. Abort in that case.
    if duration_sec <= 0:
        return jsonify({"status": "failure", "error": "Calculated run time is 0 or negative."}), 400

    # 4. Turn on the relay
    turn_on_relay(relay_port)
    print(f"[Manual Dispense] Turning ON Relay {relay_port} for {duration_sec:.2f} seconds...")

    time.sleep(duration_sec)

    # 5. Turn off the relay
    turn_off_relay(relay_port)
    print(f"[Manual Dispense] Turning OFF Relay {relay_port} after {duration_sec:.2f} seconds.")

    # Optionally log to the terminal
    manual_dispense(dispense_type, amount_ml)

    return jsonify({
        "status": "success",
        "message": f"Dispensed {amount_ml:.2f} ml of pH {dispense_type} over {duration_sec:.2f} seconds."
    })
