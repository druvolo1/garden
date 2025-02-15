# File: utils/settings_utils.py

import json
import os

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def load_settings():
    """
    Load settings from the settings file.
    """
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings(new_settings):
    """
    Save settings to the settings file.
    """
    with open(SETTINGS_FILE, "w") as f:
        json.dump(new_settings, f, indent=4)