import socket
import time
import threading
import atexit
import json
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from api.ph import ph_blueprint
from api.pump import pump_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from services.ph_service import get_latest_ph_reading, start_serial_reader, stop_serial_reader
from services.ph_service import latest_ph_value
from datetime import datetime
from services.device_config import (
    get_hostname, set_hostname, get_ip_config, set_ip_config, get_timezone, set_timezone,
    is_daylight_savings, get_ntp_server, set_ntp_server, get_wifi_config, set_wifi_config
)
from services.dosage_service import get_dosage_info


app = Flask(__name__)
socketio = SocketIO(app, async_mode="eventlet")  # or "gevent" if you switch to gevent
stop_event = threading.Event()  # Event to stop background threads
cleanup_called = False  # To avoid duplicate cleanup calls
serial_reader_thread = None  # Global variable for tracking the serial reader thread

def log_with_timestamp(message):
    """Log messages with a timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


# Function to get the Pi's local IP address
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"  # Fallback to localhost
    finally:
        s.close()
    return ip


# Background task to broadcast pH readings
def broadcast_ph_readings():
    """Emit the latest pH value over WebSocket whenever it changes."""
    last_emitted_value = None
    while not stop_event.is_set():
        try:
            ph_value = get_latest_ph_reading()  # Get the latest value
            ph_value = round(ph_value, 2)  # Round to 2 decimal places
            if ph_value is not None and ph_value != last_emitted_value:
                last_emitted_value = ph_value
                socketio.emit('ph_update', {'ph': ph_value})  # Emit the value
                print(f"[Broadcast] Emitting pH update: {ph_value}")
            #else:
            #    print("[Broadcast] No new pH value to emit.")
            time.sleep(1)  # Check for updates every second
        except Exception as e:
            print(f"[Broadcast] Error broadcasting pH value: {e}")

# Start threads for background tasks
def start_threads():
    if stop_event.is_set():
        log_with_timestamp("Background threads already stopped. Starting again.")
    else:
        log_with_timestamp("Background threads are running. Skipping redundant start.")
    stop_event.clear()
    threading.Thread(target=broadcast_ph_readings, daemon=True).start()
    start_serial_reader()

def stop_threads():
    """Stop all background threads."""
    print("Stopping background threads...")
    stop_event.set()  # Signal threads to stop
    stop_serial_reader()  # Properly stop the serial reader
    print("Background threads stopped.")

# Cleanup function
def cleanup():
    global cleanup_called
    if cleanup_called:
        return
    cleanup_called = True
    print("Cleaning up resources...")
    stop_threads()
    print("Background threads stopped.")


atexit.register(cleanup)  # Register cleanup function

# Register API blueprints
app.register_blueprint(ph_blueprint, url_prefix='/api/ph')
app.register_blueprint(pump_blueprint, url_prefix='/api/pump')
app.register_blueprint(relay_blueprint, url_prefix='/api/relay')
app.register_blueprint(water_level_blueprint, url_prefix='/api/water_level')
app.register_blueprint(settings_blueprint, url_prefix='/api/settings')
app.register_blueprint(log_blueprint, url_prefix='/api/logs')


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
    """Render the device configuration page."""
    return render_template('configuration.html')

@socketio.on('connect')
def handle_connect():
    """Handle new client connections."""
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
    """
    dosage_data = get_dosage_info()
    return render_template('dosage.html', dosage_data=dosage_data)

@app.route('/api/dosage/manual', methods=['POST'])
def api_manual_dosage():
    """
    Endpoint to manually dispense pH Up or Down for the calculated amount.
    Expects JSON with:
      {
        "type": "up" or "down",
        "amount":  [some numeric value]
      }
    """
    data = request.get_json()
    dispense_type = data.get('type')  # 'up' or 'down'
    amount = data.get('amount', 0)

    if dispense_type not in ['up', 'down']:
        return jsonify({"status": "failure", "error": "Invalid dispense type"}), 400

    manual_dispense(dispense_type, amount)

    return jsonify({"status": "success", "message": f"Dispensed {amount} ml of pH {dispense_type}."})

@app.route('/api/device/config', methods=['GET', 'POST'])
def device_config():
    """
    API endpoint to get or set device configuration.
    """
    if request.method == 'GET':
        try:
            # Fetch configuration for Ethernet (eth0)
            eth0_config = get_ip_config(interface="eth0")

            # Fetch configuration for Wi-Fi (wlan0)
            wlan0_config = get_ip_config(interface="wlan0")
            wlan0_config["ssid"] = get_wifi_config()

            # Construct the response
            config = {
                "hostname": get_hostname(),
                "eth0": eth0_config,
                "wlan0": wlan0_config,
                "timezone": get_timezone(),
                "daylight_savings": is_daylight_savings(),
                "ntp_server": get_ntp_server()
            }

            return jsonify({"status": "success", "config": config}), 200
        except Exception as e:
            return jsonify({"status": "failure", "message": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json()

            # Update hostname if provided
            if "hostname" in data:
                set_hostname(data["hostname"])

            # Update network configuration for specified interface
            if "interface" in data:
                set_ip_config(
                    interface=data["interface"],
                    dhcp=data.get("dhcp", False),
                    ip_address=data.get("ip_address"),
                    subnet_mask=data.get("subnet_mask"),
                    gateway=data.get("gateway"),
                    dns_server=data.get("dns_server")
                )

            # Update timezone and NTP if provided
            if "timezone" in data:
                set_timezone(data["timezone"])
            if "ntp_server" in data:
                set_ntp_server(data["ntp_server"])

            # Update Wi-Fi configuration only if SSID or password is provided
            if "wifi_ssid" in data:
                set_wifi_config(data["wifi_ssid"], data.get("wifi_password"))

            return jsonify({"status": "success", "message": "Configuration applied successfully."}), 200
        except Exception as e:
            return jsonify({"status": "failure", "message": str(e)}), 500

# Run the application for development purposes
if __name__ == '__main__':
    try:
        start_threads()  # Start background tasks
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)  # For local development
    except KeyboardInterrupt:
        print("Application interrupted. Exiting...")
    finally:
        cleanup()
