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
from api.valve_relay import valve_relay_blueprint
from api.plant_info import plant_info_blueprint  # New blueprint

# Import the aggregator's set_socketio_instance + our /status namespace
from status_namespace import StatusNamespace, set_socketio_instance
from status_namespace import is_debug_enabled

# Services
from services.auto_dose_state import auto_dose_state
from services.auto_dose_utils import reset_auto_dose_timer
from services.ph_service import get_latest_ph_reading, serial_reader
from services.dosage_service import get_dosage_info, perform_auto_dose, manual_dispense  # Added manual_dispense
from services.error_service import check_for_hardware_errors
from utils.settings_utils import load_settings

# Changelog dependencies
import markdown

# Added imports for remote WS
import uuid
import json
from queue import Queue
import threading
import asyncio
import websockets

########################################################################
# Added globals for remote WS
########################################################################
send_queue = Queue()
ws_connected = False
device_id = None
api_key = None
server_url = 'wss://garden.ruvolo.loseyourip.com/ws/devices'  # e.g., 'wss://your-server.com/ws/devices'

########################################################################
# Added config loading (device_id, api_key, server_url)
########################################################################
SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

def load_config():
    global device_id, api_key, server_url
    settings = {}
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                print(f"[CONFIG] Settings loaded from {SETTINGS_FILE}")
        
        # Generate/load device_id
        if 'device_id' in settings:
            device_id = settings['device_id']
            print(f"[CONFIG] Device ID loaded: {device_id}")
        else:
            device_id = str(uuid.uuid4())
            settings['device_id'] = device_id
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
            print(f"[CONFIG] New Device ID generated and saved: {device_id}")
        
        # Load api_key and server_url if present
        api_key = settings.get('api_key')
        server_url = settings.get('server_url')
        server_enabled = settings.get('server_enabled', False)
        
        if api_key and server_url and server_enabled:
            print("[CONFIG] API key, server URL, and enabled flag loaded; will connect to remote server.")
        else:
            print("[CONFIG] Missing API key, server URL, or not enabled; remote sync disabled.")
        
        return device_id, api_key, server_url
    except Exception as e:
        print(f"[CONFIG ERROR] Failed to load or save config: {e}")
        return None, None, None

def start_ws_client():
    settings = load_settings()
    if settings.get('server_enabled', False) and api_key and server_url:
        thread = threading.Thread(target=lambda: asyncio.run(ws_client()))
        thread.daemon = True
        thread.start()

load_config()

########################################################################
# Added remote WS client
########################################################################
async def ws_client():
    global ws_connected
    uri = f"{server_url}/{device_id}?api_key={api_key}"
    try:
        async with websockets.connect(uri) as ws:
            ws_connected = True
            print(f"Connected to remote server WS at {uri}")
            while True:
                try:
                    # Send from queue
                    if not send_queue.empty():
                        data = send_queue.get()
                        print(f"Sending to remote WS: {json.dumps(data)}")
                        await ws.send(json.dumps(data))
                    
                    # Receive commands
                    data = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    payload = json.loads(data)
                    print(f"Received from remote WS: {json.dumps(payload)}")
                    # Handle incoming commands (e.g., from remote dashboard)
                    if payload.get('command') == 'manual_dose':
                        params = payload.get('params', {})
                        dispense_type = params.get('dispense_type')
                        amount = params.get('amount', 0.0)
                        manual_dispense(dispense_type, amount)
                        reset_auto_dose_timer()
                        auto_dose_state["last_dose_time"] = datetime.now()
                        auto_dose_state["last_dose_type"] = dispense_type
                        auto_dose_state["last_dose_amount"] = amount
                        print(f"Remote manual dose executed: {dispense_type} {amount}ml")
                    # Add more command handlers here for index controls
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"WS inner error: {e}")
                    break
    except Exception as e:
        print(f"WS connection error: {e}")
    ws_connected = False
    print("WS disconnected; retrying in 10s...")
    await asyncio.sleep(10)
    await ws_client()  # Retry

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
                    # Added: Forward to remote server if connected
                    if ws_connected:
                        send_queue.put({'type': 'ph_update', 'ph': ph_value})
            eventlet.sleep(1)
        except Exception as e:
            log_with_timestamp(f"[Broadcast] Error broadcasting pH value: {e}")

