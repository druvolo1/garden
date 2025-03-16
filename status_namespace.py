import socketio  # for python-socketio (used by aggregator to connect to remote IPs)
from flask_socketio import Namespace
from datetime import datetime
import socket
import subprocess
import json
import os


# Import DNS helpers from your new file:
from utils.network_utils import standardize_host_ip, resolve_mdns

# Services and logic
from services.ph_service import get_latest_ph_reading
from services.ec_service import get_latest_ec_reading
from utils.settings_utils import load_settings
from services.auto_dose_state import auto_dose_state
from services.plant_service import get_weeks_since_start
from services.water_level_service import get_water_level_status
from services.notification_service import get_all_notifications

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
remote_valve_states = {}  # Stores the latest valve states from remote systems

LAST_EMITTED_STATUS = None  # Stores the last sent status update
DEBUG_SETTINGS_FILE = os.path.join(os.getcwd(), "data", "debug_settings.json")


def is_debug_enabled(component):
    """Check if debugging is enabled for a specific component."""
    try:
        with open(DEBUG_SETTINGS_FILE, "r") as f:
            settings = json.load(f)
            if component not in settings:
                print(f"[DEBUG WARNING] '{component}' not found in debug_settings.json. Defaulting to False.")
            return settings.get(component, False)
    except FileNotFoundError:
        return False
    except json.JSONDecodeError:
        print(f"[ERROR] Could not parse {DEBUG_SETTINGS_FILE}. Check the JSON formatting.")
        return False


def log_with_timestamp(msg):
    """Prints log messages only if debugging is enabled for WebSocket (websocket)."""
    if is_debug_enabled("websocket"):
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
    """
    Connects to a remote device, resolving .local names only for connection
    but keeping .local in stored data.
    """
    if not remote_ip:
        log_with_timestamp("[DEBUG] connect_to_remote_if_needed called with empty remote_ip")
        return

    original_name = remote_ip  # Preserve .local for stored data

    # Resolve .local names **only** for connection
    resolved_ip = remote_ip
    if remote_ip.endswith(".local"):
        mdns_ip = resolve_mdns(remote_ip)
        if mdns_ip:
            log_with_timestamp(f"[DEBUG] Resolved {remote_ip} -> {mdns_ip}, using IP for WebSocket connection.")
            resolved_ip = mdns_ip
        else:
            log_with_timestamp(f"[ERROR] Could not resolve {remote_ip}. Skipping connection.")
            return

    # Check if already connected
    if resolved_ip in REMOTE_CLIENTS:
        log_with_timestamp(f"[DEBUG] Already connected to {resolved_ip}, checking for updates...")
        if not get_cached_remote_states(original_name):
            log_with_timestamp(f"[DEBUG] No updates from {original_name}, forcing reconnect.")
            REMOTE_CLIENTS[resolved_ip].disconnect()
            del REMOTE_CLIENTS[resolved_ip]
        else:
            return

    log_with_timestamp(f"[AGG] Creating new Socket.IO client for remote {resolved_ip}")
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event
    def connect():
        log_with_timestamp(f"[AGG] Connected to remote {resolved_ip}")

    @sio.event
    def disconnect():
        log_with_timestamp(f"[AGG] Disconnected from remote {resolved_ip}")

    @sio.event
    def connect_error(data):
        log_with_timestamp(f"[AGG] Connect error for remote {resolved_ip}: {data}")

    @sio.on("status_update", namespace="/status")
    def on_remote_status_update(data):
        REMOTE_STATES[original_name] = data  # store under the original .local name
        log_with_timestamp(f"[AGG] on_remote_status_update from {original_name}, keys: {list(data.keys())}")
        emit_status_update(force_emit=True)

    url = f"http://{resolved_ip}:8000"
    try:
        log_with_timestamp(f"[AGG] Attempting to connect to {url}")
        sio.connect(url, socketio_path="/socket.io", transports=["websocket", "polling"])
        REMOTE_CLIENTS[resolved_ip] = sio
    except Exception as e:
        log_with_timestamp(f"[AGG] Failed to connect to {resolved_ip}: {e}")


def get_cached_remote_states(remote_ip):
    """
    Return the last-known status data from remote_ip, checking both .local
    and resolved IP. If remote_ip is blank/None, skip entirely.
    """
    if not remote_ip:
        log_with_timestamp("[DEBUG] get_cached_remote_states called with empty/None remote_ip. Skipping.")
        return {}

    if remote_ip.endswith(".local"):
        resolved_ip = resolve_mdns(remote_ip)
    else:
        resolved_ip = remote_ip

    data = REMOTE_STATES.get(remote_ip, REMOTE_STATES.get(resolved_ip, {}))

    if data:
        log_with_timestamp(f"[DEBUG] get_cached_remote_states({remote_ip}) -> found keys: {list(data.keys())}")
    else:
        log_with_timestamp(f"[DEBUG] get_cached_remote_states({remote_ip}) -> empty")
    return data


