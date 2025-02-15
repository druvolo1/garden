#File: app.py

import socket
import eventlet
eventlet.monkey_patch()

import sys
import signal
from datetime import datetime, timedelta

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS

from api.ph import ph_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from api.dosing import dosing_blueprint

from status_namespace import StatusNamespace

from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.ph_service import get_latest_ph_reading, start_serial_reader, stop_serial_reader, latest_ph_value, serial_reader
from services.dosage_service import get_dosage_info, perform_auto_dose
from services.plant_service import get_weeks_since_start


app = Flask(__name__)
CORS(app)
socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*"
)

socketio.on_namespace(StatusNamespace('/status'))

def log_with_timestamp(msg):
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

def auto_dosing_loop():
    """
    Periodically checks settings to see if auto-dosing is enabled and if it's time to dose.
    If the dosing interval has changed, resets the timer.
    If auto-dosing is disabled, it resets the auto-dose state and waits.
    """
    from api.settings import load_settings

    log_with_timestamp("Inside auto dosing loop")
    while True:
        try:
            settings = load_settings()
            auto_enabled = settings.get("auto_dosing_enabled", False)
            interval_hours = float(settings.get("dosing_interval", 0))

            # If auto-dosing is disabled or the interval is invalid, reset and wait.
            if not auto_enabled or interval_hours <= 0:
                reset_auto_dose_timer()
                eventlet.sleep(5)
                continue

            now = datetime.now()

            # If the interval has changed, reset next_dose_time.
            if auto_dose_state.get("last_interval") != interval_hours:
                auto_dose_state["last_interval"] = interval_hours
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                log_with_timestamp(f"Interval changed; next dose time reset to {auto_dose_state['next_dose_time']}")

            # If next_dose_time is not set, initialize it.
            if not auto_dose_state.get("next_dose_time"):
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                log_with_timestamp(f"Next dose time initialized to {auto_dose_state['next_dose_time']}")

            # If it's time to dose, perform auto-dose.
            if now >= auto_dose_state["next_dose_time"]:
                dose_type, dose_amount = perform_auto_dose(settings)
                if dose_amount > 0:
                    auto_dose_state["last_dose_time"] = now
                    auto_dose_state["last_dose_type"] = dose_type
                    auto_dose_state["last_dose_amount"] = dose_amount
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                    log_with_timestamp(f"Auto-dose performed: {dose_type} {dose_amount} ml; next dose at {auto_dose_state['next_dose_time']}")
                else:
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                    log_with_timestamp(f"No dose performed; next dose rescheduled for {auto_dose_state['next_dose_time']}")

            eventlet.sleep(5)
        except Exception as e:
            log_with_timestamp(f"[AutoDosing] Error: {e}")
            eventlet.sleep(5)

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
    from api.settings import load_settings
    log_with_timestamp("Inside function for broadcasting status updates")
    while True:
        try:
            settings = load_settings()
            status = {
                "settings": settings,
                "current_ph": get_latest_ph_reading(),
                "auto_dose_state": auto_dose_state,
                "plant_weeks_since_start": 0,  # default
                "errors": []
            }

            # If we have plant_info in settings, compute weeks
            plant_info = settings.get("plant_info", {})
            weeks = get_weeks_since_start(plant_info)
            status["plant_weeks_since_start"] = weeks

            # Emit the status update on the '/status' namespace
            socketio.emit("status_update", status, namespace="/status")
            log_with_timestamp("[Status] Emitting status update")
            eventlet.sleep(5)
        except Exception as e:
            log_with_timestamp(f"[Status] Error broadcasting status update: {e}")
            eventlet.sleep(5)


def start_threads():
    # Spawn all background threads.
    log_with_timestamp("Spawning broadcast_ph_readings...")
    eventlet.spawn(broadcast_ph_readings)
    log_with_timestamp("Broadcast_ph_readings spawned.")

    log_with_timestamp("Spawning auto_dosing_loop...")
    eventlet.spawn(auto_dosing_loop)
    log_with_timestamp("Auto_dosing_loop spawned.")

    log_with_timestamp("Spawning serial reader...")
    eventlet.spawn(serial_reader)
    log_with_timestamp("Serial reader spawned.")

    log_with_timestamp("Spawning status broadcaster...")
    eventlet.spawn(broadcast_status)
    log_with_timestamp("Status broadcaster spawned.")

# ***** IMPORTANT: Start threads at module level so Gunicorn sees them *****
start_threads()

# Register our Blueprints
app.register_blueprint(ph_blueprint, url_prefix='/api/ph')
app.register_blueprint(relay_blueprint, url_prefix='/api/relay')
app.register_blueprint(water_level_blueprint, url_prefix='/api/water_level')
app.register_blueprint(settings_blueprint, url_prefix='/api/settings')
app.register_blueprint(log_blueprint, url_prefix='/api/logs')
app.register_blueprint(dosing_blueprint, url_prefix="/api/dosage")

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

@socketio.on('connect')
def handle_connect():
    log_with_timestamp("Client connected")
    current = get_latest_ph_reading()
    if current is not None:
        socketio.emit('ph_update', {'ph': current})

@app.route('/api/ph/latest', methods=['GET'])
def get_latest_ph():
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
    if auto_dose_state.get("next_dose_time"):
        dosage_data["next_dose_time"] = auto_dose_state["next_dose_time"].strftime("%Y-%m-%d %H:%M:%S")
    else:
        dosage_data["next_dose_time"] = "Not Scheduled"
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
    auto_dose_state["next_dose_time"] = None
    return jsonify({"status": "success", "message": f"Dispensed {amount} ml of pH {dispense_type}."})

@app.route('/api/device/config', methods=['GET', 'POST'])
def device_config():
    # Your existing code ...
    pass

if __name__ == "__main__":
    log_with_timestamp("[WSGI] Running in local development mode...")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)