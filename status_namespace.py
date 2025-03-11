import socketio  # for python-socketio (used by aggregator to connect to remote IPs)
from flask_socketio import Namespace
from datetime import datetime

# Services and logic
from services.ph_service import get_latest_ph_reading
from services.ec_service import get_latest_ec_reading
from utils.settings_utils import load_settings
from services.auto_dose_state import auto_dose_state
from services.plant_service import get_weeks_since_start
from services.water_level_service import get_water_level_status

_socketio = None

def set_socketio_instance(sio):
    """
    Called once from app.py after the app initializes its SocketIO object.
    Eliminates circular import by not importing from app here.
    """
    global _socketio
    _socketio = sio

REMOTE_STATES = {}   # remote_ip -> last-known JSON from that remote's "status_update"
REMOTE_CLIENTS = {}  # remote_ip -> python-socketio.Client instance

def log_with_timestamp(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def is_local_host(host: str, local_names=None):
    """ Decide if `host` is local or truly remote. """
    if not host or host.lower() in ("localhost", "127.0.0.1"):
        log_with_timestamp(f"[DEBUG] is_local_host({host}) -> True (empty/localhost)")
        return True
    if local_names:
        host_lower = host.lower()
        for ln in local_names:
            ln_lower = ln.lower()
            # e.g. host="zone1.local" => matches "Zone1"
            if host_lower == ln_lower or host_lower == f"{ln_lower}.local":
                log_with_timestamp(f"[DEBUG] is_local_host({host}) -> True (matched {ln_lower}.local)")
                return True
    log_with_timestamp(f"[DEBUG] is_local_host({host}) -> False")
    return False

def connect_to_remote_if_needed(remote_ip):
    """Create (or reuse) a python-socketio.Client to connect to remote_ip:8000."""
    if not remote_ip:
        log_with_timestamp("[DEBUG] connect_to_remote_if_needed called with empty remote_ip")
        return

    if remote_ip in REMOTE_CLIENTS:
        log_with_timestamp(f"[DEBUG] Already connected to {remote_ip}, skipping.")
        return

    log_with_timestamp(f"[AGG] Creating new Socket.IO client for remote {remote_ip}")
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event
    def connect():
        log_with_timestamp(f"[AGG] Connected to remote {remote_ip}")

    @sio.event
    def disconnect():
        log_with_timestamp(f"[AGG] Disconnected from remote {remote_ip}")

    @sio.event
    def connect_error(data):
        log_with_timestamp(f"[AGG] Connect error for remote {remote_ip}: {data}")

    @sio.on("status_update", namespace="/status")
    def on_remote_status_update(data):
        REMOTE_STATES[remote_ip] = data
        log_with_timestamp(f"[AGG] on_remote_status_update from {remote_ip}, keys: {list(data.keys())}")

    url = f"http://{remote_ip}:8000"
    try:
        log_with_timestamp(f"[AGG] Attempting to connect to {url}")
        sio.connect(
            url,
            socketio_path="/socket.io",
            transports=["websocket", "polling"]
        )
        REMOTE_CLIENTS[remote_ip] = sio
    except Exception as e:
        log_with_timestamp(f"[AGG] Failed to connect to {remote_ip}: {e}")

def get_cached_remote_states(remote_ip):
    """Return the last-known status data from remote_ip."""
    data = REMOTE_STATES.get(remote_ip, {})
    if data:
        log_with_timestamp(f"[DEBUG] get_cached_remote_states({remote_ip}) -> found keys: {list(data.keys())}")
    else:
        log_with_timestamp(f"[DEBUG] get_cached_remote_states({remote_ip}) -> empty")
    return data

def emit_status_update():
    """
    Collects all valve statuses from:
      - Local USB device (if assigned in usb_roles["valve_relay"])
      - Remote fill_valve_ip, drain_valve_ip (if assigned)
    Then merges them all (local + remote) into valve_info["valve_relays"].

    The front end can look at fill_valve_label/drain_valve_label to highlight
    which ones are 'their' fill or drain channels, but we always include all channels.
    """
    try:
        if not _socketio:
            log_with_timestamp("[ERROR] _socketio is not set yet; cannot emit_status_update.")
            return

        # 1) Load settings
        settings = load_settings()
        log_with_timestamp(f"[DEBUG] Loaded settings, system_name={settings.get('system_name')}")

        # 2) Convert auto_dose_state times
        auto_dose_copy = dict(auto_dose_state)
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

        # 3) Plant info
        plant_info_raw = settings.get("plant_info", {})
        weeks = get_weeks_since_start(plant_info_raw)
        plant_info = {
            "name": plant_info_raw.get("name", ""),
            "start_date": plant_info_raw.get("start_date", ""),
            "weeks_since_start": weeks
        }

        # 4) Water level
        water_level_info = get_water_level_status()

        # aggregator_map holds label -> { label, status }, from both local + remote
        aggregator_map = {}

        # 5) If there's a local USB valve device, gather its statuses
        valve_relay_device = settings.get("usb_roles", {}).get("valve_relay")
        if valve_relay_device:
            log_with_timestamp(f"[DEBUG] local valve_relay_device={valve_relay_device}")
            from services.valve_relay_service import get_valve_status
            local_labels = settings.get("valve_labels", {})
            for valve_id_str, label in local_labels.items():
                try:
                    valve_id = int(valve_id_str)
                except:
                    continue
                st = get_valve_status(valve_id)
                aggregator_map[label] = {
                    "label": label,
                    "status": st
                }
        else:
            log_with_timestamp("[DEBUG] No local valve_relay_device assigned.")

        # 6) If fill_valve_ip or drain_valve_ip is assigned, gather remote states
        fill_valve_ip  = (settings.get("fill_valve_ip")   or "").strip()
        drain_valve_ip = (settings.get("drain_valve_ip") or "").strip()

        log_with_timestamp(f"[DEBUG] fill_valve_ip={fill_valve_ip}, drain_valve_ip={drain_valve_ip}")

        local_system_name = settings.get("system_name", "Garden")
        local_names = [local_system_name]

        for ip_addr in [fill_valve_ip, drain_valve_ip]:
            if not ip_addr:
                log_with_timestamp("[DEBUG] skip empty ip_addr")
                continue
            if is_local_host(ip_addr, local_names):
                log_with_timestamp(f"[DEBUG] skip connect, {ip_addr} is local")
                continue

            connect_to_remote_if_needed(ip_addr)
            remote_data = get_cached_remote_states(ip_addr)
            remote_valve_info = remote_data.get("valve_info", {})
            remote_relays = remote_valve_info.get("valve_relays", {})
            log_with_timestamp(f"[DEBUG] From remote {ip_addr}, found {len(remote_relays)} label_keys")

            # Merge all remote channels into aggregator_map
            for label_key, label_obj in remote_relays.items():
                aggregator_map[label_key] = {
                    "label":  label_obj.get("label", label_key),
                    "status": label_obj.get("status", "unknown")
                }

        # 7) Build final valve_info with no filtering
        valve_info = {
            "fill_valve_ip":   fill_valve_ip,
            "fill_valve":      settings.get("fill_valve", ""),
            "fill_valve_label": settings.get("fill_valve_label", ""),
            "drain_valve_ip":  drain_valve_ip,
            "drain_valve":     settings.get("drain_valve", ""),
            "drain_valve_label": settings.get("drain_valve_label", ""),
            "valve_relays":    aggregator_map  # everything
        }

        # 8) Final payload
        status_payload = {
            "settings":       settings,
            "current_ph":     get_latest_ph_reading(),
            "current_ec":     get_latest_ec_reading(),
            "auto_dose_state": auto_dose_copy,
            "plant_info":     plant_info,
            "water_level":    water_level_info,
            "valve_info":     valve_info,
            "errors":         []
        }

        _socketio.emit("status_update", status_payload, namespace="/status")
        log_with_timestamp("Status update emitted successfully (including all valves).")

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()

class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        emit_status_update()

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")