def emit_status_update(force_emit=False):
    """
    Collects valve statuses (local or remote) and emits them under keys like
    'fill_4' or 'drain_4' rather than plain '4'.
    """
    global LAST_EMITTED_STATUS

    try:
        if not _socketio:
            log_with_timestamp("[ERROR] _socketio is not set yet; cannot emit_status_update.")
            return

        settings = load_settings()
        log_with_timestamp(f"[DEBUG] Loaded settings, system_name={settings.get('system_name')}")

        # Convert auto_dose_state times to ISO string if needed
        auto_dose_copy = dict(auto_dose_state)
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()
        if auto_dose_copy["last_dose_type"] is None and auto_dose_copy["last_dose_amount"] == 0:
            auto_dose_copy["last_dose_time"] = None

        # Plant info + water level
        plant_info_raw = settings.get("plant_info", {})
        weeks = get_weeks_since_start(plant_info_raw)
        plant_info = {
            "name": plant_info_raw.get("name", ""),
            "start_date": plant_info_raw.get("start_date", ""),
            "weeks_since_start": weeks
        }
        water_level_info = get_water_level_status()

        fill_valve_id    = settings.get("fill_valve", "")         # e.g. "4"
        fill_valve_label = settings.get("fill_valve_label", "")   # e.g. "Zone 4 Fill"
        drain_valve_id   = settings.get("drain_valve", "")
        drain_valve_label= settings.get("drain_valve_label", "")

        from services.valve_relay_service import get_valve_status
        aggregator_map = {}

        #
        # (A) Populate aggregator_map with the local fill/drain, if numeric
        #
        if fill_valve_id.isdigit():
            aggregator_map[f"fill_{fill_valve_id}"] = {
                "label": fill_valve_label,
                "status": get_valve_status(int(fill_valve_id))
            }

        if drain_valve_id.isdigit():
            aggregator_map[f"drain_{drain_valve_id}"] = {
                "label": drain_valve_label,
                "status": get_valve_status(int(drain_valve_id))
            }

        #
        # (B) Merge in remote states for fill/drain IPs
        #
        fill_valve_ip  = settings.get("fill_valve_ip", "").strip()
        drain_valve_ip = settings.get("drain_valve_ip", "").strip()

        resolved_fill_ip = None
        if fill_valve_ip:
            if fill_valve_ip.endswith(".local"):
                resolved_fill_ip = resolve_mdns(fill_valve_ip) or fill_valve_ip
            else:
                resolved_fill_ip = fill_valve_ip

        resolved_drain_ip = None
        if drain_valve_ip:
            if drain_valve_ip.endswith(".local"):
                resolved_drain_ip = resolve_mdns(drain_valve_ip) or drain_valve_ip
            else:
                resolved_drain_ip = drain_valve_ip

        log_with_timestamp(f"[DEBUG] fill_valve_ip='{fill_valve_ip}' => '{resolved_fill_ip}'")
        log_with_timestamp(f"[DEBUG] drain_valve_ip='{drain_valve_ip}' => '{resolved_drain_ip}'")

        remote_relays = {}
        for ip_addr, resolved_ip in [
            (fill_valve_ip,  resolved_fill_ip),
            (drain_valve_ip, resolved_drain_ip)
        ]:
            if not ip_addr:
                continue

            connect_to_remote_if_needed(resolved_ip)
            remote_data         = get_cached_remote_states(resolved_ip)  # from REMOTE_STATES
            remote_valve_info   = remote_data.get("valve_info", {})
            remote_relay_states = remote_valve_info.get("valve_relays", {})

            log_with_timestamp(f"[DEBUG] Remote '{resolved_ip}' has {len(remote_relay_states)} valves")

            for key, relay_obj in remote_relay_states.items():
                # if the remote valve's numeric ID is the fill_valve_id
                if key.replace("fill_","").replace("drain_","") == fill_valve_id:
                    remote_relays[f"fill_{fill_valve_id}"] = {
                        "label": relay_obj.get("label", f"Valve {fill_valve_id}"),
                        "status": relay_obj.get("status", "off")
                    }
                elif key.replace("fill_","").replace("drain_","") == drain_valve_id:
                    remote_relays[f"drain_{drain_valve_id}"] = {
                        "label": relay_obj.get("label", f"Valve {drain_valve_id}"),
                        "status": relay_obj.get("status", "off")
                    }

        # Merge
        valve_relays = aggregator_map.copy()
        valve_relays.update(remote_relays)

        valve_info = {
            "fill_valve_ip":    fill_valve_ip,
            "fill_valve":       fill_valve_id,
            "fill_valve_label": fill_valve_label,

            "drain_valve_ip":    drain_valve_ip,
            "drain_valve":       drain_valve_id,
            "drain_valve_label": drain_valve_label,

            "valve_relays": valve_relays
        }

        status_payload = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "current_ec": get_latest_ec_reading(),
            "auto_dose_state": auto_dose_copy,
            "plant_info": plant_info,
            "water_level": water_level_info,
            "valve_info": valve_info,
            "notifications": get_all_notifications()
        }

        # Decide whether to emit forcibly
        force_emit = force_emit or (LAST_EMITTED_STATUS is None)
        if force_emit:
            _socketio.emit("status_update", status_payload, namespace="/status")
            LAST_EMITTED_STATUS = status_payload
            return

        # Check for changes
        changes = {}
        for key in status_payload:
            old_val = LAST_EMITTED_STATUS.get(key) if LAST_EMITTED_STATUS else None
            if status_payload[key] != old_val:
                changes[key] = (old_val, status_payload[key])

        if not changes:
            log_with_timestamp("[DEBUG] No changes detected in status, skipping emit.")
            return

        _socketio.emit("status_update", status_payload, namespace="/status")
        LAST_EMITTED_STATUS = status_payload
        log_with_timestamp("Status update emitted successfully.")

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()


class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        global LAST_EMITTED_STATUS
        LAST_EMITTED_STATUS = None  # Force first update when a client connects
        emit_status_update(force_emit=True)

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")
