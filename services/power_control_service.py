# File: services/power_control_service.py

import eventlet
eventlet.monkey_patch()

import socketio
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
    """
    Main loop: checks 'power_controls' in settings, ensures socket.io connections
    for each tracked valve host, then reevaluates Shelly outlets.
    """
    while True:
        try:
            settings = load_settings()
            power_controls = settings.get("power_controls", [])

            needed_hosts = set()
            for pc in power_controls:
                for tv in pc.get("tracked_valves", []):
                    needed_hosts.add(tv["host_ip"])

            log(f"[power_control_main_loop] Needed hosts for power control: {needed_hosts}")

            # Close old, unused connections
            for old_host in list(sio_clients.keys()):
                if old_host not in needed_hosts:
                    close_host_connection(old_host)

            # Open connections for new needed hosts
            for host_ip in needed_hosts:
                log(f"[power_control_main_loop] Checking if {host_ip} is in sio_clients => {host_ip in sio_clients}")
                if host_ip not in sio_clients:
                    log(f"[power_control_main_loop] Opening socket.io connection to {host_ip}")
                    open_host_connection(host_ip)

            # Evaluate Shelly on/off logic
            reevaluate_all_outlets()

        except Exception as e:
            log(f"power_control_main_loop error: {e}")

        eventlet.sleep(5)  # re-check every 5s

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
        log(f"[DEBUG] on_status_update from {host_ip} => {data}")
        valve_relays = data.get("valve_info", {}).get("valve_relays", {})

        # For each valve_id, store as string-based keys
        for valve_id_str, vinfo in valve_relays.items():
            status_str = vinfo.get("status", "off").lower()
            remote_valve_states[(host_ip, valve_id_str)] = status_str
            log(f"    -> Storing remote_valve_states[({host_ip}, {valve_id_str})] = {status_str}")

        # After we update, reevaluate Shelly states
        reevaluate_all_outlets()

    try:
        log(f"Attempting socket.io connection to {url} (namespace=/status)")
        client.connect(url, namespaces=["/status"])
        log(f"[{host_ip}] connect() call completed.")
        sio_clients[host_ip] = client
    except Exception as e:
        log(f"Error connecting to {host_ip}: {e}")

def close_host_connection(host_ip):
    """
    Disconnect from the given host_ip and remove from sio_clients.
    """
    if host_ip in sio_clients:
        try:
            sio_clients[host_ip].disconnect()
        except:
            pass
        del sio_clients[host_ip]
        log(f"Closed socketio connection for {host_ip}")

def reevaluate_all_outlets():
    """
    For each outlet in 'power_controls', if any tracked valve is 'on', turn it on; otherwise off.
    """
    settings = load_settings()
    power_controls = settings.get("power_controls", [])
    log("[reevaluate_all_outlets] Checking each power control config...")

    # Debug: show which keys we have in remote_valve_states
    all_keys = list(remote_valve_states.keys())
    log(f"Current keys in remote_valve_states: {all_keys}")

    for pc in power_controls:
        outlet_ip = pc.get("outlet_ip")
        if not outlet_ip:
            log("  No outlet_ip set for this power control config, skipping.")
            continue

        tracked = pc.get("tracked_valves", [])
        log(f"  Outlet {outlet_ip} monitors these valves: {tracked}")

        any_on = False
        for tv in tracked:
            host_ip = tv["host_ip"]
            valve_id_str = tv["valve_id"]  # we assume settings stores it as string

            key = (host_ip, valve_id_str)
            current_valve_state = remote_valve_states.get(key, "off")

            log(f"    -> Looking up remote_valve_states[{key}] => '{current_valve_state}'")
            log(f"    -> Comparing '{current_valve_state}' == 'on'?")

            if current_valve_state == "on":
                any_on = True
                log("    -> We found a valve that is on, so we'll turn the outlet on.")
                break

        desired = "on" if any_on else "off"
        current_outlet_state = last_outlet_states.get(outlet_ip)

        if current_outlet_state != desired:
            log(f"    -> Setting outlet {outlet_ip} from {current_outlet_state} to {desired}")
            set_shelly_state(outlet_ip, desired)
            last_outlet_states[outlet_ip] = desired
        else:
            log(f"    -> Outlet {outlet_ip} is already {current_outlet_state}, no change.")

def set_shelly_state(outlet_ip, state):
    """
    Send GET to Shelly: http://outlet_ip/relay/0?turn=on (or off).
    """
    url = f"http://{outlet_ip}/relay/0?turn={state}"
    try:
        resp = requests.get(url, timeout=3)
        log(f"Shelly {outlet_ip} => {state}, HTTP {resp.status_code}")
    except Exception as e:
        log(f"Error setting Shelly {outlet_ip} to {state}: {e}")
