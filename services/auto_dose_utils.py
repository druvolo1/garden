# File: services/auto_dose_utils.py

from datetime import datetime, timedelta

# Optionally, if auto_dose_state is shared, you might import it here
from services.auto_dose_state import auto_dose_state

def reset_auto_dose_timer(dose_type=None, dose_amount=0.0):
    """
    Called whenever we dose (manually or automatically) so we start counting
    a new interval until the next auto dose.

    Args:
        dose_type: The type of dose ("up", "down", or None)
        dose_amount: The amount dosed in ml
    """
    from api.settings import load_settings
    from status_namespace import is_debug_enabled

    now = datetime.now()
    auto_dose_state["last_dose_time"] = now
    auto_dose_state["last_dose_type"] = dose_type
    auto_dose_state["last_dose_amount"] = dose_amount

    # Calculate next dose time based on dosing interval
    settings = load_settings()
    dosing_interval_hours = settings.get("dosing_interval", 1.0)
    auto_dose_state["next_dose_time"] = now + timedelta(hours=dosing_interval_hours)

    auto_dose_state["last_interval"] = None  # Clear the last interval

    if is_debug_enabled("auto_dosing"):
        print(f"[DEBUG AutoDose] reset_auto_dose_timer called:")
        print(f"  - dose_type: {dose_type}")
        print(f"  - dose_amount: {dose_amount}")
        print(f"  - last_dose_time set to: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  - dosing_interval: {dosing_interval_hours} hours")
        print(f"  - next_dose_time set to: {auto_dose_state['next_dose_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  - Current state: {auto_dose_state}")