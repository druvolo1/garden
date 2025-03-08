# File: wsgi.py

import eventlet
eventlet.monkey_patch()
import subprocess

from app import app, start_threads

def flush_avahi():
    """
    Call a shell script that stops Avahi, clears stale records, and restarts Avahi.
    Must have passwordless sudo set up for systemctl and rm commands.
    """
    script_path = "/home/dave/garden/scripts/flush_avahi.sh"
    try:
        # If you require passwordless sudo, then "sudo" won't prompt for a password here.
        subprocess.run(["sudo", script_path], check=True)
        print("[Gunicorn] Avahi has been flushed prior to starting threads.")
    except subprocess.CalledProcessError as e:
        print(f"[Gunicorn] Failed to flush Avahi: {e}")

def post_fork(server, worker):
    """
    Gunicorn calls this after a worker process is forked.
    We'll first flush Avahi, then start any background threads.
    """
    print(f"[Gunicorn] Worker {worker.pid} forked. Flushing Avahi, then starting threads...")

    # --- Flush Avahi right here ---
    flush_avahi()

    try:
        # Now start any background threads in this worker
        start_threads()
        print(f"[Gunicorn] Worker {worker.pid} threads started successfully.")
    except Exception as e:
        print(f"[Gunicorn] Error starting threads in worker {worker.pid}: {e}")
        raise

def when_ready(server):
    server.log.info("Gunicorn server is ready. Workers will be spawned now...")

bind = "0.0.0.0:8000"
workers = 1
worker_class = "eventlet"
timeout = 60
loglevel = "debug"
preload_app = False

if __name__ == "__main__":
    print("[WSGI] Running in local development mode (not under Gunicorn).")
    try:
        # If you also want to flush Avahi in dev mode, call it here:
        flush_avahi()
        start_threads()
        print("[WSGI] Background threads started successfully.")
    except Exception as e:
        print(f"[WSGI] Error starting background threads: {e}")
        raise

    app.run(host="0.0.0.0", port=8000, debug=True)
