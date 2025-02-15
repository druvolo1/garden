# File: wsgi.py
import eventlet
eventlet.monkey_patch()

from app import app, start_threads
from mdns_service import register_mdns_service  # <-- Import your function

# This function will be called by Gunicorn after a worker is forked
def post_fork(server, worker):
    print(f"[Gunicorn] Worker {worker.pid} forked. Starting threads...")
    try:
        start_threads()  # Start background threads for this worker
        
        # Register the mDNS service
        mdns_zeroconf, mdns_info = register_mdns_service(service_name="GardenMonitor", port=8000)
        print(f"[Gunicorn] Worker {worker.pid} MDNS service registered successfully.")
        
        print(f"[Gunicorn] Worker {worker.pid} threads started successfully.")
    except Exception as e:
        print(f"[Gunicorn] Error starting threads in worker {worker.pid}: {e}")
        raise  # Re-raise the exception to prevent the worker from hanging

# Attach the post_fork hook to Gunicorn
def when_ready(server):
    server.log.info("Server is ready. Spawning workers...")

# Gunicorn configuration
bind = "0.0.0.0:8000"
workers = 1  # Use only 1 worker to avoid duplicate threads
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False  # Ensure the app is loaded after the worker is forked

# If running locally (not under Gunicorn), start the app directly
if __name__ == "__main__":
    print("[WSGI] Running in local development mode...")
    try:
        start_threads()  # Start threads for local development
        # Also register the mDNS service locally:
        mdns_zeroconf, mdns_info = register_mdns_service(service_name="GardenMonitor", port=8000)
        print("[WSGI] Background threads and MDNS service started successfully.")
    except Exception as e:
        print(f"[WSGI] Error starting background threads: {e}")
        raise  # Re-raise the exception to prevent the app from hanging
    app.run(host="0.0.0.0", port=8000, debug=True)
