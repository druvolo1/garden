# In a new file, e.g., status_namespace.py
from flask_socketio import Namespace
from services.ph_service import get_latest_ph_reading
from api.settings import load_settings
from services.auto_dose_state import auto_dose_state
from datetime import datetime

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

class StatusNamespace(Namespace):
    def on_connect(self):
        log_with_timestamp("StatusNamespace: Client connected.")
        self.emit_status()

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")

    def emit_status(self):
        # Build your status object – you can include settings, current pH value, and any errors
        settings = load_settings()
        status = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "auto_dose_state": auto_dose_state,
            # Optionally, you could add an "errors" field if your app collects errors.
            "errors": []
        }
        # Emit an event called 'status_update'
        self.emit("status_update", status)
