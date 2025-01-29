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
      - calculated pH Up dosage
      - calculated pH Down dosage
    """
    current_ph = get_latest_ph_reading()
    if current_ph is None:
        current_ph = 0.0  # Use 0 or some default if not available

    settings = load_settings()
    system_volume = settings.get("system_volume", 0)
    auto_dosing_enabled = settings.get("auto_dosing_enabled", False)
    ph_target = settings.get("ph_target", 5.8)

    # Retrieve separate strengths for pH Up and pH Down from the settings
    dosage_strength = settings.get("dosage_strength", {})
    ph_up_strength = dosage_strength.get("ph_up", 1.0)      # Default to 1.0 if missing
    ph_down_strength = dosage_strength.get("ph_down", 1.0)  # Default to 1.0 if missing

    # Initialize amounts
    ph_up_amount = 0.0
    ph_down_amount = 0.0

    # Calculate pH Up amount if current pH is below target
    if current_ph < ph_target:
        ph_difference = ph_target - current_ph
        ph_up_amount = (ph_up_strength * ph_difference) * system_volume

    # Calculate pH Down amount if current pH is above target
    if current_ph > ph_target:
        ph_difference = current_ph - ph_target
        ph_down_amount = (ph_down_strength * ph_difference) * system_volume

    return {
        "current_ph": round(current_ph, 2),
        "system_volume": system_volume,
        "auto_dosing_enabled": auto_dosing_enabled,
        "ph_target": ph_target,
        "ph_up_amount": round(ph_up_amount, 2),
        "ph_down_amount": round(ph_down_amount, 2),
    }

def manual_dispense(dispense_type, amount):
    """
    Simple placeholder for manually dispensing.
    For now, just print a line to the terminal with the type (up/down) and amount.
    """
    print(f"[Manual Dispense] Requested to dispense {amount} ml of pH {dispense_type.capitalize()}.")
    return True
