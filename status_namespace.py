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


def emit_status_update(force_emit=False):
    global LAST_EMITTED_STATUS

    try:
        if not _socketio:
            log_with_timestamp("[ERROR] _socketio is not set yet; cannot emit_status_update.")
            return

        settings = load_settings()

        # Grab the modes, IPs, etc.
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

        # ---------------
        # PART 1: Get local status for fill/drain if mode=local
        # ---------------
        local_fill_status  = None
        local_drain_status = None

        if local_valve_device:
            # If fill is local, read its current on/off status
            if fill_mode == "local" and fill_id.isdigit():
                from services.valve_relay_service import get_valve_status
                local_fill_status = get_valve_status(int(fill_id))

            # If drain is local, read its current on/off status
            if drain_mode == "local" and drain_id.isdigit():
                from services.valve_relay_service import get_valve_status
                local_drain_status = get_valve_status(int(drain_id))

        # ---------------
        # PART 2: Connect to remote if mode=remote
        # ---------------
        if fill_mode == "remote" and fill_ip:
            connect_to_remote_if_needed(fill_ip)
        if drain_mode == "remote" and drain_ip:
            connect_to_remote_if_needed(drain_ip)

        # Grab whichever remote states we have cached
        remote_relays = {}
        for ip_addr in [fill_ip, drain_ip]:
            if ip_addr:
                remote_data = get_cached_remote_states(ip_addr)
                valve_info  = remote_data.get("valve_info", {})
                r_valves    = valve_info.get("valve_relays", {})
                # Merge them into one big dict, keyed by label
                for lbl, state_dict in r_valves.items():
                    remote_relays[lbl] = state_dict

        # ---------------
        # PART 3: Build the final valve_relays dict with exactly two keys
        # ---------------
        valve_relays = {}

        # FILL entry
        if fill_mode == "local" and fill_label:
            # local_fill_status should be either "on" or "off"
            valve_relays[fill_label] = {"status": local_fill_status or "off"}
        elif fill_mode == "remote" and fill_label:
            # Remote has a dictionary keyed by label, e.g. "Zone 4 Fill"
            remote_entry = remote_relays.get(fill_label, {"status": "off"})
            valve_relays[fill_label] = {"status": remote_entry["status"]}

        # DRAIN entry
        if drain_mode == "local" and drain_label:
            valve_relays[drain_label] = {"status": local_drain_status or "off"}
        elif drain_mode == "remote" and drain_label:
            remote_entry = remote_relays.get(drain_label, {"status": "off"})
            valve_relays[drain_label] = {"status": remote_entry["status"]}

        # Now build valve_info for the JSON
        valve_info = {
            "fill_valve_ip":     fill_ip,
            "fill_valve":        fill_id,
            "fill_valve_label":  fill_label,
            "drain_valve_ip":    drain_ip,
            "drain_valve":       drain_id,
            "drain_valve_label": drain_label,
            "valve_relays":      valve_relays
        }

        # ---------------
        # PART 4: Rest of your payload
        # ---------------
        status_payload = {
            "settings": settings,
            "current_ph": get_latest_ph_reading(),
            "current_ec": get_latest_ec_reading(),
            # ...
            "valve_info": valve_info,
            # ...
        }

        # Emit logic as normal...
        _socketio.emit("status_update", status_payload, namespace="/status")
        LAST_EMITTED_STATUS = status_payload

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
