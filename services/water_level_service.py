# File: services/water_level_service.py

try:
    import RPi.GPIO as GPIO
except ImportError:
    # Mock environment for non-Pi
    GPIO = None
    print("RPi.GPIO not available. Using mock environment.")

import sys
from api.settings import load_settings

def load_water_level_sensors():
    """
    Read sensor definitions from settings['water_level_sensors'] or fallback defaults.
    Example structure:
    {
      "sensor1": { "label": "Full",  "pin": 22 },
      "sensor2": { "label": "3 Gal", "pin": 23 },
      "sensor3": { "label": "Empty", "pin": 24 }
    }
    """
    s = load_settings()
    default_sensors = {
        "sensor1": {"label": "Full",  "pin": 22},
        "sensor2": {"label": "3 Gal", "pin": 23},
        "sensor3": {"label": "Empty", "pin": 24},
    }
    return s.get("water_level_sensors", default_sensors)

def setup_water_level_pins():
    """
    Re-initialize water-level sensor pins. If pins changed, this ensures new pins are set.
    1) Cleanup any existing config
    2) setmode(GPIO.BCM)
    3) set up each sensor's pin as input
    """
    if not GPIO:
        print("Skipping GPIO setup (mock environment).")
        return

    # Cleanup everything: frees up pins so we can re-set them
    GPIO.cleanup()

    # Re-establish BCM mode
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    sensors = load_water_level_sensors()
    for sensor_key, cfg in sensors.items():
        pin = cfg.get("pin")
        if pin is not None:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def get_water_level_status():
    """
    Return a dict with sensor label, pin, and triggered state.
    'triggered' depends on your hardware logic (HIGH vs LOW).
    Example:
      {
        "sensor1": {"label": "Full",   "pin": 22, "triggered": True},
        "sensor2": {"label": "3 Gal",  "pin": 23, "triggered": False},
        "sensor3": {"label": "Empty",  "pin": 24, "triggered": False}
      }
    """
    sensors = load_water_level_sensors()
    status = {}

    for sensor_key, cfg in sensors.items():
        label = cfg.get("label", sensor_key)
        pin = cfg.get("pin")
        triggered = False
        if GPIO and pin is not None:
            # For typical float sensors or contact sensors, you may find
            # that "GPIO.input(pin) == 0" means "triggered". Adjust as needed.
            sensor_state = GPIO.input(pin)
            triggered = (sensor_state == 0)
        status[sensor_key] = {
            "label": label,
            "pin": pin,
            "triggered": triggered
        }
    return status
