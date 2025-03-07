# File: app.py

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

# Import your other blueprints
from api.ph import ph_blueprint
from api.pump_relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from api.dosing import dosing_blueprint
from api.valve_relay import valve_relay_blueprint
from api.update_code import update_code_blueprint

from status_namespace import StatusNamespace, emit_status_update

from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.ph_service import (
    get_latest_ph_reading, start_serial_reader, stop_serial_reader,
    latest_ph_value, serial_reader
)
from services.dosage_service import get_dosage_info, perform_auto_dose
from services.plant_service import get_weeks_since_start
from services.error_service import check_for_hardware_errors
from services.device_config import (
    get_hostname, get_ip_config, get_timezone, is_daylight_savings,
    get_ntp_server, get_wifi_config, set_hostname, set_ip_config,
    set_timezone, set_ntp_server, set_wifi_config
)

from services.water_level_service import get_water_level_status, monitor_water_level_sensors
from services.mdns_service import update_mdns_service
from utils.settings_utils import load_settings
from services.power_control_service import start_power_control_loop

from api.ec import ec_blueprint

# Create a SocketIO instance first
socketio = SocketIO(async_mode="eventlet")

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

#################
# CREATE FLASK APP
#################
app = Flask(__name__)
CORS(app)

# Now initialize SocketIO with the Flask app
socketio.init_app(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*"
)

# Register your Socket.IO namespace
socketio.on_namespace(StatusNamespace('/status'))

#################
# BACKGROUND TASKS
#################
def auto_dosing_loop():
    from api.settings import load_settings
    log_with_timestamp("Inside auto dosing loop")
    while True:
        try:
            settings = load_settings()
            auto_enabled = settings.get("auto_dosing_enabled", False)
            interval_hours = float(settings.get("dosing_interval", 0))

            if not auto_enabled or interval_hours <= 0:
                reset_auto_dose_timer()
                eventlet.sleep(5)
                continue

            now = datetime.now()

            if auto_dose_state.get("last_interval") != interval_hours:
                auto_dose_state["last_interval"] = interval_hours
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                log_with_timestamp(
                    f"Interval changed; next dose time reset to {auto_dose_state['next_dose_time']}"
                )

            if not auto_dose_state.get("next_dose_time"):
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                log_with_timestamp(f"Next dose time initialized to {auto_dose_state['next_dose_time']}")

            if now >= auto_dose_state["next_dose_time"]:
                dose_type, dose_amount = perform_auto_dose(settings)
                if dose_amount > 0:
                    auto_dose_state["last_dose_time"] = now
                    auto_dose_state["last_dose_type"] = dose_type
                    auto_dose_state["last_dose_amount"] = dose_amount
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                    log_with_timestamp(
                        f"Auto-dose performed: {dose_type} {dose_amount} ml; "
                        f"next dose at {auto_dose_state['next_dose_time']}"
                    )
                else:
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                    log_with_timestamp(
                        f"No dose performed; next dose rescheduled for {auto_dose_state['next_dose_time']}"
                    )

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

def broadcast_ec_readings():
    log_with_timestamp("Inside function for broadcasting EC readings")
    last_emitted_value = None
    while True:
        try:
            from services.ec_service import get_latest_ec_reading
            ec_value = get_latest_ec_reading()
            if ec_value is not None:
                if ec_value != last_emitted_value:
                    last_emitted_value = ec_value
                    socketio.emit('ec_update', {'ec': ec_value})
                    log_with_timestamp(f"[EC Broadcast] Emitting EC update: {ec_value}")
            eventlet.sleep(1)
        except Exception as e:
            log_with_timestamp(f"[EC Broadcast] Error: {e}")
            eventlet.sleep(5)

def broadcast_status():
    log_with_timestamp("Inside function for broadcasting status updates")
    while True:
        try:
            emit_status_update()
            eventlet.sleep(5)
        except Exception as e:
            log_with_timestamp(f"[broadcast_status] Error: {e}")
            eventlet.sleep(5)

#################
# START THREADS
#################
def start_threads():
    settings = load_settings()
    system_name = settings.get("system_name", "Zone 1")

    update_mdns_service(system_name=system_name, port=8000)
    log_with_timestamp(f"mDNS service registered from start_threads()! (system_name={system_name})")

    # pH broadcast
    log_with_timestamp("Spawning broadcast_ph_readings...")
    eventlet.spawn(broadcast_ph_readings)

    # EC broadcast
    log_with_timestamp("Spawning broadcast_ec_readings...")
    eventlet.spawn(broadcast_ec_readings)

    # Actually start the EC serial reader
    from services.ec_service import start_ec_serial_reader
    log_with_timestamp("Spawning ec_serial_reader...")
    eventlet.spawn(start_ec_serial_reader)

    # Auto-dosing
    log_with_timestamp("Spawning auto_dosing_loop...")
    eventlet.spawn(auto_dosing_loop)

    # pH serial
    log_with_timestamp("Spawning pH serial reader...")
    eventlet.spawn(serial_reader)

    # Status, hardware checker, water level, etc.
    log_with_timestamp("Spawning status broadcaster...")
    eventlet.spawn(broadcast_status)

    log_with_timestamp("Spawning hardware error checker...")
    eventlet.spawn(check_for_hardware_errors)

    log_with_timestamp("Spawning water level sensor monitor...")
    eventlet.spawn(monitor_water_level_sensors)

    # Valve thread
    from services.valve_relay_service import init_valve_thread
    init_valve_thread()

    log_with_timestamp("Spawning water power control monitor...")
    start_power_control_loop()  # to spin up the power control logic

# Kick off your background threads so Gunicorn sees them:
start_threads()

#################
# REGISTER BLUEPRINTS
#################
app.register_blueprint(ph_blueprint, url_prefix='/api/ph')
app.register_blueprint(relay_blueprint, url_prefix='/api/relay')
app.register_blueprint(water_level_blueprint, url_prefix='/api/water_level')
app.register_blueprint(settings_blueprint, url_prefix='/api/settings')
app.register_blueprint(log_blueprint, url_prefix='/api/logs')
app.register_blueprint(dosing_blueprint, url_prefix="/api/dosage")
app.register_blueprint(valve_relay_blueprint, url_prefix='/api/valve_relay')
app.register_blueprint(ec_blueprint, url_prefix='/api/ec')
app.register_blueprint(update_code_blueprint, url_prefix='/api/system')


#################
# ROUTES
#################
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
    log_with_timestamp("Client connected")
    current_ph = get_latest_ph_reading()
    if current_ph is not None:
        socketio.emit('ph_update', {'ph': current_ph})

@app.route('/api/ph/latest', methods=['GET'])
def get_ph_latest():
    ph_value = get_latest_ph_reading()
    if ph_value is not None:
        return jsonify({"status": "success", "ph": ph_value}), 200
    else:
        return jsonify({"status": "failure", "message": "No pH reading available."}), 404

@app.route('/dosage', methods=['GET'])
def dosage_page():
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

@app.route("/api/device/timezones", methods=["GET"])
def device_timezones():
    try:
        output = subprocess.check_output(["timedatectl", "list-timezones"]).decode().splitlines()
        all_timezones = sorted(output)
        return jsonify({"status": "success", "timezones": all_timezones}), 200
    except Exception as e:
        return jsonify({"status": "failure", "message": str(e)}), 500

#################
# MAIN
#################
if __name__ == "__main__":
    log_with_timestamp("[WSGI] Running in local development mode...")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)
