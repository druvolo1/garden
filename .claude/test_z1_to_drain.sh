#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== Fresh WS connect from zone1 to drain.dr/status ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    got.append(data)
try:
    sio.connect("http://drain.dr:8000", socketio_path="/socket.io",
                transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
    print("  CONNECTED OK")
    time.sleep(1.5)
    if got:
        vr = (got[0].get("valve_info") or {}).get("valve_relays") or {}
        print(f"  got status_update with valve_relays keys: {sorted(vr.keys())[:3]}...")
    else:
        print("  connected but no event in 1.5s")
    sio.disconnect()
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
PY

echo
echo "=== zone1 [AGG] activity related to drain.dr (debug-enabled briefly) ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
p.write_text(json.dumps(d, indent=4))
PY
T0=$(date '+%Y-%m-%d %H:%M:%S')
sleep 4
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -iE "AGG\].*drain" | head -10 || echo "  (no AGG/drain lines)"
echo "  --- generic AGG lines ---"
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\]" | head -10
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
p.write_text(json.dumps(d, indent=4))
PY
