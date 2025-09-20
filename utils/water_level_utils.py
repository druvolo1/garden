import threading
import time
import requests

# Import your new helper
from utils.network_utils import standardize_host_ip
from utils.settings_utils import load_settings
from services.valve_relay_service import turn_off_valve as turn_off_valve_local
from services.valve_relay_service import turn_on_valve as turn_on_valve_local

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

def turn_off_fill_valve():
    """
    Checks settings to see if fill_valve is 'local' or 'remote',
    then calls the correct approach.
    """
    settings = load_settings()
    fill_mode = settings.get("fill_valve_mode", "local")  # or "remote"
    fill_valve_id_str = settings.get("fill_valve")        # e.g. "1"
    fill_valve_label  = settings.get("fill_valve_label")  # e.g. "Fill 4"

    if fill_mode == "local":
        # Use the local approach
        if not fill_valve_id_str:
            print("[ERROR] fill_valve is not set, can't turn off locally.")
            return
        try:
            numeric_id = int(fill_valve_id_str)
            print(f"[DEBUG] Turning OFF fill valve locally, valve_id={numeric_id}")
            turn_off_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_off_fill_valve local failed: {ex}")
    else:
        # Remote approach: see if we have fill_valve_ip
        fill_ip = settings.get("fill_valve_ip", "")
        if not fill_ip:
            print("[ERROR] fill_valve_mode=remote but no fill_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(fill_ip)
        if final_ip:
            fill_ip = final_ip
        if not fill_valve_label:
            # fallback to something
            fill_valve_label = "FillValve"
        # Now do exactly what your old code does: call the “IP approach”
        url = f"http://{fill_ip}:8000/api/valve_relay/{fill_valve_label}/off"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Fill valve OFF success (remote).")
                else:
                    print(f"[ERROR] Fill valve OFF remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Fill valve OFF returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote fill valve OFF failed: {ex}")

def turn_on_fill_valve():
    """
    Checks settings to see if fill_valve is 'local' or 'remote',
    then calls the correct approach to turn it ON.
    """
    settings = load_settings()
    fill_mode = settings.get("fill_valve_mode", "local")  # or "remote"
    fill_valve_id_str = settings.get("fill_valve")        # e.g. "1"
    fill_valve_label  = settings.get("fill_valve_label")  # e.g. "Fill 4"

    if fill_mode == "local":
        # Use the local approach
        if not fill_valve_id_str:
            print("[ERROR] fill_valve is not set, can't turn on locally.")
            return
        try:
            numeric_id = int(fill_valve_id_str)
            print(f"[DEBUG] Turning ON fill valve locally, valve_id={numeric_id}")
            turn_on_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_on_fill_valve local failed: {ex}")
    else:
        # Remote approach: see if we have fill_valve_ip
        fill_ip = settings.get("fill_valve_ip", "")
        if not fill_ip:
            print("[ERROR] fill_valve_mode=remote but no fill_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(fill_ip)
        if final_ip:
            fill_ip = final_ip
        if not fill_valve_label:
            # fallback to something
            fill_valve_label = "FillValve"
        # Now do exactly what your old code does: call the “IP approach”
        url = f"http://{fill_ip}:8000/api/valve_relay/{fill_valve_label}/on"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Fill valve ON success (remote).")
                else:
                    print(f"[ERROR] Fill valve ON remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Fill valve ON returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote fill valve ON failed: {ex}")


def turn_off_drain_valve():
    """
    Exactly the same pattern, but for drain_valve_mode, drain_valve_ip, etc.
    """
    settings = load_settings()
    drain_mode = settings.get("drain_valve_mode", "local")
    drain_valve_id_str = settings.get("drain_valve")
    drain_valve_label  = settings.get("drain_valve_label", "")

    if drain_mode == "local":
        if not drain_valve_id_str:
            print("[ERROR] drain_valve is not set, can't turn off locally.")
            return
        try:
            numeric_id = int(drain_valve_id_str)
            print(f"[DEBUG] Turning OFF drain valve locally, valve_id={numeric_id}")
            turn_off_valve_local(numeric_id)
        except Exception as ex:
            print(f"[ERROR] turn_off_drain_valve local failed: {ex}")
    else:
        # Remote approach
        drain_ip = settings.get("drain_valve_ip", "")
        if not drain_ip:
            print("[ERROR] drain_valve_mode=remote but no drain_valve_ip is configured.")
            return
        final_ip = standardize_host_ip(drain_ip)
        if final_ip:
            drain_ip = final_ip
        if not drain_valve_label:
            drain_valve_label = "DrainValve"
        url = f"http://{drain_ip}:8000/api/valve_relay/{drain_valve_label}/off"
        try:
            resp = requests.post(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    print(f"[DEBUG] Drain valve OFF success (remote).")
                else:
                    print(f"[ERROR] Drain valve OFF remote error: {data.get('error')}")
            else:
                print(f"[ERROR] Drain valve OFF returned HTTP {resp.status_code}")
        except Exception as ex:
            print(f"[ERROR] Remote drain valve OFF failed: {ex}")

def get_water_level_status():
    sensors = load_water_level_sensors()
    ensure_pins_inited()

    print("[WaterLevel] Fetching sensor states...")

    status = {}
    if GPIO:
        for sensor_key, cfg in sensors.items():
            label = cfg.get("label", sensor_key)
            pin = cfg.get("pin")
            triggered = False
            if pin is not None:
                sensor_state = GPIO.input(pin)
                triggered = (sensor_state == 0)  # Inverted for NC: low (0) = triggered = no water / 'Not Present'
                print(f"[WaterLevel] Sensor {sensor_key} ({label}) pin {pin} state {sensor_state} triggered {triggered}")
            status[sensor_key] = {
                "label": label,
                "pin": pin,
                "triggered": triggered
            }
    else:
        # Mock environment: assume all sensors are "not triggered"
        for sensor_key, cfg in sensors.items():
            print(f"[WaterLevel] Mock sensor {sensor_key} ({cfg.get('label', sensor_key)}) triggered False")
            status[sensor_key] = {
                "label": cfg.get("label", sensor_key),
                "pin": cfg.get("pin"),
                "triggered": False
            }

    return status

def monitor_water_level_sensors():
    global _last_sensor_state
    while True:
        current_state = get_water_level_status()
        print("[WaterLevel] Current state:", current_state)
        if current_state != _last_sensor_state:
            _last_sensor_state = current_state
            settings = load_settings()

            fill_sensor_key  = settings.get("fill_sensor",  "sensor1")
            drain_sensor_key = settings.get("drain_sensor", "sensor3")
            auto_fill_key = settings.get("auto_fill_sensor", "disabled")

            print("[WaterLevel] State changed. Settings: fill_sensor=", fill_sensor_key, "drain_sensor=", drain_sensor_key, "auto_fill=", auto_fill_key)

            # For safety: always turn off fill if fill_sensor triggered
            if fill_sensor_key in current_state:
                fill_triggered = current_state[fill_sensor_key]["triggered"]
                print("[WaterLevel] Fill safety check: fill_triggered=", fill_triggered)
                if fill_triggered:
                    print("[WaterLevel] Turning off fill due to full sensor")
                    turn_off_fill_valve()

            # For auto fill: if auto_fill_sensor not triggered, and not fill_triggered, turn on fill
            if auto_fill_key != "disabled" and auto_fill_key in current_state:
                auto_triggered = current_state[auto_fill_key]["triggered"]
                fill_triggered = current_state.get(fill_sensor_key, {"triggered": False})["triggered"]
                print("[WaterLevel] Auto fill check: auto_triggered=", auto_triggered, "fill_triggered=", fill_triggered)
                if not auto_triggered and not fill_triggered:
                    print("[WaterLevel] Turning on fill for auto")
                    turn_on_fill_valve()

            # If drain sensor is triggered => we want to turn off drain valve
            if drain_sensor_key in current_state:
                drain_triggered = current_state[drain_sensor_key]["triggered"]
                print("[WaterLevel] Drain check: drain_triggered=", drain_triggered)
                if drain_triggered:
                    print("[WaterLevel] Turning off drain due to empty sensor")
                    turn_off_drain_valve()

            from status_namespace import emit_status_update
            emit_status_update()
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