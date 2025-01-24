from flask import Flask, render_template
from flask_socketio import SocketIO
from api.ph import ph_blueprint
from api.pump import pump_blueprint
from api.relay import relay_blueprint
from api.water_level import water_level_blueprint
from api.settings import settings_blueprint
from api.logs import log_blueprint

# Initialize Flask app and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

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
    return render_template('index.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

# Example WebSocket event: real-time pH updates
@socketio.on('connect')
def handle_connect():
    print("Client connected")
    socketio.emit('message', {'data': 'Welcome to the pH Dosing System!'})

# Main entry point
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000,debug=True)
