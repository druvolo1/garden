#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== Confirm deployed status_namespace.py has the fix ==="
grep -n -B1 -A3 'namespaces=\["/status"\]' ~/garden/status_namespace.py | head -10

echo
echo "=== Reproduce aggregator's exact code path (with eventlet) ==="
"$PY" - <<'PY'
# Simulate gunicorn's environment: monkey-patch with eventlet first
import eventlet
eventlet.monkey_patch()

import socketio, time

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("status_update", namespace="/status")
def on_evt(data):
    print("    [evt] got status_update")

resolved_ip = "drain.dr"
url = f"http://{resolved_ip}:8000"

try:
    print(f"  [AGG-SIM] Attempting to connect to {url}")
    sio.connect(url, socketio_path="/socket.io",
                transports=["websocket", "polling"],
                namespaces=["/status"], wait_timeout=5)
    print(f"  [AGG-SIM] CONNECTED")
    time.sleep(2)
    sio.disconnect()
except Exception as e:
    print(f"  [AGG-SIM] Failed: {type(e).__name__}: {e}")

# Try without explicit transports (matches AFS pattern)
print()
sio2 = socketio.Client(logger=False, engineio_logger=False)
@sio2.on("status_update", namespace="/status")
def on_evt2(data):
    print("    [evt2] got status_update")
try:
    print(f"  [SIMPLE-SIM] Attempting (no transports) to drain.dr:8000")
    sio2.connect(url, namespaces=["/status"], wait_timeout=5)
    print(f"  [SIMPLE-SIM] CONNECTED")
    time.sleep(2)
    sio2.disconnect()
except Exception as e:
    print(f"  [SIMPLE-SIM] Failed: {type(e).__name__}: {e}")
PY
