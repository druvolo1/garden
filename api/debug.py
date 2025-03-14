from flask import Blueprint, request, jsonify, render_template
import json

debug_blueprint = Blueprint("debug", __name__)

DEBUG_SETTINGS_FILE = os.path.join("config", "debug_settings.json")

def load_debug_settings():
    try:
        with open(DEBUG_SETTINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "status_namespace": False,
            "water_level_service": False,
            "power_control_service": False,
            "valve_relay_service": False
        }

def save_debug_settings(settings):
    with open(DEBUG_SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

@debug_blueprint.route("/status", methods=["GET"])
def get_debug_status():
    return jsonify(load_debug_settings())

@debug_blueprint.route("/toggle", methods=["POST"])
def toggle_debug():
    data = request.json
    component = data.get("component")
    new_state = data.get("enabled")

    settings = load_debug_settings()
    
    if component in settings:
        settings[component] = new_state
        save_debug_settings(settings)
        return jsonify({"message": f"Debug for {component} set to {new_state}"}), 200
    else:
        return jsonify({"error": "Invalid component"}), 400
    
@debug_blueprint.route("/")
def debug_page():
    return render_template("debug.html")
