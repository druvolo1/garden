from flask import Blueprint, request, jsonify
import json
import os
import subprocess
import stat
from status_namespace import emit_status_update
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.plant_service import get_weeks_since_start
from datetime import datetime
from utils.settings_utils import load_settings, save_settings
from services.mdns_service import register_mdns_pc_hostname
from services.mdns_service import register_mdns_pure_system_name

from flask import send_file

# Create the Blueprint for settings
settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# >>> Define your in-code program version here <<<
PROGRAM_VERSION = "1.0.47"

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
            "usb_roles": {
                "ph_probe": None,
                "relay": None,
                "valve_relay": None,
                "ec_meter": None
            },
            "pump_calibration": {"pump1": 0.5, "pump2": 0.5},
            "relay_ports": {"ph_up": 1, "ph_down": 2},

            # The local usb-based labels for a physically attached relay board
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

            # Water-level sensors
            "water_level_sensors": {
                "sensor1": {"label": "Full",  "pin": 17},
                "sensor2": {"label": "3 Gal", "pin": 18},
                "sensor3": {"label": "Empty", "pin": 19}
            },
            "plant_info": {},
            "additional_plants": [],

            # Let them store fill_valve_ip, fill_valve, fill_valve_label, etc.
            "fill_valve_ip": "",
            "fill_valve": "",
            "fill_valve_label": "",      # <--- newly introduced
            "drain_valve_ip": "",
            "drain_valve": "",
            "drain_valve_label": "",     # <--- newly introduced
            "fill_sensor": "",
            "drain_sensor": "",

            # For Shelly or other power outlets
            "power_controls": []
        }, f, indent=4)


@settings_blueprint.route('/', methods=['GET'])
def get_settings():
    settings = load_settings()
    # Inject our code-based version
    settings["program_version"] = PROGRAM_VERSION
    return jsonify(settings)


def ensure_script_executable(script_path: str):
    """Check if script is executable by the owner; if not, chmod +x."""
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    mode = os.stat(script_path).st_mode
    # Check if "owner execute" bit is set:
    if not (mode & stat.S_IXUSR):
        print(f"[INFO] Making {script_path} executable (chmod +x)")
        subprocess.run(["chmod", "+x", script_path], check=True)


@settings_blueprint.route('/', methods=['POST'])
def update_settings():
    """ Merge new settings into current_settings.json and emit a status update. """
    new_settings = request.get_json() or {}
    current_settings = load_settings()

    old_system_name = current_settings.get("system_name", "Garden")

    # Check if auto-dosing changed, so we can reset timers
    auto_dosing_changed = (
        "auto_dosing_enabled" in new_settings or
        "dosing_interval" in new_settings
    )

    # 1) Merge relay_ports if present
    if "relay_ports" in new_settings:
        if "relay_ports" not in current_settings:
            current_settings["relay_ports"] = {}
        current_settings["relay_ports"].update(new_settings["relay_ports"])
        del new_settings["relay_ports"]

    # 2) Merge water_level_sensors if present
    water_sensors_updated = False
    if "water_level_sensors" in new_settings:
        if "water_level_sensors" not in current_settings:
            current_settings["water_level_sensors"] = {}

        for sensor_key, sensor_data in new_settings["water_level_sensors"].items():
            current_settings["water_level_sensors"][sensor_key] = sensor_data

        del new_settings["water_level_sensors"]
        water_sensors_updated = True

    # 3) Merge power_controls if present
    if "power_controls" in new_settings:
        current_settings["power_controls"] = new_settings["power_controls"]
        del new_settings["power_controls"]

    # 4) Merge everything else (system_name, fill_valve, fill_valve_label, etc.)
    current_settings.update(new_settings)
    save_settings(current_settings)

    # If water-level pins changed, re-init them
    if water_sensors_updated:
        from services.water_level_service import force_cleanup_and_init
        force_cleanup_and_init()

    # If auto-dosing changed, reset the auto-dose timer
    if auto_dosing_changed:
        reset_auto_dose_timer()

    # If system_name changed, do your rename logic
    new_system_name = current_settings.get("system_name", "Garden")
    if new_system_name != old_system_name:
        print(f"System name changed from {old_system_name} to {new_system_name}.")

        appended_hostname = f"{new_system_name}-pc"

        script_path = os.path.join(os.getcwd(), "scripts", "change_hostname.sh")
        ensure_script_executable(script_path)

        try:
            subprocess.run(["sudo", script_path, appended_hostname], check=True)
            print(f"Successfully updated system hostname to {appended_hostname}.")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Unable to change system hostname: {e}")

        # Re-register mDNS for both appended and pure names
        try:
            register_mdns_pc_hostname(new_system_name, service_port=8000)
            print(f"[mDNS] Re-registered new system name: {appended_hostname}.local")
        except Exception as e:
            print(f"[mDNS] Error re-registering name: {e}")

        try:
            register_mdns_pure_system_name(new_system_name, service_port=8000)
            print(f"[mDNS] Also broadcasting pure name: {new_system_name}.local")
        except Exception as e:
            print(f"[mDNS] Error registering pure system name: {e}")

        emit_status_update()
        return jsonify({"status": "success", "settings": current_settings})

    # Otherwise, just emit status
    emit_status_update()
    return jsonify({"status": "success", "settings": current_settings})


