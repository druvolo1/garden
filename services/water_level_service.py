# File: services/water_level_service.py

import threading
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

import requests
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
        return  # mock environment, no-op

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
                print("Water-level pins have been initialized.")
            except Exception as e:
                print(f"Error initializing water-level pins: {e}")

def force_cleanup_and_init():
    if not GPIO:
        return
    with _pins_lock:
        global _pins_inited
        GPIO.cleanup()
        _pins_inited = False
        ensure_pins_inited()

    # Optional: if you have a status_namespace, you can emit here
    # from status_namespace import emit_status_update
    # threading.Timer(0.5, emit_status_update).start()

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
    Continuously monitor sensor changes. If the fill or drain sensor triggers,
    call the appropriate valve API route to turn that valve off.
    """
    from status_namespace import emit_status_update

    global _last_sensor_state

    while True:
        try:
            current_state = get_water_level_status()

            # Only act if there's an actual change in sensor states
            if current_state != _last_sensor_state:
                _last_sensor_state = current_state

                settings = load_settings()
                valve_info = settings.get("valve_info", {})

                # Where your fill sensor is assigned (e.g. "sensor1" => "Full")
                fill_sensor_key = valve_info.get("fill_sensor", "sensor1")
                drain_sensor_key = valve_info.get("drain_sensor", "sensor3")

                # The numeric IDs
                fill_valve_id  = valve_info.get("fill_valve")   # e.g. "1"
                drain_valve_id = valve_info.get("drain_valve")  # e.g. "2"

                # The dictionary of ID->label
                valve_labels = valve_info.get("valve_labels", {})

                # Convert the numeric ID => user-friendly name
                fill_valve_label  = valve_labels.get(fill_valve_id, fill_valve_id)
                drain_valve_label = valve_labels.get(drain_valve_id, drain_valve_id)

                # Fill logic: If the fill sensor reads "not triggered" => turn off fill
                if fill_sensor_key in current_state:
                    if not current_state[fill_sensor_key]["triggered"] and fill_valve_label:
                        turn_off_valve_by_name(fill_valve_label)

                # Drain logic: If the drain sensor reads "triggered" => turn off drain
                if drain_sensor_key in current_state:
                    if current_state[drain_sensor_key]["triggered"] and drain_valve_label:
                        turn_off_valve_by_name(drain_valve_label)

                # If you have a real-time UI, broadcast the status update
                emit_status_update()

        except Exception as e:
            print(f"Error monitoring water level sensors: {e}")

        time.sleep(0.5)

def turn_off_valve_by_name(valve_name: str):
    """
    Make a local request to /api/valve_relay/<valve_name>/off
    so that all valve logic is handled in valve_relay.py
    """
    if not valve_name:
        return

    url = f"http://127.0.0.1:8000/api/valve_relay/{valve_name}/off"
    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                print(f"Valve '{valve_name}' turned off via API route.")
            else:
                print(f"Valve '{valve_name}' off error: {data.get('error')}")
        else:
            print(f"Valve '{valve_name}' off returned HTTP {resp.status_code}.")
    except Exception as ex:
        print(f"Error calling valve off route for '{valve_name}': {ex}")