def broadcast_status():
    """ Periodically call emit_status_update() from status_namespace. """
    from status_namespace import emit_status_update
    log_with_timestamp("Inside function for broadcasting status updates")
    while True:
        try:
            payload = emit_status_update()
            # Added: Forward status to remote (adjust 'data' if emit_status_update returns specific data; otherwise, trigger a full status push)
            if ws_connected and payload is not None:
                send_queue.put({'type': 'status_update', 'data': payload})  # Add actual data if available from emit
            eventlet.sleep(1)
        except Exception as e:
            log_with_timestamp(f"[broadcast_status] Error: {e}")
            eventlet.sleep(1)

def auto_dose_loop():
    while True:
        settings = load_settings()
        dosing_interval_hours = settings.get("dosing_interval", 1.0)  # Define outside the if, with a default
        if settings.get("auto_dosing_enabled", False):
            perform_auto_dose(settings)
        eventlet.sleep(dosing_interval_hours * 3600)  # Now always safe to use

def start_threads():
    settings = load_settings()
    # Broadcast latest pH to websockets
    log_with_timestamp("Spawning broadcast_ph_readings…")
    eventlet.spawn(broadcast_ph_readings)

    # Serial reader from services.ph_service import serial_reader
    log_with_timestamp("Spawning pH serial reader…")
    eventlet.spawn(serial_reader)

    # Status broadcaster
    log_with_timestamp("Spawning status broadcaster…")
    eventlet.spawn(broadcast_status)

    # Hardware error checker
    log_with_timestamp("Spawning hardware error checker…")
    eventlet.spawn(check_for_hardware_errors)

    # Auto-dosing loop
    log_with_timestamp("Spawning auto-dosing loop…")
    eventlet.spawn(auto_dose_loop)

    # Power control loop
    from services.power_control_service import power_control_main_loop
    log_with_timestamp("Spawning power control loop…")
    eventlet.spawn(power_control_main_loop)

    # Water level monitoring
    from services.water_level_service import monitor_water_level_sensors
    log_with_timestamp("Spawning water level sensor monitor…")
    eventlet.spawn(monitor_water_level_sensors)

    # Valve relay polling
    from services.valve_relay_service import init_valve_thread
    log_with_timestamp("Initializing valve relay service…")
    init_valve_thread()

    # EC serial reader
    from services.ec_service import ec_serial_reader
    log_with_timestamp("Spawning EC serial reader…")
    eventlet.spawn(ec_serial_reader)

    # Added: Start remote WS client if configured
    start_ws_client()

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
app.register_blueprint(valve_relay_blueprint, url_prefix='/api/valve_relay')
app.register_blueprint(plant_info_blueprint, url_prefix='/api/plant_info')  # New blueprint

########################################################################
# Routes
########################################################################
@app.route('/')
def index():
    pi_ip = get_local_ip()
    return render_template('index.html', pi_ip=pi_ip, device_id=device_id)  # Added device_id

@app.route('/settings')
def settings_page():
    pi_ip = get_local_ip()
    return render_template('settings.html', pi_ip=pi_ip, device_id=device_id)

@app.route('/calibration')
def calibration():
    return render_template('calibration.html')

@app.route('/configuration')
def configuration():
    return render_template('configuration.html')

@app.route('/valves')
def valves_page():
    return render_template('valves.html')

@app.route('/changelog')
def show_changelog():
    changelog_path = os.path.join(os.path.dirname(__file__), 'CHANGELOG.md')  # Adjust path if needed
    if os.path.exists(changelog_path):
        with open(changelog_path, 'r') as f:
            md_content = f.read()
        html_content = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])  # Add extensions for better formatting
    else:
        html_content = "<p>No changelog available.</p>"
    return render_template('changelog.html', changelog_html=html_content)

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

@app.route('/plant_info')
def plant_info_page():
    return render_template('plant_info.html')

# Initialization logic (moved from post_fork for consistency)
print("[WSGI] Initializing. Starting threads and registering mDNS...")
try:
    start_threads()
    print("[WSGI] Background threads started successfully.")
    s = load_settings()
    system_name = s.get("system_name", "Garden")
    # 1) Register the system_name-pc mDNS (hostname-based)
    # register_mdns_pc_hostname(system_name, service_port=8000)
    # 2) Also register the pure system name
    #from mdsn import register_mdns_pure_system_name
    #register_mdns_pure_system_name(system_name, service_port=8000)
    #print(f"[WSGI] Completed mDNS registration for '{system_name}'.")
except Exception as e:
    print(f"[WSGI] Error in top-level startup code: {e}")

########################################################################
# MAIN
########################################################################
if __name__ == "__main__":
    # Added: Load config early
    load_config()
    log_with_timestamp("[WSGI] Running in local development mode...")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)