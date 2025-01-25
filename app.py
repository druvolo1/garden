import socket
import time
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from api.ph import ph_blueprint
from api.pump import pump_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint
from services.ph_service import get_ph_reading
from api.settings import load_settings
from services.ph_service import listen_for_ph_readings


# Initialize Flask app and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

# Function to get the Pi's local IP address
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Connect to an external address to determine the local IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"  # Fallback to localhost
    finally:
        s.close()
    return ip

# Background task to broadcast pH readings
def broadcast_ph_readings():
    while True:
        settings = load_settings()
        ph_probe = settings.get("usb_roles", {}).get("ph_probe")

        if ph_probe:  # Only emit readings if a pH probe is assigned
            try:
                ph_value = get_ph_reading()
                if ph_value is not None:
                    # Emit to all connected clients
                    socketio.emit('ph_update', {'ph': ph_value})
                    print(f"Emitting pH update: {ph_value}")
            except Exception as e:
                print(f"Error reading pH value: {e}")
        else:
            print("No pH probe assigned. Skipping pH reading.")

        time.sleep(1)  # Emit every second

# Start background tasks
socketio.start_background_task(broadcast_ph_readings)
socketio.start_background_task(listen_for_ph_readings)

# Register API blueprints
app.register_blueprint(ph_blueprint, url_prefix='/api/ph')
app.register_blueprint(pump_blueprint, url_prefix='/api/pump')
app.register_blueprint(relay_blueprint, url_prefix='/api/relay')
app.register_blueprint(water_level_blueprint, url_prefix='/api/water_level')
app.register_blueprint(settings_blueprint, url_prefix='/api/settings')
app.register_blueprint(log_blueprint, url_prefix='/api/logs')

# Serve the main dashboard page
@app.route('/')
def index():
    pi_ip = get_local_ip()  # Get the Pi's IP address
    return render_template('index.html', pi_ip=pi_ip)  # Pass it to the frontend

@app.route('/settings')
def settings():
    pi_ip = get_local_ip()  # Get the Pi's IP address
    return render_template('settings.html', pi_ip=pi_ip)  # Pass it to the frontend

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    emit('message', {'data': 'Connected to the server'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
