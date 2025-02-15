# File: services/water_level_service.py

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)  # Disable warnings about pins already in use
except ImportError:
    print("RPi.GPIO not available. Using mock environment.")

from api.settings import load_settings

def load_water_level_sensors():
    """
    Load the water-level sensor config from settings, which should look like:
      {
        "sensor1": {"label": "Full", "pin": 22},
        "sensor2": {"label": "3 Gal", "pin": 23},
        "sensor3": {"label": "Empty", "pin": 24}
      }
    If not present, fall back to defaults.
    """
    s = load_settings()
    default_sensors = {
        "sensor1": {"label": "Full",   "pin": 22},
        "sensor2": {"label": "3 Gal",  "pin": 23},
        "sensor3": {"label": "Empty",  "pin": 24},
    }
    return s.get("water_level_sensors", default_sensors)

def setup_water_level_pins():
    """
    Configure each sensor's pin as input with pull-up.
    Call this at startup or after sensor pin changes.
    """
    sensors = load_water_level_sensors()
    try:
        for sensor_key, cfg in sensors.items():
            pin = cfg.get("pin")
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except NameError:
        print("Skipping GPIO setup (mock environment).")

# Initialize pins on import
setup_water_level_pins()

def get_water_level_status():
    """
    Return a dict with each sensor's label, pin, and whether it's triggered.
    Example:
        {
          "sensor1": {
            "label": "Full",
            "pin": 22,
            "triggered": True
          },
          "sensor2": {
            "label": "3 Gal",
            "pin": 23,
            "triggered": False
          },
          "sensor3": {
            "label": "Empty",
            "pin": 24,
            "triggered": False
          }
        }
    """
    sensors = load_water_level_sensors()
    status = {}
    for sensor_key, cfg in sensors.items():
        label = cfg.get("label", sensor_key)
        pin = cfg.get("pin")
        try:
            # If RPi.GPIO is available, read the pin
            triggered = False
            if pin is not None:
                # Low means "not triggered", so we invert if you want True=active:
                # This depends on your actual float sensor hardware.
                sensor_state = GPIO.input(pin)
                triggered = (sensor_state == 0)  # or not sensor_state
        except NameError:
            # Mock for non-Pi
            triggered = (sensor_key == "sensor1")  # e.g., just pick one random True

        status[sensor_key] = {
            "label": label,
            "pin": pin,
            "triggered": triggered
        }

    return status
