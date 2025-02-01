# services/auto_dose_utils.py

from datetime import datetime

# Optionally, if auto_dose_state is shared, you might import it here
from services.auto_dose_state import auto_dose_state

def reset_auto_dose_timer():
    """
    Called whenever we dose (manually or automatically) so we start counting
    a new interval until the next auto dose.
    """
    now = datetime.now()
    auto_dose_state["last_dose_time"] = now
    auto_dose_state["last_dose_type"] = None
    auto_dose_state["last_dose_amount"] = 0.0
    auto_dose_state["next_dose_time"] = None
    auto_dose_state["last_interval"] = None  # Clear the last interval
