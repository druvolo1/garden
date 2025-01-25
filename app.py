import socket
import time
import threading
import atexit
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from api.ph import ph_blueprint
from api.pump import pump_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from services.ph_service import get_latest_ph_reading, start_serial_reader, stop_serial_reader
from api.settings import load_settings
from flask_socketio import SocketIO, emit
from services.ph_service import get_latest_ph_reading

app = Flask(__name__)
socketio = SocketIO(app)
stop_event = threading.Event()  # Event to stop background threads
cleanup_called = False  # To avoid duplicate cleanup calls


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
            if ph_value is not None and ph_value != last_emitted_value:
                last_emitted_value = ph_value
                socketio.emit('ph_update', {'ph': ph_value})  # Emit the value
                print(f"Emitting pH update: {ph_value}")
            time.sleep(1)  # Check for updates every second
        except Exception as e:
            print(f"Error broadcasting pH value: {e}")


# Start threads for background tasks
def start_threads():
    stop_event.clear()
    threading.Thread(target=broadcast_ph_readings, daemon=True).start()
    start_serial_reader()  # Start the centralized serial reader


# Stop threads gracefully
def stop_threads():
    print("Stopping background threads...")
    stop_event.set()
    stop_serial_reader()  # Stop the centralized serial reader
    time.sleep(1)
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

@socketio.on('connect')
def handle_connect():
    global latest_ph_value  # Ensure access to the global variable
    print("Client connected")
    if latest_ph_value is not None:
        socketio.emit('ph_update', {'ph': latest_ph_value})

if __name__ == '__main__':
    try:
        start_threads()  # Start background tasks
        socketio.run(app, host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("Application interrupted. Exiting...")
    finally:
        cleanup()
