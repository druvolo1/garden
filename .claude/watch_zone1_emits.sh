#!/bin/bash
# Subscribe to zone1.dr /status as a client and log every status_update
# for 12 seconds. Meanwhile, toggle valve 1 on fill.dr (Zone 1 Fill OFF
# then back ON, since it's currently on). The expected good behavior:
# Zone 1 Fill alternates cleanly between on and off, with no transient
# "off everywhere" event.
set +e

PY=~/garden/venv/bin/python3

# launch the watcher in background
"$PY" - <<'PY' > /tmp/zone1_emits.log 2>&1 &
import socketio, json, time, sys
sio = socketio.Client(logger=False, engineio_logger=False)
events = []

@sio.on("status_update", namespace="/status")
def on_evt(data):
    vr = (data.get("valve_info") or {}).get("valve_relays") or {}
    z1f = vr.get("Zone 1 Fill", {}).get("status", "?")
    z1d = vr.get("Zone 1 Drain", {}).get("status", "?")
    t   = time.strftime("%H:%M:%S")
    keys = sorted(vr.keys())
    print(f"{t} Z1Fill={z1f} Z1Drain={z1d}  keys={keys}", flush=True)

@sio.on("valve_update", namespace="/status")
def on_vu(data):
    t = time.strftime("%H:%M:%S")
    print(f"{t} VALVE_UPDATE_EVENT: {data}", flush=True)

try:
    sio.connect("http://zone1.dr:8000", socketio_path="/socket.io",
                transports=["websocket","polling"], namespaces=["/status"])
    time.sleep(15)
finally:
    try: sio.disconnect()
    except: pass
PY
WATCHER_PID=$!
sleep 2

echo "=== toggling Zone 1 Fill OFF on fill.dr ==="
curl -s -X POST http://fill.dr:8000/api/valve_relay/1/off; echo
sleep 4
echo "=== toggling Zone 1 Fill back ON on fill.dr ==="
curl -s -X POST http://fill.dr:8000/api/valve_relay/1/on; echo
sleep 5

wait $WATCHER_PID 2>/dev/null

echo "=== ZONE1 EMITTED STATUS_UPDATES ==="
cat /tmp/zone1_emits.log
