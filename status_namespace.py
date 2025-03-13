import socketio  # for python-socketio (used by aggregator to connect to remote IPs)
from flask_socketio import Namespace
from datetime import datetime
import socket
import subprocess

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

LAST_EMITTED_STATUS = None  # Stores the last sent status update

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

def resolve_mdns(hostname):
    """ Try resolving .local using avahi-resolve-host-name first, fallback to socket """
    try:
        # Attempt to resolve via avahi (Linux/macOS)
        result = subprocess.run(["avahi-resolve-host-name", "-4", hostname], capture_output=True, text=True)
        if result.returncode == 0:
            ip_address = result.stdout.strip().split()[-1]  # Extract the IP
            print(f"[DEBUG] Resolved {hostname} via Avahi: {ip_address}")
            return ip_address
    except Exception as e:
        print(f"[ERROR] Avahi resolution failed for {hostname}: {e}")

    # Fallback to socket.getaddrinfo()
    try:
        info = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if info:
            ip_address = info[0][4][0]
            print(f"[DEBUG] Resolved {hostname} via socket.getaddrinfo(): {ip_address}")
            return ip_address
    except socket.gaierror as e:
        print(f"[ERROR] Failed to resolve {hostname} via socket: {e}")

    return None  # If both methods fail


def connect_to_remote_if_needed(remote_ip):
    """Create (or reuse) a python-socketio.Client to connect to remote_ip:8000."""
    if not remote_ip:
        log_with_timestamp("[DEBUG] connect_to_remote_if_needed called with empty remote_ip")
        return

    # Resolve .local hostname if needed
    if remote_ip.endswith(".local"):
        resolved_ip = resolve_mdns(remote_ip)
        if resolved_ip:
            log_with_timestamp(f"[DEBUG] Resolved {remote_ip} -> {resolved_ip}")
            remote_ip = resolved_ip
        else:
            log_with_timestamp(f"[ERROR] Could not resolve {remote_ip}. Skipping connection.")
            return

    # **Force reconnection if using a .local domain**
    if remote_ip in REMOTE_CLIENTS:
        log_with_timestamp(f"[DEBUG] Forcing reconnection to {remote_ip} (mDNS detected).")
        REMOTE_CLIENTS[remote_ip].disconnect()  # Force a disconnect
        del REMOTE_CLIENTS[remote_ip]           # Remove from the cache

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
        sio.connect(url, socketio_path="/socket.io", transports=["websocket", "polling"])
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

def emit_status_update(force_emit=False):
    """
    Collects all valve statuses from local and remote sources and emits only when there are changes.
    """
    global LAST_EMITTED_STATUS

    try:
        if not _socketio:
            log_with_timestamp("[ERROR] _socketio is not set yet; cannot emit_status_update.")
            return

        # 1) Load settings
        settings = load_settings()
        log_with_timestamp(f"[DEBUG] Loaded settings, system_name={settings.get('system_name')}")

        # 2) Convert auto_dose_state times and prevent unnecessary updates
        auto_dose_copy = dict(auto_dose_state)
        if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
            auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
        if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
            auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

        # **Ignore `last_dose_time` if no dose actually occurred**
        if auto_dose_copy["last_dose_type"] is None and auto_dose_copy["last_dose_amount"] == 0:
            auto_dose_copy["last_dose_time"] = None  # Don't trigger an update if nothing happened

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

        # 5) Valve relays and aggregator map
        aggregator_map = {}
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
                aggregator_map[label] = {"label": label, "status": st}
        else:
            log_with_timestamp("[DEBUG] No local valve_relay_device assigned.")

        # 6) Check remote valve states
        fill_valve_ip = (settings.get("fill_valve_ip") or "").strip()
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

            for label_key, label_obj in remote_relays.items():
                aggregator_map[label_key] = {"label": label_obj.get("label", label_key), "status": label_obj.get("status", "unknown")}

        # 7) Build final valve_info
        fill_valve_label = settings.get("fill_valve_label", "")
        drain_valve_label = settings.get("drain_valve_label", "")
        valve_relay_device = settings.get("usb_roles", {}).get("valve_relay", "")

        filtered_relays = {}

        if valve_relay_device:  # ✅ If valve relay is assigned via USB, send all relays
            log_with_timestamp(f"[DEBUG] Local valve relay detected via USB: {valve_relay_device}. Including all relays.")
            filtered_relays = aggregator_map  # Send all valves
        else:  # ✅ Otherwise, filter to only include assigned fill/drain valves
            log_with_timestamp(f"[DEBUG] Filtering valves. Only sending assigned fill/drain valves.")
            for label, relay in aggregator_map.items():
                if label in (fill_valve_label, drain_valve_label):
                    filtered_relays[label] = relay

        valve_info = {
            "fill_valve_ip": fill_valve_ip,
            "fill_valve": settings.get("fill_valve", ""),
            "fill_valve_label": fill_valve_label,
            "drain_valve_ip": drain_valve_ip,
            "drain_valve": settings.get("drain_valve", ""),
            "drain_valve_label": drain_valve_label,
            "valve_relays": filtered_relays  # ✅ Only send assigned valves unless it's a USB relay host
        }


        # 8) Build final status payload
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

        # **Force emit if first connection**
        if force_emit or LAST_EMITTED_STATUS is None:
            log_with_timestamp("[DEBUG] Forcing status update emit on first connection.")
            _socketio.emit("status_update", status_payload, namespace="/status")
            LAST_EMITTED_STATUS = status_payload
            return

        # **Only emit if changes are detected**
        changes = {}
        for key in status_payload:
            if status_payload[key] != LAST_EMITTED_STATUS[key]:
                changes[key] = (LAST_EMITTED_STATUS[key], status_payload[key])

        if not changes:
            log_with_timestamp("[DEBUG] No changes detected in status, skipping emit.")
            return  # ✅ Skip emitting if nothing changed

        log_with_timestamp(f"[DEBUG] Changes detected in status: {changes}")

        # ✅ Emit the status update and store it
        _socketio.emit("status_update", status_payload, namespace="/status")
        LAST_EMITTED_STATUS = status_payload  # ✅ Store the last known status
        log_with_timestamp("Status update emitted successfully (including forced emit on connection).")

    except Exception as e:
        log_with_timestamp(f"Error in emit_status_update: {e}")
        import traceback
        traceback.print_exc()

class StatusNamespace(Namespace):
    def on_connect(self, auth=None):
        log_with_timestamp(f"StatusNamespace: Client connected. auth={auth}")
        global LAST_EMITTED_STATUS
        LAST_EMITTED_STATUS = None  # Force first update when a client connects
        emit_status_update(force_emit=True)  # Explicitly force emit

    def on_disconnect(self):
        log_with_timestamp("StatusNamespace: Client disconnected.")
