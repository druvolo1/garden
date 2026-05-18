#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== Outbound BEFORE ==="
ss -tn 'dst :8000' 2>/dev/null

echo
echo "=== Subscribing to zone1 /status (triggers on_connect) ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    got.append(time.time())
sio.connect("http://127.0.0.1:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=8)
print(f"  connected; waiting 10s for events...")
time.sleep(10)
print(f"  received {len(got)} status_update events")
sio.disconnect()
PY

echo
echo "=== Outbound AFTER ==="
ss -tn 'dst :8000' 2>/dev/null

echo
echo "=== Enable WS debug and capture aggregator activity ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
p.write_text(json.dumps(d, indent=4))
PY
T0=$(date '+%Y-%m-%d %H:%M:%S')
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
sio.connect("http://127.0.0.1:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
time.sleep(3)
sio.disconnect()
PY

echo "  --- [AGG] activity (Fill.dr and drain.dr) ---"
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\]" | head -30
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
p.write_text(json.dumps(d, indent=4))
PY
