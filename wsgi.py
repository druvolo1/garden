# File: wsgi.py

import eventlet
eventlet.monkey_patch()
import subprocess
import os, stat

from app import app, start_threads

def ensure_script_executable(script_path: str):
    """Check if script is executable by the owner; if not, chmod +x."""
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    mode = os.stat(script_path).st_mode
    # Check if the owner-execute bit is set:
    if not (mode & stat.S_IXUSR):
        print(f"[INFO] Making {script_path} executable (chmod +x)")
        subprocess.run(["chmod", "+x", script_path], check=True)

def flush_avahi():
    """
    Stop Avahi, remove stale runtime files, and restart it.
    Ensures the script is executable first.
    """
    script_path = "/home/dave/garden/scripts/flush_avahi.sh"

    # 1) Make sure it’s executable
    ensure_script_executable(script_path)

    # 2) Call the script with sudo
    try:
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

    flush_avahi()

    try:
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
        flush_avahi()
        start_threads()
        print("[WSGI] Background threads started successfully.")
    except Exception as e:
        print(f"[WSGI] Error starting background threads: {e}")
        raise

    app.run(host="0.0.0.0", port=8000, debug=True)
