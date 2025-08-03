###############################################################################
# app.py
###############################################################################
import socket
import eventlet
eventlet.monkey_patch()

import sys
import signal
from datetime import datetime, timedelta
import os
import subprocess

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

# Blueprints
from api.ph import ph_blueprint
from api.pump_relay import relay_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from api.dosing import dosing_blueprint
from api.update_code import update_code_blueprint
from api.debug import debug_blueprint
from api.notifications import notifications_blueprint

# Import the aggregator's set_socketio_instance + our /status namespace
from status_namespace import StatusNamespace, set_socketio_instance
from status_namespace import is_debug_enabled


# Services
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.ph_service import get_latest_ph_reading, serial_reader
from services.dosage_service import get_dosage_info, perform_auto_dose
from services.error_service import check_for_hardware_errors
from utils.settings_utils import load_settings

########################################################################
# 1) Create the global SocketIO instance
########################################################################
socketio = SocketIO(
    async_mode="eventlet",
    cors_allowed_origins="*"
)

def log_with_timestamp(msg):
    if is_debug_enabled("websocket"):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

########################################################################
# 2) Create the Flask app and init SocketIO
########################################################################
app = Flask(__name__)
CORS(app)

socketio.init_app(app, async_mode="eventlet", cors_allowed_origins="*")

# Let status_namespace.py have our main SocketIO reference
set_socketio_instance(socketio)

# Now register the /status namespace
socketio.on_namespace(StatusNamespace('/status'))

########################################################################
# 3) Background tasks
########################################################################
def broadcast_ph_readings():
    log_with_timestamp("Inside function for broadcasting pH readings")
    last_emitted_value = None
    while True:
        try:
            ph_value = get_latest_ph_reading()
            if ph_value is not None:
                ph_value = round(ph_value, 2)
                if ph_value != last_emitted_value:
                    last_emitted_value = ph_value
                    socketio.emit('ph_update', {'ph': ph_value})
                    log_with_timestamp(f"[Broadcast] Emitting pH update: {ph_value}")
            eventlet.sleep(1)
        except Exception as e:
            log_with_timestamp(f"[Broadcast] Error broadcasting pH value: {e}")



def broadcast_status():
    """
    Periodically call emit_status_update() from status_namespace.
    """
    from status_namespace import emit_status_update
    log_with_timestamp("Inside function for broadcasting status updates")
    while True:
        try:
            emit_status_update()
            eventlet.sleep(5)
        except Exception as e:
            log_with_timestamp(f"[broadcast_status] Error: {e}")
            eventlet.sleep(5)

def start_threads():
    settings = load_settings()

    # Broadcast latest pH to websockets
    log_with_timestamp("Spawning broadcast_ph_readings…")
    eventlet.spawn(broadcast_ph_readings)

    # Serial reader
    from services.ph_service import serial_reader
    log_with_timestamp("Spawning pH serial reader…")
    eventlet.spawn(serial_reader)

    # Status broadcaster
    log_with_timestamp("Spawning status broadcaster…")
    eventlet.spawn(broadcast_status)

    # Hardware error checker
    log_with_timestamp("Spawning hardware error checker…")
    eventlet.spawn(check_for_hardware_errors)

########################################################################
# Register Blueprints
########################################################################
app.register_blueprint(ph_blueprint, url_prefix='/api/ph')
app.register_blueprint(relay_blueprint, url_prefix='/api/relay')
app.register_blueprint(settings_blueprint, url_prefix='/api/settings')
app.register_blueprint(log_blueprint, url_prefix='/api/logs')
app.register_blueprint(dosing_blueprint, url_prefix="/api/dosage")
app.register_blueprint(update_code_blueprint, url_prefix='/api/system')
app.register_blueprint(debug_blueprint, url_prefix='/debug')
app.register_blueprint(notifications_blueprint, url_prefix='/api/notifications')


########################################################################
# Routes
########################################################################
@app.route('/')
def index():
    pi_ip = get_local_ip()
    return render_template('index.html', pi_ip=pi_ip)

@app.route('/settings')
def settings_page():
    pi_ip = get_local_ip()
    return render_template('settings.html', pi_ip=pi_ip)

@app.route('/calibration')
def calibration():
    return render_template('calibration.html')

@app.route('/configuration')
def configuration():
    return render_template('configuration.html')

@app.route('/valves')
def valves_page():
    return render_template('valves.html')

@socketio.on('connect')
def handle_connect():
    """ Basic connect handler for the default namespace. """
    log_with_timestamp("Client connected (default namespace)")
    ph_value = get_latest_ph_reading()
    if ph_value is not None:
        socketio.emit('ph_update', {'ph': ph_value})

@app.route('/api/ph/latest', methods=['GET'])
def get_ph_latest():
    ph_value = get_latest_ph_reading()
    if ph_value is not None:
        return jsonify({"status": "success", "ph": ph_value}), 200
    else:
        return jsonify({"status": "failure", "message": "No pH reading available."}), 404

@app.route('/dosage', methods=['GET'])
def dosage_page():
    from services.dosage_service import get_dosage_info
    dosage_data = get_dosage_info()

    if auto_dose_state.get("last_dose_time"):
        dosage_data["last_dose_time"] = auto_dose_state["last_dose_time"].strftime("%Y-%m-%d %H:%M:%S")
    else:
        dosage_data["last_dose_time"] = "Never"

    dosage_data["last_dose_type"] = auto_dose_state.get("last_dose_type") or "N/A"
    dosage_data["last_dose_amount"] = auto_dose_state.get("last_dose_amount")

    return render_template('dosage.html', dosage_data=dosage_data)

@app.route('/api/dosage/manual', methods=['POST'])
def api_manual_dosage():
    from datetime import datetime
    from services.dosage_service import manual_dispense
    data = request.get_json()
    dispense_type = data.get('type', 'none')
    amount = data.get('amount', 0.0)

    manual_dispense(dispense_type, amount)
    reset_auto_dose_timer()

    auto_dose_state["last_dose_time"] = datetime.now()
    auto_dose_state["last_dose_type"] = dispense_type
    auto_dose_state["last_dose_amount"] = amount

    return jsonify({"status": "success", "message": f"Dispensed {amount} ml of pH {dispense_type}."})

@app.route("/api/device/timezones", methods=["GET"])
def device_timezones():
    try:
        output = subprocess.check_output(["timedatectl", "list-timezones"]).decode().splitlines()
        all_timezones = sorted(output)
        return jsonify({"status": "success", "timezones": all_timezones}), 200
    except Exception as e:
        return jsonify({"status": "failure", "message": str(e)}), 500

@app.route('/notifications')
def notifications_page():
    return render_template('notifications.html')

@app.route('/logs')
def logs_page():
    return render_template('logs.html')

########################################################################
# MAIN
########################################################################
if __name__ == "__main__":
    log_with_timestamp("[WSGI] Running in local development mode...")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)