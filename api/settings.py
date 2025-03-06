from flask import Blueprint, request, jsonify
import json
import os
import subprocess
from status_namespace import emit_status_update
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.plant_service import get_weeks_since_start
from datetime import datetime
from utils.settings_utils import load_settings, save_settings
from services.mdns_service import update_mdns_service

# Create the Blueprint for settings
settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# >>> Define your in-code program version here <<<
PROGRAM_VERSION = "1.0.11"

# Ensure the settings file exists with default values
if not os.path.exists(SETTINGS_FILE):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({
            "system_name": "Garden",
            "ph_range": {"min": 5.5, "max": 6.5},
            "ph_target": 5.8,
            "max_dosing_amount": 5,
            "dosing_interval": 1.0,
            "system_volume": 5.5,
            "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
            "auto_dosing_enabled": True,
            "time_zone": "America/New_York",
            "daylight_savings_enabled": True,
            # Add "ec_meter": None in usb_roles
            "usb_roles": {
                "ph_probe": None,
                "relay": None,
                "valve_relay": None,
                "ec_meter": None  # <--- NEW
            },
            "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
            "relay_ports": {"ph_up": 1, "ph_down": 2},
            "water_valve_ip": "",
            "water_fill_valve": "",
            "water_drain_valve": "",
            "valve_labels": {
                "1": "Valve #1",
                "2": "Valve #2",
                "3": "Valve #3",
                "4": "Valve #4",
                "5": "Valve #5",
                "6": "Valve #6",
                "7": "Valve #7",
                "8": "Valve #8"
            },
            "water_level_sensors": {
                "sensor1": {"label": "Full",  "pin": 17},
                "sensor2": {"label": "3 Gal", "pin": 18},
                "sensor3": {"label": "Empty", "pin": 19}
            },
            "plant_info": {},
            "additional_plants": []
        }, f, indent=4)


# API endpoint: Get all settings
@settings_blueprint.route('/', methods=['GET'])
def get_settings():
    settings = load_settings()
    # Inject our code-based version
    settings["program_version"] = PROGRAM_VERSION
    return jsonify(settings)


# API endpoint: Update settings
@settings_blueprint.route('/', methods=['POST'])
def update_settings():
    new_settings = request.get_json() or {}
    current_settings = load_settings()

    # Use Garden as fallback
    old_system_name = current_settings.get("system_name", "Garden")

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

    # Merge all remaining top-level keys (system_name, ph_range, ph_target, etc.)
    # This automatically merges any "additional_plants" array the front-end sends.
    current_settings.update(new_settings)

    # Save changes
    save_settings(current_settings)

    # If water-level pins changed, reinit them
    if water_sensors_updated:
        from services.water_level_service import force_cleanup_and_init
        force_cleanup_and_init()

    # If auto-dosing changed, reset timer
    if auto_dosing_changed:
        reset_auto_dose_timer()

    # Check if system_name changed; if so, re-register mDNS
    new_system_name = current_settings.get("system_name", "Garden")
    if new_system_name != old_system_name:
        update_mdns_service(system_name=new_system_name, port=8000)

    # Emit a status_update event to notify all clients
    emit_status_update()

    return jsonify({"status": "success", "settings": current_settings})


# API endpoint: Reset settings to defaults
@settings_blueprint.route('/reset', methods=['POST'])
def reset_settings():
    default_settings = {
        "system_name": "Garden",
        "ph_range": {"min": 5.5, "max": 6.5},
        "ph_target": 5.8,
        "max_dosing_amount": 5,
        "dosing_interval": 1.0,
        "system_volume": 5.5,
        "dosage_strength": {"ph_up": 1.3, "ph_down": 0.9},
        "auto_dosing_enabled": True,
        "time_zone": "America/New_York",
        "daylight_savings_enabled": True,
        "usb_roles": {
            "ph_probe": None,
            "relay": None,
            "valve_relay": None,
            "ec_meter": None
        },
        "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
        "relay_ports": {"ph_up": 1, "ph_down": 2},
        "fill_valve_ip": "",
        "fill_valve": "",
        "fill_sensor": "",
        "drain_valve_ip": "",
        "drain_valve": "",
        "drain_sensor": "",
        "valve_labels": {
            "1": "Valve #1",
            "2": "Valve #2",
            "3": "Valve #3",
            "4": "Valve #4",
            "5": "Valve #5",
            "6": "Valve #6",
            "7": "Valve #7",
            "8": "Valve #8"
        },
        "water_level_sensors": {
            "sensor1": {"label": "Full",  "pin": 17},
            "sensor2": {"label": "3 Gal", "pin": 18},
            "sensor3": {"label": "Empty", "pin": 19}
        },
        "plant_info": {},
        "additional_plants": []
    }
    save_settings(default_settings)

    # Emit a status_update event
    emit_status_update()

    return jsonify({"status": "success", "settings": default_settings})


