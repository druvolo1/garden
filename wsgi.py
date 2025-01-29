# File: wsgi.py
import eventlet
eventlet.monkey_patch()

from app import app, start_threads

# Start your threads at import time:
print("[WSGI] top-level import: about to call start_threads()")
start_threads()  # Will launch auto_dosing_loop, broadcast_ph_readings, etc.

if __name__ == "__main__":
    # local dev testing only
    app.run(host="0.0.0.0", port=5000, debug=True)
