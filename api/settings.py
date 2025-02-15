from flask import Blueprint, request, jsonify
import json
import os
import subprocess
from flask_socketio import emit  # Import emit from flask_socketio
from services.auto_dose_state import auto_dose_state  # Import the shared dictionary
from services.auto_dose_utils import reset_auto_dose_timer
from services.plant_service import get_weeks_since_start
from datetime import datetime
from utils.settings_utils import load_settings, save_settings  # Import from utils

# Create the Blueprint for settings
settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# Ensure the settings file exists with default values
if not os.path.exists(SETTINGS_FILE):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "ph_range": {"min": 5.5, "max": 6.5},
            "max_dosing_amount": 5,
            "dosing_interval": 1.0,
            "system_volume": 5.5,
            "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
            "auto_dosing_enabled": True,
            "time_zone": "America/New_York",
            "daylight_savings_enabled": True,
            "usb_roles": {"ph_probe": None, "relay": None},
            "pump_calibration": {"pump1": 2.3, "pump2": 2.3},
            "ph_target": 5.8,
            "relay_ports": {"ph_up": 1, "ph_down": 2},
            "water_level_sensors": {
                "sensor1": {"label": "Full",  "pin": 22},
                "sensor2": {"label": "3 Gal", "pin": 23},
                "sensor3": {"label": "Empty", "pin": 24}
            }
        }, f, indent=4)

def emit_status_update():
    """
    Emit a status_update event with the latest settings and system status.
    """
    # Lazy import to avoid circular dependencies
    from services.ph_service import get_latest_ph_reading
    from services.water_level_service import get_water_level_status

    settings = load_settings()

    # Prepare the status update payload
    auto_dose_copy = dict(auto_dose_state)
    if isinstance(auto_dose_copy.get("last_dose_time"), datetime):
        auto_dose_copy["last_dose_time"] = auto_dose_copy["last_dose_time"].isoformat()
    if isinstance(auto_dose_copy.get("next_dose_time"), datetime):
        auto_dose_copy["next_dose_time"] = auto_dose_copy["next_dose_time"].isoformat()

    plant_info_raw = settings.get("plant_info", {})
    weeks = get_weeks_since_start(plant_info_raw)
    plant_info = {
        "name": plant_info_raw.get("name", ""),
        "start_date": plant_info_raw.get("start_date", ""),
        "weeks_since_start": weeks
    }

    water_level_info = get_water_level_status()

    status = {
        "settings": settings,
        "current_ph": get_latest_ph_reading(),
        "auto_dose_state": auto_dose_copy,
        "plant_info": plant_info,
        "water_level": water_level_info,
        "errors": []
    }

    # Emit the status_update event to all clients
    emit("status_update", status, namespace="/status")

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
    new_settings = request.get_json() or {}
    current_settings = load_settings()

    auto_dosing_changed = (
        "auto_dosing_enabled" in new_settings or
        "dosing_interval" in new_settings
    )

    # Merge relay_ports if present
    if "relay_ports" in new_settings:
        if "relay_ports" not in current_settings:
            current_settings["relay_ports"] = {}
        current_settings["relay_ports"].update(new_settings["relay_ports"])
        del new_settings["relay_ports"]

    # Merge water_level_sensors if present
    water_sensors_updated = False
    if "water_level_sensors" in new_settings:
        if "water_level_sensors" not in current_settings:
            current_settings["water_level_sensors"] = {}

        for sensor_key, sensor_data in new_settings["water_level_sensors"].items():
            current_settings["water_level_sensors"][sensor_key] = sensor_data

        del new_settings["water_level_sensors"]
        water_sensors_updated = True

    # Merge all remaining top-level keys (ph_range, ph_target, etc.)
    current_settings.update(new_settings)

    # Save the changes so that future load_settings() sees them
    save_settings(current_settings)

    # If water-level pins changed, reinit them
    if water_sensors_updated:
        from services.water_level_service import force_cleanup_and_init
        force_cleanup_and_init()

    # If auto-dosing changed, reset timer
    if auto_dosing_changed:
        reset_auto_dose_timer()

    # Emit a status_update event to notify all clients
    emit_status_update()

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
        "dosing_interval": 1.0,
        "system_volume": 5.5,
        "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
        "auto_dosing_enabled": True,
        "time_zone": "America/New_York",
        "daylight_savings_enabled": True,
        "usb_roles": {"ph_probe": None, "relay": None},
        "pump_calibration": {"pump1": 2.3, "pump2": 2.3},
        "ph_target": 5.8,
        "relay_ports": {"ph_up": 1, "ph_down": 2},
        "water_level_sensors": {
            "sensor1": {"label": "Full",  "pin": 22},
            "sensor2": {"label": "3 Gal", "pin": 23},
            "sensor3": {"label": "Empty", "pin": 24}
        }
    }
    save_settings(default_settings)

    # Emit a status_update event to notify all clients
    emit_status_update()

    return jsonify({"status": "success", "settings": default_settings})

# API endpoint: List USB devices
@settings_blueprint.route('/usb_devices', methods=['GET'])
def list_usb_devices():
    """
    List all USB devices connected to the Raspberry Pi, excluding disconnected devices.
    """
    devices = []
    try:
        result = subprocess.check_output("ls /dev/serial/by-id", shell=True).decode().splitlines()
        devices = [{"device": f"/dev/serial/by-id/{dev}"} for dev in result]
    except subprocess.CalledProcessError:
        devices = []

    settings = load_settings()
    usb_roles = settings.get("usb_roles", {})

    # Remove any device from usb_roles that is not currently connected
    for role, assigned_device in usb_roles.items():
        if assigned_device not in [dev["device"] for dev in devices]:
            usb_roles[role] = None

    settings["usb_roles"] = usb_roles
    save_settings(settings)

    # Emit a status_update event to notify all clients
    emit_status_update()

    return jsonify(devices)

# API endpoint: Assign a USB device to a specific role
@settings_blueprint.route('/assign_usb', methods=['POST'])
def assign_usb_device():
    """
    Assign a USB device to a specific role (e.g., ph_probe, relay).
    Expects JSON payload with `role` and `device`.
    """
    data = request.get_json()
    role = data.get("role")
    device = data.get("device")

    if role not in ["ph_probe", "relay"]:
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    settings = load_settings()
    if not device:
        # Clear the role
        settings["usb_roles"][role] = None
    else:
        # Ensure no duplication across roles
        for other_role, assigned_device in settings["usb_roles"].items():
            if assigned_device == device and other_role != role:
                return jsonify({"status": "failure", "error": f"Device already assigned to {other_role}"}), 400
        settings["usb_roles"][role] = device

    save_settings(settings)

    # Emit a status_update event to notify all clients
    emit_status_update()

    return jsonify({"status": "success", "usb_roles": settings["usb_roles"]})