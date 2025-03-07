import eventlet
eventlet.monkey_patch()

import socketio  # pip install "python-socketio[client]"
from utils.settings_utils import load_settings
from datetime import datetime
import requests

remote_valve_states = {}  # (host_ip, valve_id) -> "on"/"off"
last_outlet_states = {}   # outlet_ip -> "on"/"off"
sio_clients = {}          # host_ip -> socketio.Client instance

def log(msg):
    print(f"[PowerControlService] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

def power_control_main_loop():
    while True:
        try:
            settings = load_settings()
            power_controls = settings.get("power_controls", [])

            # 1) Gather all host_ips we need from the tracked valves
            needed_hosts = set()
            for pc in power_controls:
                for tv in pc.get("tracked_valves", []):
                    needed_hosts.add(tv["host_ip"])

            log(f"[power_control_main_loop] Needed hosts for power control: {needed_hosts}")

            # 2) Close any old connections we no longer need
            for old_host in list(sio_clients.keys()):
                if old_host not in needed_hosts:
                    close_host_connection(old_host)

            # 3) Ensure we have a socket.io connection for each needed host
            for host_ip in needed_hosts:
                log(f"[power_control_main_loop] Checking if {host_ip} is in sio_clients => {host_ip in sio_clients}")
                if host_ip not in sio_clients:
                    log(f"[power_control_main_loop] Opening socket.io connection to {host_ip}")
                    open_host_connection(host_ip)

            # 4) Re-check all power outlet states
            reevaluate_all_outlets()

        except Exception as e:
            log(f"power_control_main_loop error: {e}")

        eventlet.sleep(5)  # re-check every 5 seconds

def open_host_connection(host_ip):
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
        for valve_id_str, vinfo in valve_relays.items():
            status_str = vinfo.get("status", "off")
            remote_valve_states[(host_ip, int(valve_id_str))] = status_str.lower()
        reevaluate_all_outlets()

    try:
        log(f"Attempting socket.io connection to {url} (namespace=/status)")
        client.connect(url, namespaces=["/status"])
        log(f"[{host_ip}] connect() call completed.")
        sio_clients[host_ip] = client
    except Exception as e:
        log(f"Error connecting to {host_ip}: {e}")

def reevaluate_all_outlets():
    settings = load_settings()
    power_controls = settings.get("power_controls", [])
    log("[reevaluate_all_outlets] Checking each power control config...")

    for pc in power_controls:
        outlet_ip = pc.get("outlet_ip")
        if not outlet_ip:
            log("  No outlet_ip set in this power control config, skipping.")
            continue

        tracked = pc.get("tracked_valves", [])
        log(f"  Outlet {outlet_ip} monitors these valves: {tracked}")

        any_on = False
        for tv in tracked:
            host_ip = tv["host_ip"]
            valve_id = tv["valve_id"]

            current_valve_state = remote_valve_states.get((host_ip, valve_id), "off")
            log(f"    -> Checking valve (host={host_ip}, id={valve_id}) => {current_valve_state}")

            if current_valve_state == "on":
                any_on = True
                break

        desired = "on" if any_on else "off"
        current_outlet_state = last_outlet_states.get(outlet_ip)

        if current_outlet_state != desired:
            log(f"    -> Setting outlet {outlet_ip} from {current_outlet_state} to {desired}")
            set_shelly_state(outlet_ip, desired)
            last_outlet_states[outlet_ip] = desired
        else:
            log(f"    -> Outlet {outlet_ip} is already {current_outlet_state}, no change.")

def close_host_connection(host_ip):
    if host_ip in sio_clients:
        try:
            sio_clients[host_ip].disconnect()
        except:
            pass
        del sio_clients[host_ip]
        log(f"Closed socketio connection for {host_ip}")

def set_shelly_state(outlet_ip, state):
    """
    Send a GET request to the Shelly for on/off
      e.g. http://192.168.1.50/relay/0?turn=on
    """
    url = f"http://{outlet_ip}/relay/0?turn={state}"
    try:
        resp = requests.get(url, timeout=3)
        log(f"Shelly {outlet_ip} => {state}, HTTP {resp.status_code}")
    except Exception as e:
        log(f"Error setting Shelly {outlet_ip} to {state}: {e}")