@settings_blueprint.route('/reset', methods=['POST'])
def reset_settings():
    """Reset all settings to defaults, including fill_valve_label, etc."""
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

        # water valve assignment
        "fill_valve_ip": "",
        "fill_valve": "",
        "fill_valve_label": "",
        "fill_sensor": "",
        "drain_valve_ip": "",
        "drain_valve": "",
        "drain_valve_label": "",
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
        "additional_plants": [],
        "power_controls": []
    }
    save_settings(default_settings)

    emit_status_update()
    return jsonify({"status": "success", "settings": default_settings})


@settings_blueprint.route('/usb_devices', methods=['GET'])
def list_usb_devices():
    """List local USB devices, remove invalid assignments, emit status."""
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

    # If an assigned device is missing, clear it out
    settings = load_settings()
    usb_roles = settings.get("usb_roles", {})
    connected_paths = [d["device"] for d in devices]
    modified = False
    for role, assigned_device in list(usb_roles.items()):
        if assigned_device and assigned_device not in connected_paths:
            usb_roles[role] = None
            modified = True

    if modified:
        settings["usb_roles"] = usb_roles
        save_settings(settings)

    emit_status_update()
    return jsonify(devices)


@settings_blueprint.route('/assign_usb', methods=['POST'])
def assign_usb_device():
    """Assign or clear a USB device for pH probe, dosing relay, valve relay, or ec_meter."""
    from services.valve_relay_service import init_valve_thread, stop_valve_thread

    data = request.get_json()
    role = data.get("role")
    device = data.get("device")

    if role not in ["ph_probe", "relay", "valve_relay", "ec_meter"]:
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    settings = load_settings()
    old_device = settings.get("usb_roles", {}).get(role)

    # If switching valve_relay devices, stop old thread
    if role == "valve_relay" and old_device != device:
        stop_valve_thread()

    # Clear or set
    if not device:
        settings["usb_roles"][role] = None
    else:
        # Ensure no duplication
        for other_role, assigned_dev in settings["usb_roles"].items():
            if assigned_dev == device and other_role != role:
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
    # ec_meter has no special logic yet

    emit_status_update()
    return jsonify({"status": "success", "usb_roles": settings["usb_roles"]})


@settings_blueprint.route('/system_name', methods=['GET'])
def get_system_name():
    settings = load_settings()
    return jsonify({"system_name": settings.get("system_name", "Garden")})


@settings_blueprint.route('/system_name', methods=['POST'])
def set_system_name():
    data = request.get_json() or {}
    system_name = data.get("system_name")
    settings = load_settings()

    if system_name:
        settings["system_name"] = system_name
        save_settings(settings)
        emit_status_update()

    return jsonify({"system_name": settings.get("system_name", "Garden")})


@settings_blueprint.route('/export', methods=['GET'])
def export_settings():
    """Download the current settings.json file."""
    return send_file(
        SETTINGS_FILE,
        mimetype='application/json',
        as_attachment=True,
        download_name='settings.json'
    )


@settings_blueprint.route('/import', methods=['POST'])
def import_settings():
    """Upload a settings.json to replace existing, then re-init services."""
    if 'file' not in request.files:
        return jsonify({"status": "failure", "error": "No file part in request."}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "failure", "error": "No selected file."}), 400

    try:
        data = json.load(file)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)

        if "system_name" not in data:
            return jsonify({
                "status": "failure",
                "error": "Missing 'system_name' in imported settings."
            }), 400

        # Try re-init logic
        try:
            from services.ph_service import restart_serial_reader
            from services.pump_relay_service import reinitialize_relay_service
            from services.valve_relay_service import stop_valve_thread, init_valve_thread
            from services.auto_dose_utils import reset_auto_dose_timer

            restart_serial_reader()
            reinitialize_relay_service()
            stop_valve_thread()
            init_valve_thread()
            reset_auto_dose_timer()

            print("[IMPORT] Successfully re-initialized dependent services.")
        except Exception as ex:
            print(f"[IMPORT] Service re-init failed: {ex}")
            # Possibly restart the entire system:
            import subprocess
            try:
                subprocess.run(["sudo", "systemctl", "restart", "garden.service"], check=True)
                print("[IMPORT] Triggered service restart due to re-init failure.")
            except Exception as restart_err:
                print(f"[IMPORT] Could not restart garden.service: {restart_err}")

        emit_status_update()
        return jsonify({"status": "success"}), 200

    except json.JSONDecodeError:
        return jsonify({"status": "failure", "error": "Invalid JSON in uploaded file."}), 400
    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500
