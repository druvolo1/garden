from flask import Blueprint, request, jsonify, render_template
import json
import os

debug_blueprint = Blueprint("debug", __name__)

DEBUG_SETTINGS_FILE = os.path.join(os.getcwd(), "data", "debug_settings.json")

def load_debug_settings():
    defaults = {
        "websocket": False,
        "water_level_service": False,
        "power_control_service": False,
        "valve_relay_service": False,
        "notifications": False,
        "ph": False,
        "status_namespace": False
    }

    try:
        with open(DEBUG_SETTINGS_FILE, "r") as f:
            loaded = json.load(f)
            # Merge defaults with loaded settings (loaded settings take precedence)
            merged = defaults.copy()
            merged.update(loaded)

            # Save back if we added new defaults
            if set(merged.keys()) != set(loaded.keys()):
                save_debug_settings(merged)

            return merged
    except FileNotFoundError:
        # Create the file with defaults
        save_debug_settings(defaults)
        return defaults

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

    # Allow new components to be added dynamically
    settings[component] = new_state
    save_debug_settings(settings)
    return jsonify({"message": f"Debug for {component} set to {new_state}"}), 200
    
@debug_blueprint.route("/")
def debug_page():
    return render_template("debug.html")
