from flask import Blueprint, request, jsonify
import json
import os

# Create the Blueprint for settings
settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# Ensure the settings file exists
if not os.path.exists(SETTINGS_FILE):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "ph_range": {"min": 5.5, "max": 6.5},
            "max_dosing_amount": 5,
            "dosing_interval": 1,
            "system_volume": 50,
            "dosage_strength": {"ph_up": 10, "ph_down": 15},
            "auto_dosing_enabled": True,
            "time_zone": "America/New_York",
            "daylight_savings_enabled": True
        }, f, indent=4)


# Load the settings from the JSON file
def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


# Save updated settings to the JSON file
def save_settings(new_settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(new_settings, f, indent=4)


# API endpoint: Get all settings
@settings_blueprint.route('/', methods=['GET'])
def get_settings():
    """
    Get all system settings.
    """
    settings = load_settings()
    return jsonify(settings)


# API endpoint: Update settings
@settings_blueprint.route('/', methods=['POST'])
def update_settings():
    """
    Update system settings. Expects JSON payload with updated values.
    """
    new_settings = request.json
    current_settings = load_settings()

    # Update the settings with the new values
    current_settings.update(new_settings)
    save_settings(current_settings)

    return jsonify({"status": "success", "settings": current_settings})


# API endpoint: Reset settings to defaults
@settings_blueprint.route('/reset', methods=['POST'])
def reset_settings():
    """
    Reset settings to their default values.
    """
    default_settings = {
        "ph_range": {"min": 5.5, "max": 6.5},
        "max_dosing_amount": 5,
        "dosing_interval": 1,
        "system_volume": 50,
        "dosage_strength": {"ph_up": 10, "ph_down": 15},
        "auto_dosing_enabled": True,
        "time_zone": "America/New_York",
        "daylight_savings_enabled": True
    }
    save_settings(default_settings)
    return jsonify({"status": "success", "settings": default_settings})
