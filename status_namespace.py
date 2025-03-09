# File: status_namespace.py

import socketio  # <-- Make sure you `pip install "python-socketio[client]"`
from flask_socketio import Namespace
from services.ph_service import get_latest_ph_reading
from services.ec_service import get_latest_ec_reading
from utils.settings_utils import load_settings
from services.auto_dose_state import auto_dose_state
from services.plant_service import get_weeks_since_start
from services.water_level_service import get_water_level_status
from datetime import datetime

# Keep track of known remote states and clients
REMOTE_STATES = {}   # remote_ip -> last-known JSON from that remote's "status_update"
REMOTE_CLIENTS = {}  # remote_ip -> socketio.Client instance

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def is_local_host(host: str, local_names=None):
    """
    Decide if `host` is "local" or truly remote. You can expand this logic as needed.
    """
    if not host or host.lower() in ("localhost", "127.0.0.1"):
        return True
    if local_names:
        # If your local system_name is "Zone4", you might consider "Zone4.local" or "zone4" local, etc.
        host_lower = host.lower()
        for ln in local_names:
            ln_lower = ln.lower()
            if host_lower == ln_lower or host_lower == f"{ln_lower}.local":
                return True
    return False

def connect_to_remote_if_needed(remote_ip):
    """
    Creates (or reuses) a Socket.IO client to remote_ip:8000/status.
    If we haven't connected before, set up event handlers for "status_update."
    """
    if not remote_ip:
        return
    if remote_ip in REMOTE_CLIENTS:
        return  # Already connected

    print(f"[AGG] Creating new Socket.IO client for remote {remote_ip}")
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event
    def connect():
        print(f"[AGG] Connected to remote {remote_ip}")

    @sio.event
    def disconnect():
        print(f"[AGG] Disconnected from remote {remote_ip}")

    @sio.event
    def connect_error(data):
        print(f"[AGG] Connect error for remote {remote_ip}: {data}")

    @sio.on("status_update")
    def on_remote_status_update(data):
        # We store the entire payload from that remote
        REMOTE_STATES[remote_ip] = data

    url = f"http://{remote_ip}:8000/status"
    try:
        print(f"[AGG] Attempting to connect to {url}")
        sio.connect(url, transports=["websocket"])
        REMOTE_CLIENTS[remote_ip] = sio
    except Exception as e:
        print(f"[AGG] Failed to connect to {remote_ip}: {e}")

def get_cached_remote_states(remote_ip):
    """
    Return the last-known `status_update` data from remote_ip (if any),
    or an empty dict if we haven't received anything yet.
    """
    return REMOTE_STATES.get(remote_ip, {})

def emit_status_update():
    """
    Emit a status_update event with merged local & remote valve states (by LABEL).
    """
    try:
        from app import socketio  # your Flask-SocketIO instance

        # 1) Load main settings
        settings = load_settings()

        # 2) Format auto_dose_state
        auto_dose_copy = dict(auto_dose_state)
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

        # 3) Basic info for front-end
        plant_info_raw = settings.get("plant_info", {})
        weeks = get_weeks_since_start(plant_info_raw)
        plant_info = {
            "name": plant_info_raw.get("name", ""),
            "start_date": plant_info_raw.get("start_date", ""),
            "weeks_since_start": weeks
        }
        water_level_info = get_water_level_status()

        # 4) Identify local vs. remote IPs for fill/drain
        fill_valve_ip  = (settings.get("fill_valve_ip")   or "").strip()
        fill_valve     =  settings.get("fill_valve", "")
        drain_valve_ip = (settings.get("drain_valve_ip") or "").strip()
        drain_valve    =  settings.get("drain_valve", "")

        # ANY numeric keys in valve_labels become possible local channels
        valve_labels = settings.get("valve_labels", {})

        local_system_name = settings.get("system_name", "Garden")

        # ----------------------------------------------------------------------
        # 5) Build a label-keyed dictionary for LOCAL valves  (ADDED / CHANGED)
        # ----------------------------------------------------------------------
        from services.valve_relay_service import get_valve_status
        label_map_local = {}
        valve_relay_device = settings.get("usb_roles", {}).get("valve_relay")

        if valve_relay_device:
            # For each numeric ID -> label, get local status
            for valve_id_str, label in valve_labels.items():
                try:
                    valve_id = int(valve_id_str)
                except:
                    continue
                status = get_valve_status(valve_id)  # "on" / "off" / "unknown"
                label_map_local[label] = {
                    "label": label,
                    "status": status
                }
        # If there's no local device, label_map_local stays empty

        # Create aggregator map (label -> {label, status})
        aggregator_map = dict(label_map_local)

        # ----------------------------------------------------------------------
        # 6) Merge REMOTE states (also by label)  (ADDED / CHANGED)
        # ----------------------------------------------------------------------
        local_names = [local_system_name]  # If you have synonyms, add them here
        for ip_addr in [fill_valve_ip, drain_valve_ip]:
            if ip_addr and not is_local_host(ip_addr, local_names):
                # Connect if needed
                connect_to_remote_if_needed(ip_addr)
                # Grab the remote's last-known status_update
                remote_data = get_cached_remote_states(ip_addr)
                remote_valve_info = remote_data.get("valve_info", {})
                remote_valve_relays = remote_valve_info.get("valve_relays", {})

                # Now, because the remote is also label-based, `remote_valve_relays`
                # is something like:
                #   {"Zone 4 Fill": {"label":"Zone 4 Fill","status":"off"}, ... }
                for label_key, label_obj in remote_valve_relays.items():
                    # label_key = e.g. "Zone 4 Fill"
                    # label_obj = {"label":"Zone 4 Fill", "status":"off"}
                    aggregator_map[label_key] = {
                        "label": label_obj.get("label", label_key),
                        "status": label_obj.get("status", "unknown")
                    }

        # ----------------------------------------------------------------------
        # 7) Construct final valve_info with label-based 'valve_relays'
        # ----------------------------------------------------------------------
        valve_info = {
            "fill_valve_ip":  fill_valve_ip,
            "fill_valve":     fill_valve,
            "drain_valve_ip": drain_valve_ip,
            "drain_valve":    drain_valve,
            "valve_labels":   valve_labels,
            # Instead of numeric keys, aggregator_map is keyed by the LABEL
            "valve_relays":   aggregator_map
        }

        # 8) Build the final payload
        status_payload = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "current_ec": get_latest_ec_reading(),
            "auto_dose_state": auto_dose_copy,
            "plant_info": plant_info,
            "water_level": water_level_info,
            "valve_info": valve_info,
            "errors": []
        }

        # 9) Emit it
        from app import socketio
        socketio.emit("status_update", status_payload, namespace="/status")
        log_with_timestamp("Status update emitted successfully (label-based aggregator).")

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()

#
# No change below here
#
class StatusNamespace(Namespace):
    def on_connect(self):
        log_with_timestamp("StatusNamespace: Client connected.")
        self.emit_status()

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")

    def emit_status(self):
        emit_status_update()
