# In a new file, e.g., status_namespace.py
from flask_socketio import Namespace
from services.ph_service import get_latest_ph_reading
from api.settings import load_settings
from services.auto_dose_state import auto_dose_state
from datetime import datetime

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        self.emit_status()

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")

def emit_status(self):
    # Build your status object.
    settings = load_settings()
    # Make a copy so we don't mutate the original
    auto_dose_copy = dict(auto_dose_state)

    # Convert any datetime fields to strings
    if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
        auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
    if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
        auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

    status = {
        "settings": settings,
        "current_ph": get_latest_ph_reading(),
        "auto_dose_state": auto_dose_copy,
        "errors": []
    }
    self.emit("status_update", status)

