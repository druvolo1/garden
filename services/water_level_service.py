# File: services/water_level_service.py
import threading

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

from utils.settings_utils import load_settings  # Import from utils

# A global lock and a flag that indicates if we've fully initialized pins
_pins_lock = threading.Lock()
_pins_inited = False

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
            # We do a full setup
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
        # Now calling ensure_pins_inited() will do the new setup
        ensure_pins_inited()

    # Emit a status update to notify all clients immediately
    from status_namespace import emit_status_update  # Import emit_status_update
    emit_status_update()

def get_water_level_status():
    """
    Return a dict with each sensor’s label, pin, and triggered state.
    """
    sensors = load_water_level_sensors()
    ensure_pins_inited()  # Make sure pins are set up before reading

    status = {}
    for sensor_key, cfg in sensors.items():
        label = cfg.get("label", sensor_key)
        pin = cfg.get("pin")
        triggered = False
        if GPIO and pin is not None:
            sensor_state = GPIO.input(pin)  # This is safe now that pins are inited
            triggered = (sensor_state == 0)
        status[sensor_key] = {
            "label": label,
            "pin": pin,
            "triggered": triggered
        }
    return status