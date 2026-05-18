#!/bin/bash
# Calibration run for AFS draining. Enables extended log, starts a flow/feedback
# logger, kicks off /api/feeding/start_all, then waits for the sequence to end.
set +e
PY=~/Auto-Feeding-System/venv/bin/python3
LOG=/tmp/afs_calibration.log
JSONLOG=/tmp/afs_calibration_events.jsonl

# Enable extended log so per-second drain monitoring is visible
$PY - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'
s = json.loads(p.read_text())
s.setdefault('debug_states', {})['feeding-extended-log'] = True
p.write_text(json.dumps(s, indent=4))
print(f"[setup] feeding-extended-log enabled; nutrient_concentration={s.get('nutrient_concentration')}")
PY

# Restart feeding.service to pick up debug change (no setting change needed for behavior)
echo password | sudo -S systemctl restart feeding.service
sleep 6
systemctl is-active feeding.service

# Start a background WS logger writing JSON-lines events to /tmp/afs_calibration_events.jsonl
$PY - <<'PY' &
import socketio, time, json, threading, signal, sys
sio = socketio.Client(logger=False, engineio_logger=False)
out = open("/tmp/afs_calibration_events.jsonl", "w", buffering=1)
stop = threading.Event()

def write(kind, data):
    rec = {"t": time.time(), "kind": kind, "data": data}
    out.write(json.dumps(rec) + "\n")

@sio.on("local_status_update", namespace="/status")
def on_local(d):
    # Capture drain_flow most importantly
    write("local_status_update", {
        "drain_flow": d.get("drain_flow"),
        "drain_total_volume": d.get("drain_total_volume"),
        "fresh_flow": d.get("fresh_flow"),
        "fresh_total_volume": d.get("fresh_total_volume"),
        "feed_flow": d.get("feed_flow"),
        "feed_total_volume": d.get("feed_total_volume"),
        "feed_level": d.get("feed_level"),
    })

@sio.on("feeding_feedback", namespace="/status")
def on_fb(d):
    write("feeding_feedback", d)

@sio.on("feeding_sequence_state", namespace="/status")
def on_state(d):
    write("feeding_sequence_state", d)
    if d.get("active") is False:
        stop.set()

@sio.on("plants_update", namespace="/status")
def on_pu(d):
    # Just record sensor states + valve states per plant
    plants = []
    for p in (d.get("plants") or []):
        plants.append({
            "ip": p.get("ip"),
            "water_level": {k: v.get("triggered") for k, v in (p.get("water_level") or {}).items() if isinstance(v, dict)},
            "fill":  ((p.get("valve_info") or {}).get("valve_relays") or {}).get((p.get("valve_info") or {}).get("fill_valve_label"), {}).get("status"),
            "drain": ((p.get("valve_info") or {}).get("valve_relays") or {}).get((p.get("valve_info") or {}).get("drain_valve_label"), {}).get("status"),
            "is_currently_feeding": p.get("is_currently_feeding"),
        })
    write("plants_update", {"plants": plants})

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
print("[logger] connected, waiting for events...", flush=True)
# Wait until feeding_sequence_state goes inactive, or 25-minute hard timeout
deadline = time.time() + 25*60
while not stop.is_set() and time.time() < deadline:
    time.sleep(0.5)
print(f"[logger] done (stop={stop.is_set()}, time={time.time():.0f})", flush=True)
sio.disconnect()
out.close()
PY
LOGGER_PID=$!
echo "[start] logger PID=$LOGGER_PID"
sleep 3

# Trigger the feeding sequence
echo "[start] POST /api/feeding/start_all"
curl -s -X POST http://127.0.0.1:8001/api/feeding/start_all
echo

# Wait for the logger (waits up to 25 minutes for sequence to end)
wait $LOGGER_PID
echo "[done] logger exited"

# Disable extended log to keep journal tidy after
$PY - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'
s = json.loads(p.read_text())
s.setdefault('debug_states', {})['feeding-extended-log'] = False
p.write_text(json.dumps(s, indent=4))
print(f"[cleanup] feeding-extended-log disabled")
PY

echo "=== Captured event counts ==="
wc -l /tmp/afs_calibration_events.jsonl
echo "Events log: /tmp/afs_calibration_events.jsonl"
