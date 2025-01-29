import eventlet
eventlet.monkey_patch()   # Must be done before importing Flask or your app

from app import app, start_threads
# Optionally: from app import socketio if you do dev testing here

# Possibly call start_threads() here so it always runs in each worker:
start_threads()  # If you want to do so unconditionally

# If you do local dev testing with python wsgi.py:
if __name__ == "__main__":
    # For local single-process dev only
    app.run(host="0.0.0.0", port=5000)
