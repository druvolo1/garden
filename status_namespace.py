# File: status_namespace.py
from flask_socketio import Namespace
from services.ph_service import get_latest_ph_reading
from api.settings import load_settings
from services.auto_dose_state import auto_dose_state
from services.plant_service import get_weeks_since_start
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
        settings = load_settings()

        # Copy auto_dose_state so we don't mutate the original
        auto_dose_copy = dict(auto_dose_state)
        # Convert any datetime fields to strings
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

        # Load plant_info from settings (if any)
        plant_info_raw = settings.get("plant_info", {})
        # Compute weeks since start
        weeks = get_weeks_since_start(plant_info_raw)

        # Create a new dict for plant_info with an additional "weeks_since_start"
        plant_info = {
            "name": plant_info_raw.get("name", ""),
            "start_date": plant_info_raw.get("start_date", ""),
            "weeks_since_start": weeks
        }

        status = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "auto_dose_state": auto_dose_copy,
            "plant_info": plant_info,    # all plant/grow data is grouped here
            "errors": []
        }

        # Emit this status to all clients in the default namespace
        # If you want it on /status, add: namespace="/status"
        self.emit("status_update", status)
