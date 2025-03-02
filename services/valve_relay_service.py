# File: services/water_level_service.py

import threading
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

from utils.settings_utils import load_settings  # Import from utils

_pins_lock = threading.Lock()
_pins_inited = False

# Store the last known state of the sensors
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
    """
    Safely ensure that GPIO.setmode() and GPIO.setup() have been called exactly once
    or after pins are changed. Any code reading the pins should call this first.
    """
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
    """
    If user updates pins, we do a full GPIO.cleanup(), then re-init.
    This is called from update_settings() after water_level_sensors changes.
    """
    if not GPIO:
        return
    with _pins_lock:
        global _pins_inited
        GPIO.cleanup()
        _pins_inited = False
        ensure_pins_inited()

    from status_namespace import emit_status_update
    threading.Timer(0.5, emit_status_update).start()

def get_water_level_status():
    """
    Return a dict with each sensor’s label, pin, and triggered state.
    triggered == True means the pin reads '1' (HIGH).
    """
    sensors = load_water_level_sensors()
    ensure_pins_inited()  # Make sure pins are set up before reading

    status = {}
    for sensor_key, cfg in sensors.items():
        label = cfg.get("label", sensor_key)
        pin = cfg.get("pin")
        triggered = False
        if GPIO and pin is not None:
            sensor_state = GPIO.input(pin)  # 0 or 1
            triggered = (sensor_state == 1)
        status[sensor_key] = {
            "label": label,
            "pin": pin,
            "triggered": triggered
        }
    return status

def monitor_water_level_sensors():
    """
    Continuously monitor sensor changes. If the fill or drain sensor triggers,
    turn off its associated valve.
    
    This function should be started in a background thread, for example
    in your Flask app startup or main script. 
    """
    from services.valve_relay_service import (
        get_valve_id_by_name,
        turn_off_valve,
        is_valve_on
    )
    from status_namespace import emit_status_update

    global _last_sensor_state

    while True:
        try:
            current_state = get_water_level_status()

            # Compare with the previously stored state to detect changes
            if current_state != _last_sensor_state:
                _last_sensor_state = current_state

                # Load which sensors/valves are assigned for fill & drain
                settings = load_settings()
                fill_sensor_key  = settings.get("water_fill_sensor")   # e.g. "sensor1"
                drain_sensor_key = settings.get("water_drain_sensor")  # e.g. "sensor3"
                fill_valve_name  = settings.get("water_fill_valve")    # e.g. "Fill"
                drain_valve_name = settings.get("water_drain_valve")   # e.g. "Drain"

                # If the assigned fill sensor is triggered, turn off the fill valve
                if fill_sensor_key and fill_sensor_key in current_state:
                    if current_state[fill_sensor_key]["triggered"]:  # If sensor is HIGH
                        if fill_valve_name:
                            fill_valve_id = get_valve_id_by_name(fill_valve_name)
                            if fill_valve_id and is_valve_on(fill_valve_id):
                                turn_off_valve(fill_valve_id)
                                print(f"Fill sensor '{fill_sensor_key}' triggered; turning off valve '{fill_valve_name}'.")

                # If the assigned drain sensor is triggered, turn off the drain valve
                if drain_sensor_key and drain_sensor_key in current_state:
                    if current_state[drain_sensor_key]["triggered"]:
                        if drain_valve_name:
                            drain_valve_id = get_valve_id_by_name(drain_valve_name)
                            if drain_valve_id and is_valve_on(drain_valve_id):
                                turn_off_valve(drain_valve_id)
                                print(f"Drain sensor '{drain_sensor_key}' triggered; turning off valve '{drain_valve_name}'.")

                # Emit a status update so clients see changes right away
                emit_status_update()

        except Exception as e:
            print(f"Error monitoring water level sensors: {e}")

        time.sleep(0.5)
