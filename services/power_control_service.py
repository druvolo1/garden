# File: services/power_control_service.py

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

def start_power_control_loop():
    """
    Creates an Eventlet green thread to watch for changes in power_controls
    and maintain socketio connections to remote hosts.
    """
    eventlet.spawn(power_control_main_loop)
    log("Power Control loop started.")

def power_control_main_loop():
    while True:
        try:
            settings = load_settings()
            power_controls = settings.get("power_controls", [])
            
            # 1) Gather all host_ips we need to connect to
            needed_hosts = set()
            for pc in power_controls:
                for tv in pc.get("tracked_valves", []):
                    needed_hosts.add(tv["host_ip"])
            
            # 2) Close any old connections we no longer need
            for old_host in list(sio_clients.keys()):
                if old_host not in needed_hosts:
                    close_host_connection(old_host)
            
            # 3) Ensure we have a socketio connection for each needed host
            for host_ip in needed_hosts:
                if host_ip not in sio_clients:
                    open_host_connection(host_ip)
            
            # We don't strictly need to do anything else in this loop
            # because updates are handled by real-time socket events.
            # But we might occasionally reevaluate all outlets
            # in case settings changed (like removing a tracked valve).
            reevaluate_all_outlets()
            
        except Exception as e:
            log(f"power_control_main_loop error: {e}")
        
        eventlet.sleep(5)  # re-check for changed settings every 5s

# File: services/power_control_service.py

def open_host_connection(host_ip):
    url = f"http://{host_ip}:8000"
    client = socketio.Client(reconnection=True, reconnection_attempts=999)

    @client.event
    def connect():
        log(f"*** CONNECT EVENT *** to {host_ip}")
        log(f"[DEBUG] client.sid={client.sid}")

    @client.event
    def disconnect():
        log(f"*** DISCONNECT EVENT *** from {host_ip}")

    @client.on("status_update")
    def on_status_update(data):
        log(f"[DEBUG] on_status_update from {host_ip} => {data}")
        valve_relays = data.get("valve_info", {}).get("valve_relays", {})
        for valve_id_str, vinfo in valve_relays.items():
            status_str = vinfo.get("status", "off")
            key = (host_ip, int(valve_id_str))
            remote_valve_states[key] = status_str.lower()
        reevaluate_all_outlets()

    try:
        log(f"Attempting socket.io connection to {url} (namespace=/status)")
        client.connect(url, namespaces=["/status"])  
        log(f"[{host_ip}] connect() call done. If successful, 'connect()' event logs will follow.")
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
    Looks at remote_valve_states, then sets each Shelly outlet on/off if needed.
    """
    settings = load_settings()
    power_controls = settings.get("power_controls", [])
    
    for pc in power_controls:
        outlet_ip = pc.get("outlet_ip")
        if not outlet_ip:
            continue
        tracked = pc.get("tracked_valves", [])
        
        any_on = False
        for tv in tracked:
            st = remote_valve_states.get((tv["host_ip"], tv["valve_id"]), "off")
            if st == "on":
                any_on = True
                break
        
        desired = "on" if any_on else "off"
        if last_outlet_states.get(outlet_ip) != desired:
            set_shelly_state(outlet_ip, desired)
            last_outlet_states[outlet_ip] = desired

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
