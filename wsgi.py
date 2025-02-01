# File: wsgi.py
import eventlet
eventlet.monkey_patch()

from app import app, start_threads

# This function will be called by Gunicorn after a worker is forked
def post_fork(server, worker):
    print(f"[Gunicorn] Worker {worker.pid} forked. Starting threads...")
    start_threads()  # Start background threads for this worker

# Attach the post_fork hook to Gunicorn
def when_ready(server):
    server.log.info("Server is ready. Spawning workers...")

# Gunicorn configuration
bind = "0.0.0.0:5000"
workers = 1  # Use only 1 worker to avoid duplicate threads
worker_class = "eventlet"
timeout = 60
loglevel = "debug"

# If running locally (not under Gunicorn), start the app directly
if __name__ == "__main__":
    print("[WSGI] Running in local development mode...")
    start_threads()  # Start threads for local development
    app.run(host="0.0.0.0", port=5000, debug=True)