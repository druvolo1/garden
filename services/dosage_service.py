# File: services/dosage_service.py

from services.ph_service import get_latest_ph_reading
from api.settings import load_settings

def get_dosage_info():
    """
    Returns a dictionary of dosage-related info:
      - current pH
      - system volume
      - auto-dosing enabled
      - pH target
      - calculated pH Up dosage (clamped if needed)
      - calculated pH Down dosage (clamped if needed)
      - feedback_up (a message if pH Up was clamped)
      - feedback_down (a message if pH Down was clamped)
    """
    current_ph = get_latest_ph_reading()
    if current_ph is None:
        current_ph = 0.0  # Use 0 or some default if not available

    settings = load_settings()
    system_volume = settings.get("system_volume", 0)
    auto_dosing_enabled = settings.get("auto_dosing_enabled", False)
    ph_target = settings.get("ph_target", 5.8)

    # Retrieve separate strengths for pH Up and pH Down
    dosage_strength = settings.get("dosage_strength", {})
    ph_up_strength = dosage_strength.get("ph_up", 1.0)
    ph_down_strength = dosage_strength.get("ph_down", 1.0)

    # Retrieve max dosing limit
    max_dosing_amount = settings.get("max_dosing_amount", 0)

    # Initialize amounts
    ph_up_amount = 0.0
    ph_down_amount = 0.0

    # Initialize feedback messages
    feedback_up = ""
    feedback_down = ""

    # ---- pH UP Calculation ----
    if current_ph < ph_target:
        ph_difference = ph_target - current_ph
        calculated_up = (ph_up_strength * ph_difference) * system_volume

        # Only clamp if max_dosing_amount > 0
        if max_dosing_amount > 0 and calculated_up > max_dosing_amount:
            feedback_up = (
                f"The actual calculated dose ({calculated_up:.2f} ml) exceeds the "
                f"max dosing amount in <a href=\"/settings\">Settings</a>. "
                f"Clamping to {max_dosing_amount:.2f} ml."
            )
            ph_up_amount = max_dosing_amount
        else:
            ph_up_amount = calculated_up

    # ---- pH DOWN Calculation ----
    if current_ph > ph_target:
        ph_difference = current_ph - ph_target
        calculated_down = (ph_down_strength * ph_difference) * system_volume

        # Only clamp if max_dosing_amount > 0
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
    """
    Simple placeholder for manually dispensing.
    For now, just print a line to the terminal with the type (up/down) and amount.
    """
    print(f"[Manual Dispense] Requested to dispense {amount} ml of pH {dispense_type.capitalize()}.")
    return True
