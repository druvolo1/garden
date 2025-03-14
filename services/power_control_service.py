# File: services/power_control_service.py

import eventlet
eventlet.monkey_patch()


import socketio  # pip install "python-socketio[client]"
from utils.settings_utils import load_settings
from datetime import datetime
import requests
import json
import socket


remote_valve_states = {}  # (host_ip, valve_id_str) -> "on"/"off"
last_outlet_states = {}   # outlet_ip -> "on"/"off"
sio_clients = {}          # host_ip -> socketio.Client instance

def log(msg):
    from status_namespace import is_debug_enabled
    """Logs messages only if debugging is enabled for power_control_service."""
    if is_debug_enabled("power_control_service"):  # ✅ Check debug setting
        print(f"[PowerControlService] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

def get_resolver():
    from status_namespace import resolve_mdns
    return resolve_mdns

def get_local_ip_address():
    """
    Return this Pi’s primary LAN IP, or '127.0.0.1' on fallback.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()

def standardize_host_ip(raw_host_ip):
    """
    If raw_host_ip is empty, or is 'localhost', '127.0.0.1', or '<system_name>.local',
    replace it with this Pi’s LAN IP. Otherwise return raw_host_ip unchanged.
    """
    if not raw_host_ip:
        return None

    s = load_settings()
    system_name = s.get("system_name", "Garden").lower()
    lower_host = raw_host_ip.lower()

    # Resolve .local hostnames
    if lower_host.endswith(".local"):
        resolve_mdns = get_resolver()
        resolved_ip = resolve_mdns(lower_host)
        if resolved_ip:
            log(f"[standardize_host_ip] Resolved '{raw_host_ip}' -> '{resolved_ip}'")
            return resolved_ip

    if lower_host in ["localhost", "127.0.0.1", f"{system_name}.local"]:
        new_ip = get_local_ip_address()
        log(f"[standardize_host_ip] Replacing '{raw_host_ip}' with '{new_ip}'.")
        return new_ip

    return raw_host_ip

def start_power_control_loop():
    """
    Spawns the background thread that connects to remote valves & controls Shelly outlets.
    """
    eventlet.spawn(power_control_main_loop)
    log("Power Control loop started.")

def power_control_main_loop():
    while True:
        try:
            settings = load_settings()
            power_controls = settings.get("power_controls", [])

            # 1) Gather the host IPs from 'tracked_valves'
            needed_hosts = set()
            for pc in power_controls:
                for tv in pc.get("tracked_valves", []):
                    fixed_host = standardize_host_ip(tv["host_ip"])
                    if fixed_host:
                        needed_hosts.add(fixed_host)

            log(f"[power_control_main_loop] Needed hosts for power control: {needed_hosts}")

            # 2) Close any old connections that are no longer needed
            for old_host in list(sio_clients.keys()):
                if old_host not in needed_hosts:
                    close_host_connection(old_host)

            # 3) Ensure we have a Socket.IO connection to each needed host
            for host_ip in needed_hosts:
                if host_ip not in sio_clients:
                    log(f"[power_control_main_loop] Opening socket.io connection to {host_ip}")
                    open_host_connection(host_ip)

            # 4) Evaluate all outlets
            reevaluate_all_outlets()

        except Exception as e:
            log(f"power_control_main_loop error: {e}")

        eventlet.sleep(5)  # loop every 5 seconds

def open_host_connection(raw_host_ip):
    """
    Connect to raw_host_ip:8000 via Socket.IO (namespace=/status).
    Resolve .local hostnames before connecting.
    """
    if not raw_host_ip:
        log("[open_host_connection] ERROR: host_ip is empty.")
        return

    # Ensure we use the resolved IP for .local hostnames
    host_ip = standardize_host_ip(raw_host_ip)
    if not host_ip:
        log(f"[open_host_connection] Could not standardize empty host? Skipping.")
        return

    url = f"http://{host_ip}:8000"
    client = socketio.Client(reconnection=True, reconnection_attempts=999)

    @client.on("connect", namespace="/status")
    def on_status_connect():
        log(f"*** CONNECT EVENT to {host_ip} (namespace=/status), client.sid={client.sid}")

    @client.event
    def disconnect():
        log(f"*** DISCONNECT EVENT from {host_ip}")

    @client.on("status_update", namespace="/status")
    def on_status_update(data):
        log(f"[DEBUG] on_status_update from {host_ip} =>\n{json.dumps(data, indent=2)}")

        # Ensure valve states are stored under the resolved IP
        resolved_host_ip = standardize_host_ip(host_ip)

        valve_relays = data.get("valve_info", {}).get("valve_relays", {})
        log(f"[DEBUG] data['valve_info']['valve_relays'] => {valve_relays}")

        for valve_id_str, vinfo in valve_relays.items():
            status_str = vinfo.get("status", "off").lower()
            label_str = vinfo.get("label", f"Valve {valve_id_str}")

            remote_valve_states[(resolved_host_ip, valve_id_str)] = status_str
            remote_valve_states[(resolved_host_ip, label_str)] = status_str  # Store under both ID & Label
            log(f"    -> Storing remote_valve_states[({resolved_host_ip}, {valve_id_str})] = '{status_str}' (label='{label_str}')")

        # Evaluate power states after every update
        reevaluate_all_outlets()

    try:
        log(f"Attempting socket.io connection to {url} (namespace=/status)")
        client.connect(url, namespaces=["/status"])
        log(f"[{host_ip}] connect() completed.")
        sio_clients[host_ip] = client
    except Exception as ex:
        log(f"Error connecting to {host_ip}: {ex}")

def close_host_connection(host_ip):
    if host_ip in sio_clients:
        try:
            sio_clients[host_ip].disconnect()
        except:
            pass
        del sio_clients[host_ip]
        log(f"Closed socketio connection for {host_ip}")

def reevaluate_all_outlets():
    
    log("[DEBUG] Full remote_valve_states dump:")
    for key, value in remote_valve_states.items():
        log(f"[DEBUG]   {key} => {value}")

    settings = load_settings()
    power_controls = settings.get("power_controls", [])
    log("[reevaluate_all_outlets] Checking each power control config...")

    if remote_valve_states:
        log("Current remote_valve_states:")
        for k, v in remote_valve_states.items():
            log(f"  Key={k}, state='{v}'")
    else:
        log("No entries in remote_valve_states yet.")

    changed_any_outlet = False  # track if we changed an outlet's state

    for pc in power_controls:
        outlet_ip = pc.get("outlet_ip")
        if not outlet_ip:
            log("  This power control config has no outlet_ip. Skipping.")
            continue

        tracked_valves = pc.get("tracked_valves", [])
        log(f"  Outlet {outlet_ip} monitors these valves: {tracked_valves}")

        any_on = False
        for tv in tracked_valves:
            # Ensure hostnames are always resolved before checking
            resolve_mdns = get_resolver()
            fixed_host_ip = resolve_mdns(tv["host_ip"])
            if not fixed_host_ip:
                log(f"[ERROR] Unable to resolve {tv['host_ip']} - skipping power control check.")
                continue

            valve_id = tv["valve_id"]
            valve_label = tv.get("valve_label", "").strip()

            # Try matching by valve ID first
            current_valve_state = remote_valve_states.get((fixed_host_ip, valve_id), None)

            # If the valve ID doesn't exist, try searching by label
            if current_valve_state is None:
                current_valve_state = remote_valve_states.get((fixed_host_ip, valve_label), None)

            # Default to "off" if not found
            current_valve_state = current_valve_state or "off"
            log(f"       Found remote_valve_states[({fixed_host_ip}, {valve_id})] => '{current_valve_state}'")

            if current_valve_state == "on":
                any_on = True
                break

        desired = "on" if any_on else "off"
        old_state = last_outlet_states.get(outlet_ip)

        if old_state != desired:
            log(f"    -> Setting outlet {outlet_ip} from '{old_state}' to '{desired}'")
            set_shelly_state(outlet_ip, desired)
            last_outlet_states[outlet_ip] = desired
            changed_any_outlet = True
        else:
            log(f"    -> Outlet {outlet_ip} is already '{old_state}', no change.")

    # If we changed ANY Shelly outlet, emit a status update:
    if changed_any_outlet:
        from status_namespace import emit_status_update
        emit_status_update()

def set_shelly_state(outlet_ip, state):
    """
    Shelly switches typically toggle with:
      GET http://<outlet_ip>/relay/0?turn=on  (or off)
    """
    url = f"http://{outlet_ip}/relay/0?turn={state}"
    try:
        resp = requests.get(url, timeout=3)
        log(f"Shelly {outlet_ip} => {state}, HTTP {resp.status_code}")
    except Exception as ex:
        log(f"Error setting Shelly {outlet_ip} to {state}: {ex}")
