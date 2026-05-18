#!/bin/bash
set +e
echo "=== HOSTNAME: $(hostname) ==="

echo "--- python-socketio + python-engineio versions ---"
~/garden/venv/bin/pip show python-socketio python-engineio 2>/dev/null | grep -E "Name|Version"

echo
echo "--- TIME_WAIT count and ephemeral range ---"
ss -tan state time-wait 2>/dev/null | wc -l
cat /proc/sys/net/ipv4/ip_local_port_range

echo
echo "--- Detailed websocket connect with engineio logger ---"
~/garden/venv/bin/python3 - <<'PY'
import socketio, time, logging, sys
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s: %(message)s', stream=sys.stdout)
sio = socketio.Client(logger=True, engineio_logger=True)
@sio.on("status_update", namespace="/status")
def on_evt(data):
    print(f"  STATUS_UPDATE received")

try:
    print("Connecting...")
    sio.connect("http://fill.dr:8000", socketio_path="/socket.io",
                transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
    print("CONNECTED")
    time.sleep(2)
    sio.disconnect()
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
PY
