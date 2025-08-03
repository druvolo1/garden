# File: api/dosing.py

import time
import eventlet
from datetime import datetime
from flask import Blueprint, request, jsonify
from api.settings import load_settings
from services.log_service import log_dosing_event
from services.auto_dose_state import auto_dose_state
from services.pump_relay_service import turn_on_relay, turn_off_relay
from services.dosage_service import manual_dispense, get_dosage_info
from services.dosing_state import state  # Import the singleton instance

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
        return jsonify({"status": "failure", "message": "Invalid dispense type"}), 400

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
        return jsonify({"status": "failure", "message": "Calculated run time is 0 or negative."}), 400

    def dispense_task():
        from app import socketio  # Import here to avoid circular import
        try:
            print(f"[DEBUG ManualDispense] Setting active state: type={dispense_type}, amount={amount_ml}, duration={duration_sec}")
            # Emit start event
            socketio.emit('dose_start', {'type': dispense_type, 'amount': amount_ml, 'duration': duration_sec})
            print(f"[Manual Dispense] Turning ON Relay {relay_port} for {duration_sec:.2f} seconds...")
            turn_on_relay(relay_port)
            eventlet.sleep(duration_sec)
            turn_off_relay(relay_port)
            print(f"[Manual Dispense] Turning OFF Relay {relay_port} after {duration_sec:.2f} seconds.")
            manual_dispense(dispense_type, amount_ml)
            socketio.emit('dose_complete', {'type': dispense_type, 'amount': amount_ml})
        except Exception as e:
            print(f"[Manual Dispense] Error during dispense: {str(e)}")
            socketio.emit('dose_error', {'type': dispense_type, 'error': str(e)})
        finally:
            # Clear active task only if this is the current task
            if state.active_dosing_task and state.active_dosing_task == eventlet.getcurrent():
                print(f"[DEBUG ManualDispense] Clearing state for {dispense_type}")
                state.active_dosing_task = None
                state.active_relay_port = None
                state.active_dosing_type = None
                state.active_dosing_amount = None
                state.active_start_time = None
                state.active_duration = None
            turn_off_relay(relay_port)  # Ensure relay is off

    # Cancel any existing task
    if state.active_dosing_task:
        try:
            state.active_dosing_task.kill()
            if state.active_relay_port is not None:
                turn_off_relay(state.active_relay_port)
            print(f"[Manual Dispense] Cancelled previous dosing task: {state.active_dosing_type or 'unknown'}")
        except Exception as e:
            print(f"[Manual Dispense] Error cancelling previous task: {str(e)}")
        finally:
            print("[DEBUG ManualDispense] Cleared previous state after cancel")
            state.active_dosing_task = None
            state.active_relay_port = None
            state.active_dosing_type = None
            state.active_dosing_amount = None
            state.active_start_time = None
            state.active_duration = None

    # Start new task
    state.active_dosing_task = eventlet.spawn(dispense_task)
    state.active_relay_port = relay_port
    state.active_dosing_type = dispense_type
    state.active_dosing_amount = amount_ml
    state.active_start_time = time.time()
    state.active_duration = duration_sec
    print(f"[DEBUG ManualDispense] Started new task, state set: start_time={state.active_start_time}, duration={state.active_duration}")

    return jsonify({
        "status": "success",
        "message": f"Dosing of {amount_ml:.2f} ml of pH {dispense_type} started.",
        "duration": duration_sec
    })

@dosing_blueprint.route('/stop', methods=['POST'])
def stop_dosage():
    """
    Stop the current dosing operation.
    POST /api/dosage/stop
    {}
    """
    from app import socketio  # Import here to avoid circular import

    if not state.active_dosing_task:
        print("[Stop Dosing] No active dosing task to stop")
        return jsonify({"status": "success", "message": "No active dosing to stop."}), 200

    try:
        type_str = state.active_dosing_type or 'unknown'
        amount_str = f"{state.active_dosing_amount:.2f}" if state.active_dosing_amount is not None else 'unknown'
        print(f"[Stop Dosing] Attempting to stop dosing: {type_str}, {amount_str} ml")
        
        # Kill the active dosing task
        state.active_dosing_task.kill()
        
        # Fallback: turn off both possible relays to ensure no relay stays on
        settings = load_settings()
        relay_ports = settings.get("relay_ports", {"ph_up": 1, "ph_down": 2})
        for port in [relay_ports["ph_up"], relay_ports["ph_down"]]:
            try:
                turn_off_relay(port)
                print(f"[Stop Dosing] Turned off relay {port} as fallback")
            except Exception as e:
                print(f"[Stop Dosing] Error turning off relay {port}: {str(e)}")
        
        # Emit stopped event
        socketio.emit('dose_stopped', {
            'type': type_str,
            'amount': state.active_dosing_amount or 0
        })

        print(f"[Stop Dosing] Stopped dosing: {type_str}, {amount_str} ml")
        return jsonify({"status": "success", "message": "Dosing stopped successfully."}), 200
    except Exception as e:
        error_msg = str(e) or 'Unknown error during stopping'
        print(f"[Stop Dosing] Error stopping dosing: {error_msg}")
        # Fallback: turn off both relays
        settings = load_settings()
        relay_ports = settings.get("relay_ports", {"ph_up": 1, "ph_down": 2})
        for port in [relay_ports["ph_up"], relay_ports["ph_down"]]:
            try:
                turn_off_relay(port)
                print(f"[Stop Dosing] Turned off relay {port} as fallback on error")
            except Exception as e:
                print(f"[Stop Dosing] Error turning off relay {port} on error: {str(e)}")
        return jsonify({"status": "failure", "message": f"Failed to stop dosing: {error_msg}"}), 500
    finally:
        # Clear state to prevent stuck relays
        print("[DEBUG StopDosing] Clearing state in finally block")
        state.active_dosing_task = None
        state.active_relay_port = None
        state.active_dosing_type = None
        state.active_dosing_amount = None
        state.active_start_time = None
        state.active_duration = None