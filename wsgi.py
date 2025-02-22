# File: wsgi.py

import eventlet
eventlet.monkey_patch()

from app import app, start_threads
from services.mdns_service import register_mdns_service

# -----------------------
# GUNICORN HOOKS/CONFIG
# -----------------------

def post_fork(server, worker):
    """
    Gunicorn calls this after a worker process is forked.
    We'll start our threads and mDNS advertisement here.
    """
    print(f"[Gunicorn] Worker {worker.pid} forked. Starting threads & mDNS...")

    try:
        # Start any background threads in this worker
        start_threads()

        # Register mDNS
        global mdns_zeroconf, mdns_info
        mdns_zeroconf, mdns_info = register_mdns_service(system_name="MyGardenService", port=8000)
        print(f"[Gunicorn] Worker {worker.pid} mDNS service registered successfully.")
    except Exception as e:
        print(f"[Gunicorn] Error starting threads or mDNS in worker {worker.pid}: {e}")
        raise

def when_ready(server):
    """
    Called just before Gunicorn starts accepting requests.
    """
    server.log.info("Gunicorn server is ready. Workers will be spawned now...")

# Gunicorn configuration variables
bind = "0.0.0.0:8000"
workers = 1            # Use 1 worker to avoid duplicating threads/mDNS
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False    # So threads/mDNS start after fork, per best practice

# This is the WSGI callable Gunicorn will use
# (gunicorn wsgi:app --config wsgi.py)
# or programmatically: app variable is imported from app.py
# def app(environ, start_response):
#     ...

# -----------------------
# STANDALONE (DEV) MODE
# -----------------------
if __name__ == "__main__":
    print("[WSGI] Running in local development mode (not under Gunicorn).")
    try:
        # Start the same background threads
        start_threads()
        # Also register the mDNS service locally
        mdns_zeroconf, mdns_info = register_mdns_service(system_name="GardenMonitor", port=8000)
        print("[WSGI] Background threads and mDNS service started successfully.")
    except Exception as e:
        print(f"[WSGI] Error starting background threads or mDNS: {e}")
        raise

    # Run Flask’s built-in dev server
    app.run(host="0.0.0.0", port=8000, debug=True)
