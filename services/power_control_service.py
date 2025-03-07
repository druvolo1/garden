# File: services/power_control_service.py

import eventlet
eventlet.monkey_patch()

import socketio  # pip install "python-socketio[client]"
from utils.settings_utils import load_settings
from datetime import datetime
import requests

remote_valve_states = {}  # (host_ip, valve_id_str) -> "on"/"off"
last_outlet_states = {}   # outlet_ip -> "on"/"off"
sio_clients = {}          # host_ip -> socketio.Client instance

def log(msg):
    print(f"[PowerControlService] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

def start_power_control_loop():
    """
    Spawns the background thread to connect to remote valves & control Shelly outlets.
    """
    eventlet.spawn(power_control_main_loop)
    log("Power Control loop started.")

def power_control_main_loop():
    while True:
        try:
            settings = load_settings()
            power_controls = settings.get("power_controls", [])

            # 1) Gather host IPs from the 'tracked_valves' entries
            needed_hosts = set()
            for pc in power_controls:
                for tv in pc.get("tracked_valves", []):
                    needed_hosts.add(tv["host_ip"])

            log(f"[power_control_main_loop] Needed hosts for power control: {needed_hosts}")

            # 2) Close any old connections that are no longer needed
            for old_host in list(sio_clients.keys()):
                if old_host not in needed_hosts:
                    close_host_connection(old_host)

            # 3) Ensure we have a socket.io connection to each needed host
            for host_ip in needed_hosts:
                already_connected = (host_ip in sio_clients)
                log(f"[power_control_main_loop] Checking if {host_ip} is in sio_clients => {already_connected}")
                if not already_connected:
                    log(f"[power_control_main_loop] Opening socket.io connection to {host_ip}")
                    open_host_connection(host_ip)

            # 4) Evaluate all outlets
            reevaluate_all_outlets()

        except Exception as e:
            log(f"power_control_main_loop error: {e}")

        eventlet.sleep(5)  # loop every 5s

def open_host_connection(host_ip):
    """
    Connect to host_ip:8000/status via Socket.IO. Listen for 'status_update'.
    """
    url = f"http://{host_ip}:8000"
    client = socketio.Client(reconnection=True, reconnection_attempts=999)

    @client.event
    def connect():
        log(f"*** CONNECT EVENT *** to {host_ip}, client.sid={client.sid}")

    @client.event
    def disconnect():
        log(f"*** DISCONNECT EVENT *** from {host_ip}")

    def open_host_connection(host_ip):
    """
    Connect to host_ip:8000/status via Socket.IO. Listen for 'status_update'.
    """
    url = f"http://{host_ip}:8000"
    client = socketio.Client(reconnection=True, reconnection_attempts=999)

    @client.event
    def connect():
        log(f"*** CONNECT EVENT *** to {host_ip}, client.sid={client.sid}")

    @client.event
    def disconnect():
        log(f"*** DISCONNECT EVENT *** from {host_ip}")

    @client.on("status_update")
    def on_status_update(data):
        import json

        # Print the entire JSON with indentation
        log(f"[DEBUG] on_status_update from {host_ip} =>\n{json.dumps(data, indent=2)}")

        # Also log the top-level keys, to confirm if "valve_info" is present
        top_level_keys = list(data.keys())
        log(f"[DEBUG] Top-level keys: {top_level_keys}")

        # Now retrieve "valve_relays" from inside "valve_info"
        valve_relays = data.get("valve_info", {}).get("valve_relays", {})
        log(f"[DEBUG] Checking data['valve_info']['valve_relays'] => {valve_relays}")

        for valve_id_str, vinfo in valve_relays.items():
            status_str = vinfo.get("status", "off").lower()
            label_str  = vinfo.get("label", f"Valve {valve_id_str}")
            remote_valve_states[(host_ip, valve_id_str)] = {
                "status": status_str,
                "label": label_str
            }
            log(f"    -> Storing remote_valve_states[({host_ip}, {valve_id_str})] = "
                f"{{status={status_str}, label={label_str}}}")

        # Reevaluate after updating
        reevaluate_all_outlets()

    try:
        log(f"Attempting socket.io connection to {url} (namespace=/status)")
        client.connect(url, namespaces=["/status"])
        log(f"[{host_ip}] connect() call completed.")
        sio_clients[host_ip] = client
    except Exception as e:
        log(f"Error connecting to {host_ip}: {e}")


def close_host_connection(host_ip):
    if host_ip in sio_clients:
        try:
            sio_clients[host_ip].disconnect()
        except:
            pass
        del sio_clients[host_ip]
        log(f"Closed socketio connection for {host_ip}")

def reevaluate_all_outlets():
    """
    For each outlet in 'power_controls', if any tracked valve is 'on', turn Shelly on; else off.
    """
    settings = load_settings()
    power_controls = settings.get("power_controls", [])
    log("[reevaluate_all_outlets] Checking each power control config...")

    # Show the entire remote_valve_states keys/values for debugging
    if remote_valve_states:
        log("Current remote_valve_states:")
        for k, v in remote_valve_states.items():
            log(f"  Key: {k} => '{v}'")
    else:
        log("No entries in remote_valve_states yet.")

    for pc in power_controls:
        outlet_ip = pc.get("outlet_ip")
        if not outlet_ip:
            log("  This power control config has no outlet_ip, skipping.")
            continue

        tracked_valves = pc.get("tracked_valves", [])
        log(f"  Outlet {outlet_ip} monitors these valves: {tracked_valves}")

        any_on = False
        for tv in tracked_valves:
            host_ip = tv["host_ip"]
            valve_id_str = tv["valve_id"]  # treat as a string

            # Create the dictionary key
            key = (host_ip, valve_id_str)
            current_valve_state = remote_valve_states.get(key, "off")

            log(f"    -> Checking valve {key}")
            log(f"       Found remote_valve_states[{key}] => '{current_valve_state}'")
            log(f"       Is '{current_valve_state}' == 'on'?")

            if current_valve_state == "on":
                log("       Yes, so this valve is on -> any_on = True")
                any_on = True
                break
            else:
                log("       No, so keep checking any others...")

        desired = "on" if any_on else "off"
        current_outlet_state = last_outlet_states.get(outlet_ip)

        if current_outlet_state != desired:
            log(f"    -> Setting outlet {outlet_ip} from '{current_outlet_state}' to '{desired}'")
            set_shelly_state(outlet_ip, desired)
            last_outlet_states[outlet_ip] = desired
        else:
            log(f"    -> Outlet {outlet_ip} is already '{current_outlet_state}', no change.")


def set_shelly_state(outlet_ip, state):
    """
    Sends a GET to the Shelly for on/off:
      http://<outlet_ip>/relay/0?turn=on
    """
    url = f"http://{outlet_ip}/relay/0?turn={state}"
    try:
        resp = requests.get(url, timeout=3)
        log(f"Shelly {outlet_ip} => {state}, HTTP {resp.status_code}")
    except Exception as e:
        log(f"Error setting Shelly {outlet_ip} to {state}: {e}")
