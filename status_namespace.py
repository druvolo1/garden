from flask_socketio import Namespace, SocketIO
from services.ph_service import get_latest_ph_reading
from utils.settings_utils import load_settings  # Import from utils
from services.auto_dose_state import auto_dose_state
from services.plant_service import get_weeks_since_start
from services.water_level_service import get_water_level_status
from datetime import datetime

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def emit_status_update():
    """
    Emit a status_update event with the latest settings and system status.
    """
    try:
        from app import socketio  # Import socketio from your main app file

        # 1. Load main settings
        settings = load_settings()

        # 2. Copy/format auto_dose_state
        auto_dose_copy = dict(auto_dose_state)
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

        # 3. Prepare plant info
        plant_info_raw = settings.get("plant_info", {})
        weeks = get_weeks_since_start(plant_info_raw)
        plant_info = {
            "name": plant_info_raw.get("name", ""),
            "start_date": plant_info_raw.get("start_date", ""),
            "weeks_since_start": weeks
        }

        # 4. Water level
        water_level_info = get_water_level_status()

        # 5. Valve relay statuses
        valve_info = {}
        valve_labels = settings.get("valve_labels", {})
        from services.valve_relay_service import get_valve_status

        for valve_id_str, label in valve_labels.items():
            valve_id = int(valve_id_str)
            current_state = get_valve_status(valve_id)  # "on", "off", or "unknown"
            valve_info[valve_id_str] = {
                "label": label,
                "status": current_state
            }

        # 6. Construct the final status payload
        status = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "auto_dose_state": auto_dose_copy,
            "plant_info": plant_info,
            "water_level": water_level_info,
            "valve_relays": valve_info,   # <--- new key
            "errors": []
        }

        # 7. Emit via SocketIO
        socketio.emit("status_update", status, namespace="/status")
        log_with_timestamp("Status update emitted successfully.")

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()

class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        self.emit_status()

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")

    def emit_status(self):
        emit_status_update()
