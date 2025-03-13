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
            log_with_timestamp(f"[DEBUG] Resolved {hostname} via Avahi: {ip_address}")
            return ip_address
    except Exception as e:
        log_with_timestamp(f"[ERROR] Avahi resolution failed for {hostname}: {e}")

    # Fallback to socket.getaddrinfo()
    try:
        info = socket.getaddrinfo(hostname, None, socket.AF_INET)
        if info:
            ip_address = info[0][4][0]
            log_with_timestamp(f"[DEBUG] Resolved {hostname} via socket.getaddrinfo(): {ip_address}")
            return ip_address
    except socket.gaierror as e:
        log_with_timestamp(f"[ERROR] Failed to resolve {hostname} via socket: {e}")

    return None  # If both methods fail


def connect_to_remote_if_needed(remote_ip):
    """ Ensure the connection uses the resolved IP rather than the .local name. """
    if not remote_ip:
        log_with_timestamp("[DEBUG] connect_to_remote_if_needed called with empty remote_ip")
        return

    original_name = remote_ip  # Save original hostname for logging

    # Resolve .local names to IPs before connecting
    if remote_ip.endswith(".local"):
        resolved_ip = resolve_mdns(remote_ip)
        if resolved_ip:
            log_with_timestamp(f"[DEBUG] Resolved {remote_ip} -> {resolved_ip}, using IP for WebSocket.")
            remote_ip = resolved_ip
        else:
            log_with_timestamp(f"[ERROR] Could not resolve {remote_ip}. Skipping connection.")
            return

    if remote_ip in REMOTE_CLIENTS:
        log_with_timestamp(f"[DEBUG] Already connected to {remote_ip}, checking for updates...")
        if not get_cached_remote_states(remote_ip):
            log_with_timestamp(f"[DEBUG] No updates received from {remote_ip}, forcing reconnect.")
            REMOTE_CLIENTS[remote_ip].disconnect()
            del REMOTE_CLIENTS[remote_ip]
        else:
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
        REMOTE_STATES[remote_ip] = data  # Store updates using resolved IP
        log_with_timestamp(f"[AGG] on_remote_status_update from {remote_ip}, keys: {list(data.keys())}")

    url = f"http://{remote_ip}:8000"  # Use resolved IP for WebSocket connection
    try:
        log_with_timestamp(f"[AGG] Attempting to connect to {url}")
        sio.connect(url, socketio_path="/socket.io", transports=["websocket", "polling"])
        REMOTE_CLIENTS[remote_ip] = sio
    except Exception as e:
        log_with_timestamp(f"[AGG] Failed to connect to {remote_ip}: {e}")


def get_cached_remote_states(remote_ip):
    """Return the last-known status data from remote_ip, checking both .local and resolved IP."""
    resolved_ip = resolve_mdns(remote_ip) if remote_ip.endswith(".local") else remote_ip
    data = REMOTE_STATES.get(remote_ip, REMOTE_STATES.get(resolved_ip, {}))

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

        # Ignore `last_dose_time` if no dose occurred
        if auto_dose_copy["last_dose_type"] is None and auto_dose_copy["last_dose_amount"] == 0:
            auto_dose_copy["last_dose_time"] = None

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
        fill_valve_ip = settings.get("fill_valve_ip", "").strip()
        drain_valve_ip = settings.get("drain_valve_ip", "").strip()

        # Ensure `.local` hostnames are resolved before connecting
        resolved_ips = {}
        for ip_addr in [fill_valve_ip, drain_valve_ip]:
            if ip_addr.endswith(".local"):
                resolved_ip = resolve_mdns(ip_addr)
                if resolved_ip:
                    resolved_ips[ip_addr] = resolved_ip
                    log_with_timestamp(f"[DEBUG] Resolved {ip_addr} -> {resolved_ip}")

        # Replace .local hostnames with resolved IPs
        fill_valve_ip = resolved_ips.get(fill_valve_ip, fill_valve_ip)
        drain_valve_ip = resolved_ips.get(drain_valve_ip, drain_valve_ip)

        log_with_timestamp(f"[DEBUG] fill_valve_ip={fill_valve_ip}, drain_valve_ip={drain_valve_ip}")

        # Fetch states from remote devices
        for ip_addr in [fill_valve_ip, drain_valve_ip]:
            if not ip_addr:
                log_with_timestamp("[DEBUG] Skipping empty ip_addr")
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

        # **Force emit if first connection or if .local clients exist**
        force_emit = force_emit or any(ip.endswith(".local") for ip in REMOTE_CLIENTS.keys())

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
