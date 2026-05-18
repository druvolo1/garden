#!/bin/bash
# Run on zone1.dr. Confirm aggregator is now connected to fill.dr and
# emitting correct Zone 1 Fill state.
set +e
PY=~/garden/venv/bin/python3

echo "=== Outbound sockets to :8000 ==="
ss -tn 'dst :8000' 2>/dev/null

echo
echo "=== fill.dr's reported state for valve 1 ==="
curl -s -m 3 http://fill.dr:8000/api/valve_relay/all_status | python3 -c "import json,sys;d=json.load(sys.stdin);v=d['valves']['1'];print(f'  fill.dr valve 1 ({v[\"label\"]}): {v[\"status\"]}')"

echo
echo "=== zone1's emitted Zone 1 Fill via websocket ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    got.append(data)
sio.connect("http://zone1.dr:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
deadline = time.time() + 4
while time.time() < deadline and not got:
    time.sleep(0.1)
if got:
    vr = (got[0].get("valve_info") or {}).get("valve_relays") or {}
    z1f = vr.get("Zone 1 Fill", {}).get("status", "?")
    z1d = vr.get("Zone 1 Drain", {}).get("status", "?")
    print(f"  Zone 1 Fill : {z1f}")
    print(f"  Zone 1 Drain: {z1d}")
sio.disconnect()
PY

echo
echo "=== Aggregator [AGG] activity in last 6 seconds ==="
T0=$(date -d '6 seconds ago' '+%Y-%m-%d %H:%M:%S')
# enable debug briefly so [AGG] lines are emitted
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
p.write_text(json.dumps(d, indent=4))
PY
sleep 4
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\]" | head -20 || echo "  (no AGG lines)"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
p.write_text(json.dumps(d, indent=4))
PY
