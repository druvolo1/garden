from flask import Blueprint, request, jsonify, render_template, send_file
import json
import os
import subprocess
import stat
from datetime import datetime
import threading

from status_namespace import emit_status_update
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.plant_service import get_weeks_since_start
from utils.settings_utils import load_settings, save_settings

import requests  # For sending the Discord test POST

settings_blueprint = Blueprint('settings', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

# >>> Define your in-code program version here <<<
CURRENT_VERSION = "v1.0.87"

feeding_in_progress = False
feeding_timer = None

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
            "auto_dosing_enabled": False,
            "time_zone": "America/New_York",
            "daylight_savings_enabled": True,
            "usb_roles": {
                "ph_probe": None,
                "relay": None,
                "valve_relay": None,
                "ec_meter": None
            },
            "pump_calibration": {"pump1": 0.5, "pump2": 0.5, "pump1_last_calibrated": "", "pump2_last_calibrated": "",
                                 "pump1_activations": 0, "pump1_cumulative_duration": 0.0,
                                 "pump2_activations": 0, "pump2_cumulative_duration": 0.0},
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
            "fill_valve_label": "",
            "drain_valve_ip": "",
            "drain_valve": "",
            "drain_valve_label": "",
            "fill_sensor": "",
            "drain_sensor": "",

            # For Shelly or other power outlets
            "power_controls": [],

            # NEW: Default Discord notification settings
            "discord_enabled": False,
            "discord_webhook_url": "",

            "telegram_enabled": False,
            "telegram_bot_token": "",
            "telegram_chat_id": "",

            "allow_remote_feeding": False,
            "auto_fill_sensor": "disabled"
        }, f, indent=4)

@settings_blueprint.route('/check_update', methods=['GET'])
def check_update():
    try:
        project_root = os.getcwd()
        # Git fetch to update remote refs
        fetch_proc = subprocess.run(['git', 'fetch'], cwd=project_root, capture_output=True, text=True, timeout=30)
        if fetch_proc.returncode != 0:
            return jsonify({"status": "failure", "error": "Failed to fetch updates"}), 500

        # Check status
        status_proc = subprocess.run(['git', 'status', '-uno'], cwd=project_root, capture_output=True, text=True, timeout=30)
        git_status = status_proc.stdout.strip()
        if 'Your branch is behind' in git_status:
            return jsonify({"status": "success", "update_available": True, "message": "Update available"})
        else:
            return jsonify({"status": "success", "update_available": False, "message": "No update available"})
    except subprocess.TimeoutExpired:
        return jsonify({"status": "failure", "error": "Check timed out"}), 500
    except Exception as e:
        return jsonify({"status": "failure", "error": f"Unexpected error: {str(e)}"}), 500

@settings_blueprint.route('/apply_update', methods=['POST'])
def apply_update():
    try:
        project_root = os.getcwd()
        venv_pip = os.path.join(project_root, 'venv', 'bin', 'pip')
        requirements_file = os.path.join(project_root, 'requirements.txt')

        # Git pull
        git_proc = subprocess.run(['git', 'pull'], cwd=project_root, capture_output=True, text=True, timeout=60)
        if git_proc.returncode != 0:
            return jsonify({"status": "failure", "error": "Failed to apply updates"}), 500

        # Pip install if requirements exist
        if os.path.exists(requirements_file):
            pip_proc = subprocess.run([venv_pip, 'install', '-r', requirements_file],
                                      cwd=project_root, capture_output=True, text=True, timeout=120)
            if pip_proc.returncode != 0:
                return jsonify({"status": "failure", "error": "Failed to install dependencies"}), 500

        # Restart the service
        subprocess.Popen(['sudo', 'systemctl', 'restart', 'garden.service'],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=project_root)

        return jsonify({"status": "success", "message": "Update complete"})
    except subprocess.TimeoutExpired:
        return jsonify({"status": "failure", "error": "Update timed out"}), 500
    except Exception as e:
        return jsonify({"status": "failure", "error": f"Unexpected error: {str(e)}"}), 500

@settings_blueprint.route('/update', methods=['POST'])
def update_application():
    # Deprecated: Redirect to new endpoints
    return jsonify({"status": "failure", "error": "Use /check_update and /apply_update instead"}), 410


