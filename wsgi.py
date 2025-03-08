# File: wsgi.py

import eventlet
eventlet.monkey_patch()

# Import your app & start_threads as before
from app import app, start_threads

def post_fork(server, worker):
    """
    Gunicorn calls this after a worker process is forked.
    We'll start our threads here.
    """
    print(f"[Gunicorn] Worker {worker.pid} forked. Starting threads...")

    try:
        # Start any background threads in this worker
        start_threads()
        print(f"[Gunicorn] Worker {worker.pid} threads started successfully.")
    except Exception as e:
        print(f"[Gunicorn] Error starting threads in worker {worker.pid}: {e}")
        raise

def when_ready(server):
    """
    Called just before Gunicorn starts accepting requests.
    """
    server.log.info("Gunicorn server is ready. Workers will be spawned now...")

# Gunicorn config:
bind = "0.0.0.0:8000"
workers = 1
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False

# STANDALONE (DEV) MODE
if __name__ == "__main__":
    print("[WSGI] Running in local development mode (not under Gunicorn).")
    try:
        start_threads()
        print("[WSGI] Background threads started successfully.")
    except Exception as e:
        print(f"[WSGI] Error starting background threads: {e}")
        raise

    # Run Flask’s built-in dev server
    app.run(host="0.0.0.0", port=8000, debug=True)
