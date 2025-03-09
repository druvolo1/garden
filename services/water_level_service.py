import threading
import time
import socket
import requests

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

from utils.settings_utils import load_settings

_pins_lock = threading.Lock()
_pins_inited = False
_last_sensor_state = {}

def load_water_level_sensors():
    s = load_settings()
    default_sensors = {
        "sensor1": {"label": "Full",  "pin": 17},
        "sensor2": {"label": "3 Gal", "pin": 18},
        "sensor3": {"label": "Empty", "pin": 19},
    }
    return s.get("water_level_sensors", default_sensors)

def ensure_pins_inited():
    global _pins_inited
    if not GPIO:
        print("[WaterLevel DEBUG] Mock environment, no GPIO setup.")
        return

    with _pins_lock:
        if not _pins_inited:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                sensors = load_water_level_sensors()
                for sensor_key, cfg in sensors.items():
                    pin = cfg.get("pin")
                    if pin is not None:
                        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                _pins_inited = True
            except Exception as e:
                print(f"[WaterLevel DEBUG] Error initializing water-level pins: {e}")

def force_cleanup_and_init():
    if not GPIO:
        return

    with _pins_lock:
        global _pins_inited
        GPIO.cleanup()
        _pins_inited = False
        ensure_pins_inited()

def get_water_level_status():
    sensors = load_water_level_sensors()
    ensure_pins_inited()

    status = {}
    if GPIO:
        for sensor_key, cfg in sensors.items():
            label = cfg.get("label", sensor_key)
            pin = cfg.get("pin")
            triggered = False
            if pin is not None:
                sensor_state = GPIO.input(pin)  # 0 or 1
                triggered = (sensor_state == 1)
            status[sensor_key] = {
                "label": label,
                "pin": pin,
                "triggered": triggered
            }
    else:
        # Mock environment: assume all sensors are "not triggered"
        for sensor_key, cfg in sensors.items():
            status[sensor_key] = {
                "label": cfg.get("label", sensor_key),
                "pin": cfg.get("pin"),
                "triggered": False
            }

    return status

def monitor_water_level_sensors():
    """
    Continuously monitors sensor changes.
    If the fill sensor is "not triggered" => turn OFF the fill valve.
    If the drain sensor is "triggered" => turn OFF the drain valve.

    Because your settings store fill/drain info at the top level,
    we read fill_valve_ip, fill_valve, fill_sensor, etc. from settings directly.
    """
    from status_namespace import emit_status_update

    global _last_sensor_state

    while True:
        try:
            current_state = get_water_level_status()

            # Only act when sensor states change
            if current_state != _last_sensor_state:
                _last_sensor_state = current_state

                settings = load_settings()

                # Pull these keys from the TOP LEVEL of the settings
                fill_sensor_key  = settings.get("fill_sensor",  "sensor1")
                drain_sensor_key = settings.get("drain_sensor", "sensor3")

                fill_valve_id  = settings.get("fill_valve")   # e.g. "1"
                drain_valve_id = settings.get("drain_valve")  # e.g. "2"

                fill_valve_ip  = settings.get("fill_valve_ip")   # e.g. "zone4.local" or "172.16.1.xxx"
                drain_valve_ip = settings.get("drain_valve_ip")

                # Also read the valve_labels from top-level (like your JSON)
                valve_labels = settings.get("valve_labels", {})
                fill_valve_label  = valve_labels.get(fill_valve_id,  fill_valve_id)
                drain_valve_label = valve_labels.get(drain_valve_id, drain_valve_id)

                # Fill logic: "If fill sensor is NOT triggered => OFF"
                if fill_sensor_key in current_state:
                    fill_triggered = current_state[fill_sensor_key]["triggered"]
                    # If sensor is "not triggered," we want to shut off the fill valve
                    if not fill_triggered and fill_valve_label:
                        turn_off_valve(fill_valve_label, fill_valve_ip)

                # Drain logic: "If drain sensor is triggered => OFF"
                if drain_sensor_key in current_state:
                    drain_triggered = current_state[drain_sensor_key]["triggered"]
                    if drain_triggered and drain_valve_label:
                        turn_off_valve(drain_valve_label, drain_valve_ip)

                # Emit a status update for any connected UI
                emit_status_update()

        except Exception as e:
            print(f"Exception in monitor_water_level_sensors: {e}")

        time.sleep(0.5)

def get_local_ip_address():
    """
    Returns the Pi's primary IP address for local connections
    (the one you'd normally get with 'hostname -I' or a socket trick).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # connect to a public IP just to pick the default interface
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()

def turn_off_valve(valve_label: str, valve_ip: str):
    """
    Decides whether to send the request locally or to a remote device
    based on whether `valve_ip` is empty or not. Then calls the name-based
    route in valve_relay.py, e.g. /api/valve_relay/<valve_label>/off.

    NEW LOGIC:
    - If valve_ip is something like "zone4.local" or "Zone4.local", let's replace
      it with our own IP from get_local_ip_address().
    """
    if not valve_label:
        return

    # If user configured the IP as "[system_name].local", override with local IP
    # for example, if your system_name is "zone4"
    # You can get your actual system_name from a config or use 'socket.gethostname()'
    # For simplicity, just check if it ends with '.local'
    if valve_ip and valve_ip.lower().endswith(".local"):
        # Replace with the Pi's IP
        resolved_ip = get_local_ip_address()
        print(f"[DEBUG] valve_ip '{valve_ip}' replaced with local IP '{resolved_ip}'.")
        valve_ip = resolved_ip

    if not valve_ip:
        # If still empty or was never set, default to 127.0.0.1
        url = f"http://127.0.0.1:8000/api/valve_relay/{valve_label}/off"
    else:
        url = f"http://{valve_ip}:8000/api/valve_relay/{valve_label}/off"

    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                print(f"Valve '{valve_label}' turned off successfully (http {valve_ip or 'localhost'}).")
            else:
                print(f"Valve '{valve_label}' off error: {data.get('error')}")
        else:
            print(f"Valve '{valve_label}' off returned HTTP {resp.status_code}")
    except Exception as ex:
        print(f"Exception calling valve off route for '{valve_label}' on {valve_ip}: {ex}")
