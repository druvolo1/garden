import socket
import eventlet
eventlet.monkey_patch()

import sys
import atexit
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

from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.ph_service import get_latest_ph_reading, start_serial_reader, stop_serial_reader, latest_ph_value
from services.dosage_service import get_dosage_info, perform_auto_dose

# We'll use an Event from eventlet instead of threading
stop_event = eventlet.event.Event()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, async_mode="eventlet")

cleanup_called = False

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
    Periodically checks if auto-dosing is enabled and if it's time to dose.
    Respects dosing_interval from settings, and last dosing time.
    """
    from api.settings import load_settings

    print("Inside auto dosing loop")

    while not stop_event.is_set():
        try:
            settings = load_settings()
            auto_enabled = settings.get("auto_dosing_enabled", False)
            interval_hours = float(settings.get("dosing_interval", 0))

            # If auto-dosing is disabled, reset and wait
            if not auto_enabled:
                reset_auto_dose_timer()
                eventlet.sleep(5)
                continue

            # If interval is invalid, reset and wait
            if interval_hours <= 0:
                reset_auto_dose_timer()
                eventlet.sleep(5)
                continue

            now = datetime.now()

            # If the interval changed, reset next_dose_time
            if auto_dose_state.get("last_interval") != interval_hours:
                auto_dose_state["last_interval"] = interval_hours
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)

            # If next_dose_time not set, set it
            if not auto_dose_state["next_dose_time"]:
                auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)

            # If it's time to dose
            if now >= auto_dose_state["next_dose_time"]:
                dose_type, dose_amount = perform_auto_dose(settings)
                if dose_amount > 0:
                    auto_dose_state["last_dose_time"] = now
                    auto_dose_state["last_dose_type"] = dose_type
                    auto_dose_state["last_dose_amount"] = dose_amount
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                else:
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)

            eventlet.sleep(5)

        except Exception as e:
            log_with_timestamp(f"[AutoDosing] Error: {e}")
            eventlet.sleep(5)

def broadcast_ph_readings():
    print("Inside function for broadcasting ph readings")
    last_emitted_value = None
    while not stop_event.is_set():
        try:
            ph_value = get_latest_ph_reading()
            if ph_value is not None:
                ph_value = round(ph_value, 2)
                if ph_value != last_emitted_value:
                    last_emitted_value = ph_value
                    socketio.emit('ph_update', {'ph': ph_value})
                    print(f"[Broadcast] Emitting pH update: {ph_value}")
            eventlet.sleep(1)
        except Exception as e:
            print(f"[Broadcast] Error broadcasting pH value: {e}")

def start_threads():
    eventlet.sleep(0.1)
    #log_with_timestamp("Starting background threads...")
    #if stop_event.ready():
    #    stop_event.reset()
    #log_with_timestamp("Spawning broadcast_ph_readings...")
    #eventlet.spawn(broadcast_ph_readings)
    #log_with_timestamp("Spawning auto_dosing_loop...")
    #eventlet.spawn(auto_dosing_loop)
    log_with_timestamp("Starting serial reader...")
    eventlet.spawn(serial_reader)
    #start_serial_reader()  # from ph_service.py
    #log_with_timestamp("Serial reader spawn requested.")

def stop_threads():
    print("Stopping background threads...")
    stop_event.send()
    stop_serial_reader()
    print("Background threads stopped.")

def cleanup():
    global cleanup_called
    if cleanup_called:
        return
    cleanup_called = True
    print("Cleaning up resources...")
    stop_threads()
    print("Background threads stopped.")

def do_cleanup():
    # Called from a signal handler in a separate green thread
    log_with_timestamp("Cleaning up resources via do_cleanup() ...")
    try:
        stop_threads()
    except Exception as e:
        log_with_timestamp(f"Error during stop_threads: {e}")
    log_with_timestamp("Background threads stopped.")
    sys.exit()

def graceful_exit(signum, frame):
    log_with_timestamp(f"Received signal {signum}. Scheduling cleanup...")
    eventlet.spawn_n(do_cleanup)

def handle_stop_signal(signum, frame):
    log_with_timestamp(f"Received signal {signum} (SIGTSTP). Scheduling cleanup...")
    eventlet.spawn_n(do_cleanup)

#signal.signal(signal.SIGINT, graceful_exit)
#signal.signal(signal.SIGTERM, graceful_exit)
#signal.signal(signal.SIGTSTP, handle_stop_signal)
atexit.register(cleanup)

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
    print("Client connected")
    if latest_ph_value is not None:
        socketio.emit('ph_update', {'ph': latest_ph_value})

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
    if auto_dose_state["last_dose_time"]:
        dosage_data["last_dose_time"] = auto_dose_state["last_dose_time"].strftime("%Y-%m-%d %H:%M:%S")
    else:
        dosage_data["last_dose_time"] = "Never"
    dosage_data["last_dose_type"] = auto_dose_state["last_dose_type"] or "N/A"
    dosage_data["last_dose_amount"] = auto_dose_state["last_dose_amount"]
    if auto_dose_state["next_dose_time"]:
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
    print("[WSGI] Running in local development mode...")
    start_threads()
    # Use socketio.run if you rely on real-time websockets
    socketio.run(app, host="0.0.0.0", port=8000, debug=True)