# API endpoint: List USB devices
@settings_blueprint.route('/usb_devices', methods=['GET'])
def list_usb_devices():
    devices = []
    try:
        print("Executing command: ls /dev/serial/by-path")
        result = subprocess.check_output("ls /dev/serial/by-path", shell=True).decode().splitlines()
        devices = [{"device": f"/dev/serial/by-path/{dev}"} for dev in result]
        print("USB devices found:", devices)
    except subprocess.CalledProcessError as e:
        print(f"Error listing USB devices: {e}")
        devices = []
    except Exception as e:
        print(f"Unexpected error: {e}")
        devices = []

    # 1) Load settings
    settings = load_settings()

    # 2) Get the current usb_roles from settings
    usb_roles = settings.get("usb_roles", {})

    # 3) Figure out which paths are actually connected
    connected_paths = [dev["device"] for dev in devices]

    # 4) Only remove assignments that no longer match an existing path
    modified = False
    for role, assigned_device in list(usb_roles.items()):
        if assigned_device not in connected_paths and assigned_device is not None:
            usb_roles[role] = None
            modified = True

    # 5) If something changed, save the settings
    if modified:
        settings["usb_roles"] = usb_roles
        save_settings(settings)

    # 6) Emit a status update and return the devices list
    emit_status_update()
    return jsonify(devices)



@settings_blueprint.route('/assign_usb', methods=['POST'])
def assign_usb_device():
    from services.valve_relay_service import init_valve_thread, stop_valve_thread

    data = request.get_json()
    role = data.get("role")
    device = data.get("device")

    # Now we allow "ec_meter" as well
    if role not in ["ph_probe", "relay", "valve_relay", "ec_meter"]:
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    settings = load_settings()
    old_device = settings.get("usb_roles", {}).get(role)

    # If changing valve_relay, we stop the old thread
    if role == "valve_relay" and old_device != device:
        stop_valve_thread()

    # Assign or clear the role
    if not device:
        settings["usb_roles"][role] = None
    else:
        # Ensure no duplication
        for other_role, assigned_device in settings.get("usb_roles", {}).items():
            if assigned_device == device and other_role != role:
                return jsonify({
                    "status": "failure",
                    "error": f"Device already assigned to {other_role}"
                }), 400
        settings["usb_roles"][role] = device

    save_settings(settings)

    # Re-init logic if needed
    if role == "ph_probe":
        from services.ph_service import restart_serial_reader
        restart_serial_reader()
    elif role == "relay":
        from services.pump_relay_service import reinitialize_relay_service
        reinitialize_relay_service()
    elif role == "valve_relay" and device:
        init_valve_thread()

    # For ec_meter, we might not have extra logic yet, so do nothing special

    emit_status_update()
    return jsonify({"status": "success", "usb_roles": settings["usb_roles"]})


# API endpoint: Get System Name
@settings_blueprint.route('/system_name', methods=['GET'])
def get_system_name():
    settings = load_settings()
    return jsonify({"system_name": settings.get("system_name", "Garden")})


# API endpoint: Set System Name
@settings_blueprint.route('/system_name', methods=['POST'])
def set_system_name():
    data = request.get_json() or {}
    system_name = data.get("system_name")
    settings = load_settings()

    if system_name:
        settings["system_name"] = system_name
        save_settings(settings)
        # Re-register mDNS
        update_mdns_service(system_name=system_name, port=8000)
        # Emit a status_update event
        emit_status_update()

    return jsonify({"system_name": settings.get("system_name", "Garden")})
