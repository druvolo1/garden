import socket
import time
import threading
import atexit
import json
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from api.ph import ph_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from api.dosing import dosing_blueprint  # Our updated dosing blueprint
from services.ph_service import get_latest_ph_reading, start_serial_reader, stop_serial_reader, latest_ph_value
from services.dosage_service import get_dosage_info, perform_auto_dose 
from services.device_config import (
    get_hostname, set_hostname, get_ip_config, set_ip_config, get_timezone, set_timezone,
    is_daylight_savings, get_ntp_server, set_ntp_server, get_wifi_config, set_wifi_config
)
from datetime import datetime, timedelta

app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")  # or "gevent" if you prefer
stop_event = threading.Event()  # Event to stop background threads
cleanup_called = False
serial_reader_thread = None

def log_with_timestamp(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

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

# -------------------------------
# AUTO-DOSING STATE & BACKGROUND
# -------------------------------
auto_dose_state = {
    "last_dose_time": None,
    "last_dose_type": None,
    "last_dose_amount": 0.0,
    "next_dose_time": None
}

def reset_auto_dose_timer():
    """
    Called whenever we dose (manually or automatically) so we start counting
    a new interval until the next auto dose.
    """
    global auto_dose_state
    now = datetime.now()
    auto_dose_state["last_dose_time"] = now
    auto_dose_state["last_dose_type"] = None  # We'll set this after we know up/down
    auto_dose_state["last_dose_amount"] = 0.0
    auto_dose_state["next_dose_time"] = None

def auto_dosing_loop():
    """
    Periodically checks if auto-dosing is enabled and if it's time to dose.
    Respects dosing_interval from settings, and last dosing time.
    """
    from services.dosing_logic import perform_auto_dose  # We'll define in a separate file or inline

    while not stop_event.is_set():
        try:
            # Load settings each loop to see if user changed auto_dosing or dosing_interval
            from api.settings import load_settings
            settings = load_settings()
            auto_enabled = settings.get("auto_dosing_enabled", False)
            interval_hours = float(settings.get("dosing_interval", 0))
            
            if not auto_enabled or interval_hours <= 0:
                # If disabled or invalid interval, just reset timer & skip
                time.sleep(5)
                continue

            now = datetime.now()
            # If we haven't dosed yet or next_dose_time is not set, set next_dose_time
            if not auto_dose_state["next_dose_time"]:
                if auto_dose_state["last_dose_time"]:
                    auto_dose_state["next_dose_time"] = auto_dose_state["last_dose_time"] + timedelta(hours=interval_hours)
                else:
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                time.sleep(5)
                continue

            # If it's time to dose
            if now >= auto_dose_state["next_dose_time"]:
                # Auto-dose logic (decide up or down & how much)
                dose_type, dose_amount = perform_auto_dose(settings)
                # If dose_amount > 0 => we dispensed
                if dose_amount > 0:
                    auto_dose_state["last_dose_time"] = now
                    auto_dose_state["last_dose_type"] = dose_type
                    auto_dose_state["last_dose_amount"] = dose_amount
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)
                else:
                    # No dose needed. Maybe check again soon
                    auto_dose_state["next_dose_time"] = now + timedelta(hours=interval_hours)

            time.sleep(5)

        except Exception as e:
            log_with_timestamp(f"[AutoDosing] Error: {e}")
            time.sleep(5)

# Background task to broadcast pH readings
def broadcast_ph_readings():
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
            time.sleep(1)
        except Exception as e:
            print(f"[Broadcast] Error broadcasting pH value: {e}")

def start_threads():
    if stop_event.is_set():
        log_with_timestamp("Background threads already stopped. Starting again.")
    else:
        log_with_timestamp("Background threads are running. Skipping redundant start.")
    stop_event.clear()
    # pH broadcast
    threading.Thread(target=broadcast_ph_readings, daemon=True).start()
    # auto-dosing
    threading.Thread(target=auto_dosing_loop, daemon=True).start()
    # serial
    start_serial_reader()

def stop_threads():
    print("Stopping background threads...")
    stop_event.set()
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

atexit.register(cleanup)

# Register API blueprints
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
def settings():
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
    if not stop_event.is_set():
        print("Starting background threads...")
        start_threads()
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
    """
    Render a page that shows:
      - current pH
      - system volume
      - auto-dosing status
      - pH target
      - calculated amounts for pH Up and pH Down
      - last dose info
      - next dose time
    """
    dosage_data = get_dosage_info()

    # We'll add auto-dose info from auto_dose_state
    # so the template can display last/next dose times.
    dosage_data["last_dose_time"] = auto_dose_state["last_dose_time"].strftime("%Y-%m-%d %H:%M:%S") if auto_dose_state["last_dose_time"] else "Never"
    dosage_data["last_dose_type"] = auto_dose_state["last_dose_type"] or "N/A"
    dosage_data["last_dose_amount"] = auto_dose_state["last_dose_amount"]
    dosage_data["next_dose_time"] = auto_dose_state["next_dose_time"].strftime("%Y-%m-%d %H:%M:%S") if auto_dose_state["next_dose_time"] else "Not Scheduled"

    return render_template('dosage.html', dosage_data=dosage_data)

# For manual dosing from UI
@app.route('/api/dosage/manual', methods=['POST'])
def api_manual_dosage():
    data = request.get_json()
    dispense_type = data.get('type')  # 'up' or 'down'
    amount = data.get('amount', 0)

    from services.dosage_service import manual_dispense
    manual_dispense(dispense_type, amount)

    # Reset the auto-dosing timer so we start a new interval
    reset_auto_dose_timer()
    # Record what we did
    from datetime import datetime
    auto_dose_state["last_dose_time"] = datetime.now()
    auto_dose_state["last_dose_type"] = dispense_type
    auto_dose_state["last_dose_amount"] = amount
    auto_dose_state["next_dose_time"] = None  # Will be re-set in auto_dosing_loop

    return jsonify({"status": "success", "message": f"Dispensed {amount} ml of pH {dispense_type}."})

@app.route('/api/device/config', methods=['GET', 'POST'])
def device_config():
    # ... existing code ...
    pass

if __name__ == '__main__':
    try:
        start_threads()
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("Application interrupted. Exiting...")
    finally:
        cleanup()
