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
from services.plant_service import get_weeks_since_start
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

import socket

def get_local_ip_addresses():
    """
    Return a set of IPv4 addresses on this machine using only stdlib getaddrinfo().
    This often enumerates all interfaces that the OS has bound (including WiFi, LAN, etc.).
    """
    local_ips = set()
    
    # getaddrinfo(None, 0, ...) with AI_PASSIVE typically enumerates all addresses
    # that this machine can bind to for IPv4. We filter for family=AF_INET.
    try:
        addrinfo_list = socket.getaddrinfo(
            None,
            0,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
            proto=0,
            flags=socket.AI_PASSIVE
        )
        # Each addrinfo is (family, socktype, proto, canonname, (ip, port))
        for addrinfo in addrinfo_list:
            ip = addrinfo[4][0]
            local_ips.add(ip)
    except socket.gaierror:
        pass
    
    # Optionally also add the loopback
    local_ips.add("127.0.0.1")
    
    # You can also incorporate the gethostbyname_ex() approach if you want:
    try:
        hostname = socket.gethostname()
        host_info = socket.gethostbyname_ex(hostname)
        for ip in host_info[2]:
            local_ips.add(ip)
    except socket.gaierror:
        pass
    
    return local_ips

def is_local_host(host: str, local_names=None):
    """
    Decide if `host` is local or truly remote, using only the standard library.

    1) If empty / 'localhost' / '127.0.0.1', treat as local.
    2) If matches an optional local_names list or <something>.local, treat as local.
    3) If IP is in get_local_ip_addresses(), treat as local.
    4) Otherwise, treat as remote.
    """
    # If no host, or explicitly localhost/127.0.0.1
    if not host or host.lower() in ("localhost", "127.0.0.1"):
        log_with_timestamp(f"[DEBUG] is_local_host({host}) -> True (empty/localhost)")
        return True

    # If local_names are provided, check them
    if local_names:
        host_lower = host.lower()
        for ln in local_names:
            ln_lower = ln.lower()
            if host_lower == ln_lower or host_lower == f"{ln_lower}.local":
                log_with_timestamp(f"[DEBUG] is_local_host({host}) -> True (matched {ln_lower}.local)")
                return True

    # Compare against the IPs known to be on this device
    local_ips = get_local_ip_addresses()
    if host in local_ips:
        log_with_timestamp(f"[DEBUG] is_local_host({host}) -> True (found in local IP list)")
        return True

    # Otherwise, not local
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
    
    # 1) If it's local, skip
    if is_local_host(remote_ip):
        log_with_timestamp(f"[DEBUG] Not connecting to local IP '{remote_ip}' to avoid loop.")
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

