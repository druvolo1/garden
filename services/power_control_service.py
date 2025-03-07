# File: services/power_control_service.py

import eventlet
import requests
import traceback
from utils.settings_utils import load_settings
from datetime import datetime

# This dictionary holds the last known state of (host_ip, valve_id).
# For instance: remote_valve_states[("192.168.1.51", 2)] = "on"
remote_valve_states = {}

# This dictionary holds the last known ON/OFF state we set for each outlet IP
last_outlet_states = {}

def log(msg):
    print(f"[PowerControlService] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)

def start_power_control_loop():
    """
    Spawns a green thread that periodically:
      1) Reloads settings (power_controls).
      2) For each remote host we haven't polled recently, calls /api/valve_relay/all_status.
      3) Updates remote_valve_states.
      4) Evaluates whether each Shelly outlet should be ON or OFF.
      5) Sends the command to the Shelly if there's a change.
    """
    eventlet.spawn(power_control_main_loop)
    log("Power Control loop spawned.")

def power_control_main_loop():
    while True:
        try:
            # 1) Load the settings each iteration
            settings = load_settings()
            power_controls = settings.get("power_controls", [])

            # 2) Identify all unique remote IP:port we need to poll
            all_hosts = set()
            for pc in power_controls:
                tv = pc.get("tracked_valves", [])
                for item in tv:
                    all_hosts.add(item["host_ip"])  # simple approach, no port splitting

            # 3) Poll each host for its valve status
            for host_ip in all_hosts:
                poll_remote_valves(host_ip)

            # 4) Decide each outlet state
            for pc in power_controls:
                outlet_ip = pc.get("outlet_ip")
                if not outlet_ip:
                    continue
                tracked_valves = pc.get("tracked_valves", [])

                # if any valve is "on", we want the outlet on
                any_on = False
                for tv in tracked_valves:
                    # default off if missing
                    state = remote_valve_states.get((tv["host_ip"], tv["valve_id"]), "off")
                    if state == "on":
                        any_on = True
                        break

                desired_state = "on" if any_on else "off"
                # Compare with last known
                if last_outlet_states.get(outlet_ip) != desired_state:
                    # set Shelly
                    set_shelly_state(outlet_ip, desired_state)
                    last_outlet_states[outlet_ip] = desired_state

        except Exception as e:
            log(f"Error in power_control_main_loop: {e}")
            traceback.print_exc()

        # Sleep a bit before next cycle
        eventlet.sleep(5)

def poll_remote_valves(host_ip):
    """
    Poll remote host for /api/valve_relay/all_status
    and update remote_valve_states accordingly.
    """
    try:
        url = f"http://{host_ip}:8000/api/valve_relay/all_status"
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("status") == "success":
            # data.valves might be { "1": {label:..., status:"on"}, "2":... }
            valves_dict = data.get("valves", {})
            for valve_id_str, vinfo in valves_dict.items():
                st = vinfo.get("status", "off")
                key = (host_ip, int(valve_id_str))
                remote_valve_states[key] = st.lower()
        else:
            log(f"Remote host {host_ip} returned error: {data}")
    except Exception as e:
        log(f"poll_remote_valves() error for {host_ip}: {e}")
        # If unreachable, we could assume "off" or keep old state. We'll leave old state for now.

def set_shelly_state(outlet_ip, state):
    """
    Attempt to set the Shelly to ON or OFF using a GET request.
    For a Shelly Plug, typically: http://<ip>/relay/0?turn=on or ?turn=off
    """
    shelly_url = f"http://{outlet_ip}/relay/0?turn={state}"
    try:
        resp = requests.get(shelly_url, timeout=3)
        log(f"Set Shelly at {outlet_ip} to {state}, response code {resp.status_code}")
    except Exception as e:
        log(f"Error setting Shelly {outlet_ip} to {state}: {e}")
