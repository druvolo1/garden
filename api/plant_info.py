from flask import Blueprint, request, jsonify, render_template
from utils.settings_utils import load_settings, save_settings
from status_namespace import emit_status_update
from services.plant_service import get_weeks_since_start
from services.log_service import upload_pending_logs, upload_specific_log_file
import os

plant_info_blueprint = Blueprint('plant_info', __name__)

# Path to the settings file
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

@plant_info_blueprint.route('/', methods=['GET'])
def get_plant_info():
    settings = load_settings()
    plant_info = settings.get('plant_info', {})
    plant_info['weeks_since_start'] = get_weeks_since_start()
    return jsonify(plant_info)

@plant_info_blueprint.route('/', methods=['POST'])
def update_plant_info():
    new_settings = request.get_json() or {}
    current_settings = load_settings()

    # Merge plant_info if present
    if "plant_info" in new_settings:
        if "plant_info" not in current_settings:
            current_settings["plant_info"] = {}
        current_settings["plant_info"].update(new_settings["plant_info"])
        del new_settings["plant_info"]

    # Merge additional_plants if present
    if "additional_plants" in new_settings:
        current_settings["additional_plants"] = new_settings["additional_plants"]
        del new_settings["additional_plants"]

    # Merge general settings that were moved
    if "system_volume" in new_settings:
        current_settings["system_volume"] = new_settings["system_volume"]
    if "auto_dosing_enabled" in new_settings:
        current_settings["auto_dosing_enabled"] = new_settings["auto_dosing_enabled"]
    if "allow_remote_feeding" in new_settings:
        current_settings["allow_remote_feeding"] = new_settings["allow_remote_feeding"]

    save_settings(current_settings)
    emit_status_update()
    return jsonify({"status": "success", "settings": current_settings})

@plant_info_blueprint.route('/plant_info')
def plant_info_page():
    return render_template('plant_info.html')

@plant_info_blueprint.route('/upload_logs', methods=['POST'])
def upload_logs():
    """
    Trigger upload of pending logs to server.
    Called when finishing a plant.
    """
    try:
        success = upload_pending_logs()
        if success:
            return jsonify({"status": "success", "message": "Logs uploaded successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to upload logs"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@plant_info_blueprint.route('/upload_log/<filename>', methods=['POST'])
def upload_single_log(filename):
    """
    Upload a specific log file to the server.
    """
    try:
        import traceback
        success = upload_specific_log_file(filename)
        if success:
            return jsonify({"status": "success", "message": f"Log file {filename} uploaded successfully"})
        else:
            print(f"[ERROR] Failed to upload {filename}")
            return jsonify({"status": "error", "message": "Failed to upload log file"}), 500
    except Exception as e:
        print(f"[ERROR] Exception uploading {filename}: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)}), 500