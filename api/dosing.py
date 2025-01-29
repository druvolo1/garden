# File: api/dosing.py

from flask import Blueprint, request, jsonify
from services.dosage_service import manual_dispense
from services.pump_service import run_pump

dosing_blueprint = Blueprint('dosing', __name__)

@dosing_blueprint.route('/manual', methods=['POST'])
def manual_dosage():
    """
    Handle manual dosing requests, e.g.:
    POST /api/dosage/manual
    {
      "type": "down",  # or "up"
      "amount": 5.0    # ml to dispense
    }
    """
    data = request.get_json()
    dispense_type = data.get("type")     # "up" or "down"
    amount_ml = data.get("amount", 0)    # The ml from the UI

    if dispense_type not in ["up", "down"]:
        return jsonify({"status": "failure", "error": "Invalid dispense type"}), 400

    # For now, just print/log a message like you do in manual_dispense
    # and optionally call run_pump() if you want to activate the pump hardware.
    # We'll assume 'ph_up' is for up, 'ph_down' for down. You can rename as needed.
    
    # Example: convert ml -> seconds (just a placeholder)
    seconds_to_run = ml_to_seconds(dispense_type, amount_ml)

    # Attempt to run pump
    pump_id = "ph_down" if dispense_type == "down" else "ph_up"
    success = run_pump(pump_id, seconds_to_run)
    if success:
        # Log the manual dispensing
        manual_dispense(dispense_type, amount_ml)  
        return jsonify({
            "status": "success", 
            "message": f"Dispensed {amount_ml} ml of pH {dispense_type.capitalize()} (for ~{seconds_to_run:.2f} sec)."
        })
    else:
        return jsonify({"status": "failure", "error": "Pump error occurred"}), 500

def ml_to_seconds(dispense_type, ml):
    """
    Convert ml into seconds based on pump calibration from settings.json (optional).
    For now, just do a simple 1 ml = 1 second approach.
    """
    return float(ml)