@settings_blueprint.route('/', methods=['GET'])
def get_settings():
    settings = load_settings()
    # Inject our code-based version
    settings['current_version'] = CURRENT_VERSION
    settings["feeding_in_progress"] = feeding_in_progress
    settings.setdefault('pump_calibration', {
        "pump1": 0.5,
        "pump2": 0.5,
        "pump1_last_calibrated": "",
        "pump2_last_calibrated": "",
        "pump1_activations": 0,
        "pump1_cumulative_duration": 0.0,
        "pump2_activations": 0,
        "pump2_cumulative_duration": 0.0
    })
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
    """
    Merge new settings into current_settings.json and emit a status update.
    This can handle many fields including the new Discord fields:
      "discord_enabled", "discord_webhook_url".
    """
    new_settings = request.get_json() or {}
    print(f"[DEBUG] update_settings received new_settings = {new_settings}")

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

    # Merge pump_calibration if present
    if "pump_calibration" in new_settings:
        if "pump_calibration" not in current_settings:
            current_settings["pump_calibration"] = {}
        current_settings["pump_calibration"].update(new_settings["pump_calibration"])
        del new_settings["pump_calibration"]

    # 4) Merge everything else (system_name, fill_valve, fill_valve_label, etc.)
    #    This includes our new Discord fields if present: "discord_enabled", "discord_webhook_url"
    current_settings.update(new_settings)
    save_settings(current_settings)

    # If water-level pins changed, re-init them
    if water_sensors_updated:
        from utils.water_level_utils import force_cleanup_and_init
        force_cleanup_and_init()

    # If auto-dosing changed, reset timer
    if auto_dosing_changed:
        reset_auto_dose_timer()

    # If system name changed, re-register mDNS
    new_system_name = current_settings.get("system_name", "Garden")
    if old_system_name != new_system_name:
        from utils.mdns_utils import register_mdns_pc_hostname, register_mdns_pure_system_name
        register_mdns_pc_hostname(new_system_name, service_port=8000)
        register_mdns_pure_system_name(new_system_name, service_port=8000)

    try:
        from services.log_service import reset_cache
        reset_cache()
        print("[DEBUG] Log service cache reset after settings update.")
    except ImportError:
        print("[WARN] Could not import log_service to reset cache.")

    emit_status_update()
    return jsonify({"status": "success", "settings": current_settings})

@settings_blueprint.route('/remove_plant', methods=['POST'])
def remove_plant():
    data = request.get_json() or {}
    index = data.get('index')
    if index is None:
        return jsonify({"status": "failure", "error": "No index provided"}), 400

    current_settings = load_settings()
    if 'additional_plants' in current_settings and 0 <= index < len(current_settings['additional_plants']):
        del current_settings['additional_plants'][index]
        save_settings(current_settings)
        return jsonify({"status": "success", "settings": current_settings})
    else:
        return jsonify({"status": "failure", "error": "Invalid index"}), 400

@settings_blueprint.route('/add_plant', methods=['POST'])
def add_plant():
    data = request.get_json() or {}
    new_ip = data.get('new_ip')
    if not new_ip:
        return jsonify({"status": "failure", "error": "No new_ip provided"}), 400

    current_settings = load_settings()
    if 'additional_plants' not in current_settings:
        current_settings['additional_plants'] = []
    if new_ip in current_settings['additional_plants']:
        return jsonify({"status": "failure", "error": "Plant already exists"}), 400
    current_settings['additional_plants'].append(new_ip)
    save_settings(current_settings)
    return jsonify({"status": "success", "settings": current_settings})

@settings_blueprint.route('/usb_devices', methods=['GET'])
def list_usb_devices():
    import subprocess
    devices = []
    try:
        result = subprocess.check_output("ls /dev/serial/by-path", shell=True).decode().splitlines()
        devices = [{"device": f"/dev/serial/by-path/{dev}"} for dev in result]
    except Exception as e:
        print(f"Error listing USB devices: {e}")
    return jsonify(devices)

@settings_blueprint.route('/assign_usb', methods=['POST'])
def assign_usb_device():
    data = request.get_json() or {}
    role = data.get("role")
    device = data.get("device")

    if role not in ["ph_probe", "relay", "valve_relay", "ec_meter"]:
        return jsonify({"status": "failure", "error": "Invalid role"}), 400

    current_settings = load_settings()
    current_settings.setdefault("usb_roles", {})[role] = device  # Safely create dict if missing
    save_settings(current_settings)

    # Reinitialize the valve relay service if device changed
    reinitialize_relay_service()

    emit_status_update()
    return jsonify({"status": "success", "usb_roles": current_settings["usb_roles"]})

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

        # Add this: Invalidate log cache after successful save
        try:
            from services.log_service import reset_cache
            reset_cache()
            print("[DEBUG] Log service cache reset after settings import.")
        except ImportError:
            print("[WARN] Could not import log_service to reset cache.")

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

