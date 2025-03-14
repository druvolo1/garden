import threading
import time
import requests

# Import your new helper
from utils.network_utils import standardize_host_ip

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
                sensor_state = GPIO.input(pin)
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
    from status_namespace import emit_status_update
    global _last_sensor_state

    while True:
        try:
            current_state = get_water_level_status()

            # Only act when sensor states change
            if current_state != _last_sensor_state:
                _last_sensor_state = current_state
                settings = load_settings()

                fill_sensor_key  = settings.get("fill_sensor",  "sensor1")
                drain_sensor_key = settings.get("drain_sensor", "sensor3")
                fill_valve_id    = settings.get("fill_valve")
                drain_valve_id   = settings.get("drain_valve")
                fill_valve_ip    = settings.get("fill_valve_ip")
                drain_valve_ip   = settings.get("drain_valve_ip")

                valve_labels = settings.get("valve_labels", {})
                fill_valve_label  = settings.get("fill_valve_label")  or valve_labels.get(fill_valve_id,  fill_valve_id)
                drain_valve_label = settings.get("drain_valve_label") or valve_labels.get(drain_valve_id, drain_valve_id)

                resolved_fill_ip  = standardize_host_ip(fill_valve_ip)
                resolved_drain_ip = standardize_host_ip(drain_valve_ip)

                # Fill logic
                if fill_sensor_key in current_state:
                    fill_triggered = current_state[fill_sensor_key]["triggered"]
                    if not fill_triggered and fill_valve_label:
                        turn_off_valve(fill_valve_label, resolved_fill_ip)

                # Drain logic
                if drain_sensor_key in current_state:
                    drain_triggered = current_state[drain_sensor_key]["triggered"]
                    if drain_triggered and drain_valve_label:
                        turn_off_valve(drain_valve_label, resolved_drain_ip)

                emit_status_update()

        except Exception as e:
            print(f"Exception in monitor_water_level_sensors: {e}")

        time.sleep(0.5)


def turn_off_valve(valve_label: str, valve_ip: str):
    """
    Calls /api/valve_relay/<valve_label>/off on the given IP (resolved by standardize_host_ip).
    """
    if not valve_label:
        print("[ERROR] No valve_label provided.")
        return
    if not valve_ip:
        print("[ERROR] No valve_ip provided (empty). Aborting turn_off_valve call.")
        return

    final_ip = standardize_host_ip(valve_ip)
    if final_ip:
        print(f"[DEBUG] Using resolved IP for valve control: '{final_ip}'.")
        valve_ip = final_ip

    url = f"http://{valve_ip}:8000/api/valve_relay/{valve_label}/off"

    try:
        resp = requests.post(url)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                print(f"Valve '{valve_label}' turned off successfully (http {valve_ip}).")
            else:
                print(f"[ERROR] Valve '{valve_label}' off failed: {data.get('error')}")
        else:
            print(f"[ERROR] Valve '{valve_label}' off returned HTTP {resp.status_code}")
    except Exception as ex:
        print(f"[ERROR] Exception calling valve off route for '{valve_label}' on {valve_ip}: {ex}")
