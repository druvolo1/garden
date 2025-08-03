# File: services/dosage_service.py

import eventlet
from services.ph_service import get_latest_ph_reading
from services.pump_relay_service import turn_on_relay, turn_off_relay
from api.settings import load_settings
from services.log_service import log_dosing_event
from services.dosing_state import state  # CHANGED: Import the singleton instance instead of individual globals

def get_dosage_info():
    current_ph = get_latest_ph_reading()
    if current_ph is None:
        current_ph = 0.0

    settings = load_settings()
    system_volume = settings.get("system_volume", 0)
    auto_dosing_enabled = settings.get("auto_dosing_enabled", False)
    ph_target = settings.get("ph_target", 5.8)

    dosage_strength = settings.get("dosage_strength", {})
    ph_up_strength = dosage_strength.get("ph_up", 1.0)
    ph_down_strength = dosage_strength.get("ph_down", 1.0)

    max_dosing_amount = settings.get("max_dosing_amount", 0)

    ph_up_amount = 0.0
    ph_down_amount = 0.0
    feedback_up = ""
    feedback_down = ""

    if current_ph < ph_target:
        ph_diff = ph_target - current_ph
        calculated_up = ph_up_strength * ph_diff * system_volume
        if max_dosing_amount > 0 and calculated_up > max_dosing_amount:
            feedback_up = (
                f"The actual calculated dose ({calculated_up:.2f} ml) exceeds the "
                f"max dosing amount in <a href=\"/settings\">Settings</a>. "
                f"Clamping to {max_dosing_amount:.2f} ml."
            )
            ph_up_amount = max_dosing_amount
        else:
            ph_up_amount = calculated_up

    if current_ph > ph_target:
        ph_diff = current_ph - ph_target
        calculated_down = ph_down_strength * ph_diff * system_volume
        if max_dosing_amount > 0 and calculated_down > max_dosing_amount:
            feedback_down = (
                f"The actual calculated dose ({calculated_down:.2f} ml) exceeds the "
                f"max dosing amount in <a href=\"/settings\">Settings</a>. "
                f"Clamping to {max_dosing_amount:.2f} ml."
            )
            ph_down_amount = max_dosing_amount
        else:
            ph_down_amount = calculated_down

    return {
        "current_ph": round(current_ph, 2),
        "system_volume": system_volume,
        "auto_dosing_enabled": auto_dosing_enabled,
        "ph_target": ph_target,
        "ph_up_amount": round(ph_up_amount, 2),
        "ph_down_amount": round(ph_down_amount, 2),
        "feedback_up": feedback_up,
        "feedback_down": feedback_down
    }

def manual_dispense(dispense_type, amount):
    current_ph = get_latest_ph_reading() or 'N/A'
    print(f"[Manual Dispense] Requested to dispense {amount} ml of pH {dispense_type.capitalize()}.")
    log_dosing_event(current_ph, dispense_type, amount_ml)
    return True

# -----------------------------
# AUTO-DOSING LOGIC BELOW
# -----------------------------
def perform_auto_dose(settings):
    """
    Checks the current pH reading against the acceptable range (from settings["ph_range"])
    and dispenses pH Up if the value is below the minimum or pH Down if above the maximum.
    Returns a tuple (direction, dose_ml) if a dose is performed, otherwise ("none", 0.0).
    """
    ph_value = get_latest_ph_reading()
    if ph_value is None:
        print("[AutoDosing] No pH reading available; skipping auto-dose.")
        return ("none", 0.0)

    # Get the acceptable pH range from settings.
    ph_range = settings.get("ph_range", {})
    try:
        min_ph = float(ph_range.get("min", 5.5))
        max_ph = float(ph_range.get("max", 6.5))
    except ValueError:
        print("[AutoDosing] Error converting ph_range values; using defaults.")
        min_ph, max_ph = 5.5, 6.5

    # Check if the current pH is below the minimum or above the maximum.
    if ph_value < min_ph:
        # pH is too low – we need to raise it (dispense pH up)
        dosage_data = get_dosage_info()  # Make sure this uses the correct logic, if needed.
        dose_ml = dosage_data.get("ph_up_amount", 0)
        if dose_ml <= 0:
            return ("none", 0.0)
        do_relay_dispense("up", dose_ml, settings)
        print(f"[AutoDosing] pH {ph_value} is below minimum {min_ph}: dispensing {dose_ml} ml of pH Up.")
        return ("up", dose_ml)
    elif ph_value > max_ph:
        # pH is too high – we need to lower it (dispense pH down)
        dosage_data = get_dosage_info()
        dose_ml = dosage_data.get("ph_down_amount", 0)
        if dose_ml <= 0:
            return ("none", 0.0)
        do_relay_dispense("down", dose_ml, settings)
        print(f"[AutoDosing] pH {ph_value} is above maximum {max_ph}: dispensing {dose_ml} ml of pH Down.")
        return ("down", dose_ml)
    else:
        print(f"[AutoDosing] pH ({ph_value}) within acceptable range ({min_ph} - {max_ph}); skipping auto dose.")
        return ("none", 0.0)


def do_relay_dispense(dispense_type, amount_ml, settings):
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
        print(f"[AutoDosing] Calculated run time is 0 for {dispense_type}, skipping.")
        return

    print(f"[AutoDosing] Dispensing {amount_ml:.2f} ml pH {dispense_type} -> Relay {relay_port}, ~{duration_sec:.2f}s")
    turn_on_relay(relay_port)
    eventlet.sleep(duration_sec)   # Non-blocking Eventlet sleep
    turn_off_relay(relay_port)

    # Reuse manual_dispense() for logging
    manual_dispense(dispense_type, amount_ml)