def get_status_payload():
    """Build and return the status payload without emitting or comparing."""
    try:
        settings = load_settings()

        # -----------------------------------------------------------
        #  1) Retrieve local roles (fill/drain) and valve_relay device
        # -----------------------------------------------------------
        fill_mode  = settings.get("fill_valve_mode", "local")
        drain_mode = settings.get("drain_valve_mode", "local")

        fill_ip    = settings.get("fill_valve_ip", "").strip()
        fill_id    = settings.get("fill_valve", "")  # e.g. "4"
        fill_label = settings.get("fill_valve_label", "Fill Valve")

        drain_ip    = settings.get("drain_valve_ip", "").strip()
        drain_id    = settings.get("drain_valve", "")
        drain_label = settings.get("drain_valve_label", "Drain Valve")

        usb_roles = settings.get("usb_roles", {})
        local_valve_device = usb_roles.get("valve_relay", None)

        # -----------------------------------------------------------
        #  2) Connect to remote if fill/drain is remote
        # -----------------------------------------------------------
        if fill_mode == "remote" and fill_ip:
            connect_to_remote_if_needed(fill_ip)
        if drain_mode == "remote" and drain_ip:
            connect_to_remote_if_needed(drain_ip)

        # -----------------------------------------------------------
        #  3) Gather any local valve statuses
        # -----------------------------------------------------------
        from services.valve_relay_service import get_valve_status
        local_valve_map = {}  # label -> status

        if local_valve_device:
            # (A) Check if fill_valve or drain_valve is assigned locally:
            local_assignments = False

            if fill_mode == "local" and fill_id.isdigit():
                local_assignments = True
                st = get_valve_status(int(fill_id))
                local_valve_map[fill_label] = st or "off"

            if drain_mode == "local" and drain_id.isdigit():
                local_assignments = True
                st = get_valve_status(int(drain_id))
                local_valve_map[drain_label] = st or "off"

            # (B) If no local fill/drain assignment, broadcast *all* 8 channels
            if not local_assignments:
                label_dict = settings.get("valve_labels", {})
                for i in range(1, 9):
                    key = str(i)
                    label = label_dict.get(key, f"Valve {key}")
                    st = get_valve_status(i)
                    local_valve_map[label] = st or "off"

        # -----------------------------------------------------------
        #  4) Gather any remote valve statuses (because fill/drain could be remote)
        # -----------------------------------------------------------
        remote_valve_map = {}
        for ip_addr in [fill_ip, drain_ip]:
            if ip_addr:
                remote_data   = get_cached_remote_states(ip_addr)
                valve_info    = remote_data.get("valve_info", {})
                r_valves      = valve_info.get("valve_relays", {})
                # Merge them into remote_valve_map by label
                for lbl, state_dict in r_valves.items():
                    remote_valve_map[lbl] = state_dict.get("status", "off")

        # -----------------------------------------------------------
        #  5) Build final valve_relays: fill + drain if assigned, OR all 8 if no local assignment
        # -----------------------------------------------------------
        valve_relays = {}

        # Fill
        if fill_mode == "local" and fill_label in local_valve_map:
            valve_relays[fill_label] = {"status": local_valve_map[fill_label]}
        elif fill_mode == "remote" and fill_label:
            st = remote_valve_map.get(fill_label, "off")
            valve_relays[fill_label] = {"status": st}

        # Drain
        if drain_mode == "local" and drain_label in local_valve_map:
            valve_relays[drain_label] = {"status": local_valve_map[drain_label]}
        elif drain_mode == "remote" and drain_label:
            st = remote_valve_map.get(drain_label, "off")
            valve_relays[drain_label] = {"status": st}

        # (Optional) Also include enumerated valves if no local assignment:
        if local_valve_device:
            for lbl, st in local_valve_map.items():
                if lbl not in valve_relays:
                    valve_relays[lbl] = {"status": st}

        # Build the final valve_info
        valve_info = {
            "fill_valve_ip":    fill_ip,
            "fill_valve":       fill_id,
            "fill_valve_label": fill_label,
            "drain_valve_ip":   drain_ip,
            "drain_valve":      drain_id,
            "drain_valve_label": drain_label,
            "valve_relays":     valve_relays
        }

        # -----------------------------------------------------------
        #  6) ADD: Water level sensors
        # -----------------------------------------------------------
        from services.water_level_service import get_water_level_status
        water_level_info = get_water_level_status()  # <--- from water_level_service.py
        log_with_timestamp(f"[DEBUG] Fetched water_level_info: {json.dumps(water_level_info)}")  # Added log for debugging

        # -----------------------------------------------------------
        #  7) Build final payload
        # -----------------------------------------------------------
        from api.settings import feeding_in_progress
        status_payload = {
            "settings":     settings,
            "current_ph":   get_latest_ph_reading(),
            "current_ec":   get_latest_ec_reading(),
            "valve_info":   valve_info,
            "water_level":  water_level_info,  # <--- RE-ADDED LINE
            "feeding_in_progress": feeding_in_progress,
            "timestamp": datetime.now().isoformat(),  # Added: Unique timestamp to force change detection
            # ... any additional fields ...
        }

        return status_payload
    except Exception as e:
        log_with_timestamp(f"Error in get_status_payload: {e}")
        import traceback
        traceback.print_exc()
        return None

def emit_status_update(force_emit=False):
    global LAST_EMITTED_STATUS

    try:
        if not _socketio:
            log_with_timestamp("[ERROR] _socketio is not set yet; cannot emit_status_update.")
            return None

        status_payload = get_status_payload()
        if status_payload is None:
            log_with_timestamp("[DEBUG] get_status_payload returned None; skipping emit.")
            return None

        # Make copy without timestamp for comparison
        compare_payload = {k: v for k, v in status_payload.items() if k != 'timestamp'}
        # Round floats in compare_payload (e.g., pH/EC to 2 decimals)
        compare_payload = round_floats(compare_payload)

        if not force_emit and LAST_EMITTED_STATUS is not None:
            compare_last = {k: v for k, v in LAST_EMITTED_STATUS.items() if k != 'timestamp'}
            compare_last = round_floats(compare_last)
            current_str = json.dumps(compare_payload, sort_keys=True)
            last_str = json.dumps(compare_last, sort_keys=True)
            if current_str == last_str:
                log_with_timestamp("[DEBUG] No changes detected (JSON comparison without timestamp); skipping emit.")
                return None

        log_with_timestamp(f"[DEBUG] Emitting status_update (force={force_emit}), payload keys={list(status_payload.keys())}")
        _socketio.emit("status_update", status_payload, namespace="/status")
        LAST_EMITTED_STATUS = status_payload
        return status_payload  # Return the payload for remote sending

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()
        return None

class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        global LAST_EMITTED_STATUS
        LAST_EMITTED_STATUS = None  # Force first update when a client connects
        emit_status_update(force_emit=True)

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")

    def on_request_refresh(self):
        log_with_timestamp("StatusNamespace: Received refresh request from client.")
        emit_status_update(force_emit=True)  # Immediately send the latest status