import json
import os
import eventlet
from eventlet import semaphore

# Use eventlet semaphore for greenlet-safe locking
_settings_lock = semaphore.Semaphore()

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def load_settings():
    """
    Load settings from the settings file under a lock so there's no partial read
    if another thread/greenlet is writing at the same time.
    """
    with _settings_lock:
        if not os.path.exists(SETTINGS_FILE):
            # If the file doesn't exist, return an empty dict or set defaults
            return {}
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)

def save_settings(new_settings):
    """
    Save settings to the settings file under a lock so there's no partial write
    if another thread/greenlet is writing at the same time.
    """
    with _settings_lock:
        # Make sure directory exists, in case it was removed
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(new_settings, f, indent=4)