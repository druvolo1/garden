# File: services/dosage_service.py

from services.ph_service import get_latest_ph_reading
from api.settings import load_settings

def get_dosage_info():
    """
    Returns a dictionary of dosage-related info that we want to display or use later.
    """
    current_ph = get_latest_ph_reading()
    if current_ph is None:
        current_ph = "No reading available"

    settings = load_settings()
    system_volume = settings.get("system_volume", 0)
    auto_dosing_enabled = settings.get("auto_dosing_enabled", False)
    ph_target = settings.get("ph_target", 5.8)

    return {
        "current_ph": current_ph,
        "system_volume": system_volume,
        "auto_dosing_enabled": auto_dosing_enabled,
        "ph_target": ph_target
    }