@settings_blueprint.route('/discord_message', methods=['POST'])
def discord_webhook():
    """
    POST JSON like:
    {
      "test_message": "Hello from my garden!"
    }
    We'll retrieve settings.discord_webhook_url and settings.discord_enabled,
    then attempt to POST to Discord.
    """
    data = request.get_json() or {}
    test_message = data.get("test_message", "").strip()
    if not test_message:
        return jsonify({"status": "failure", "error": "No test_message provided"}), 400

    settings = load_settings()
    if not settings.get("discord_enabled", False):
        return jsonify({"status": "failure", "error": "Discord notifications are disabled"}), 400

    webhook_url = settings.get("discord_webhook_url", "").strip()
    if not webhook_url:
        return jsonify({"status": "failure", "error": "No Discord webhook URL is configured"}), 400

    # Attempt to send
    try:
        resp = requests.post(webhook_url, json={"content": test_message}, timeout=10)
        if 200 <= resp.status_code < 300:
            return jsonify({"status": "success", "info": f"Message delivered (HTTP {resp.status_code})."})
        else:
            return jsonify({
                "status": "failure",
                "error": f"Discord webhook returned {resp.status_code} {resp.text}"
            }), 400
    except Exception as ex:
        return jsonify({"status": "failure", "error": f"Exception sending webhook: {ex}"}), 400

@settings_blueprint.route('/telegram_message', methods=['POST'])
def telegram_webhook():
    """
    POST JSON like:
    {
      "test_message": "Hello from my garden!"
    }
    We'll retrieve settings.telegram_bot_token and settings.telegram_enabled,
    then attempt to POST to Telegram's Bot API using raw HTTP.
    """
    data = request.get_json() or {}
    test_message = data.get("test_message", "").strip()
    if not test_message:
        return jsonify({"status": "failure", "error": "No test_message provided"}), 400

    settings = load_settings()
    if not settings.get("telegram_enabled", False):
        return jsonify({"status": "failure", "error": "Telegram notifications are disabled"}), 400

    bot_token = settings.get("telegram_bot_token", "").strip()
    if not bot_token:
        return jsonify({"status": "failure", "error": "No Telegram bot token is configured"}), 400

    # For a real integration, you also need a chat_id or channel username.
    # For testing, either store "telegram_chat_id" in settings or accept in request.
    # Example: let's just assume we store it in the settings:
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not chat_id:
        return jsonify({"status": "failure", "error": "No Telegram chat_id is configured"}), 400

    # Attempt to send a message via raw POST
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": test_message
        }
        resp = requests.post(url, json=payload, timeout=10)
        if 200 <= resp.status_code < 300:
            return jsonify({"status": "success", "info": f"Message delivered (HTTP {resp.status_code})."})
        else:
            return jsonify({
                "status": "failure",
                "error": f"Telegram API returned {resp.status_code} {resp.text}"
            }), 400
    except Exception as ex:
        return jsonify({"status": "failure", "error": f"Exception sending Telegram message: {ex}"}), 400

def reset_feeding_status():
    global feeding_in_progress, feeding_timer
    feeding_in_progress = False
    feeding_timer = None
    emit_status_update()

@settings_blueprint.route('/feeding_status', methods=['POST'])
def update_feeding_status():
    """
    Update the feeding_in_progress variable.
    POST JSON like:
    {
      "in_progress": true
    }
    """
    global feeding_in_progress, feeding_timer
    data = request.get_json() or {}
    in_progress = data.get("in_progress")
    if not isinstance(in_progress, bool):
        return jsonify({"status": "failure", "error": "Invalid or missing 'in_progress' boolean."}), 400

    if in_progress:
        if feeding_timer:
            feeding_timer.cancel()
        feeding_timer = threading.Timer(7200, reset_feeding_status)  # 2 hours = 7200 seconds
        feeding_timer.start()
        feeding_in_progress = True
    else:
        if feeding_timer:
            feeding_timer.cancel()
            feeding_timer = None
        feeding_in_progress = False

    emit_status_update()
    return jsonify({"status": "success", "feeding_in_progress": feeding_in_progress})

@settings_blueprint.route('/settings')
def settings_page():
    return render_template('settings.html')