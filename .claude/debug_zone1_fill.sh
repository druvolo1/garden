#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== Step 1: zone1 settings labels (exact bytes) ==="
"$PY" - <<'PY'
import json, pathlib
s = json.loads((pathlib.Path.home()/'garden/data/settings.json').read_text())
for k in ['fill_valve_label','drain_valve_label','fill_valve_ip','drain_valve_ip','fill_valve','drain_valve']:
    v = s.get(k)
    print(f"  {k}: {v!r}  len={len(v) if isinstance(v,str) else 'n/a'}  hex={(v.encode().hex() if isinstance(v,str) else 'n/a')}")
PY

echo
echo "=== Step 2: fresh websocket connection to zone1.dr (just like a browser refresh) ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
events = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    events.append(data)
@sio.on("valve_update", namespace="/status")
def on_vu(data):
    events.append({"_partial": True, **data})

sio.connect("http://zone1.dr:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"])
# Wait up to 5s for events
deadline = time.time() + 5
while time.time() < deadline:
    if events:
        break
    time.sleep(0.1)
print(f"Received {len(events)} events in {time.time() - (deadline-5):.2f}s")
if events:
    d = events[0]
    vi = d.get("valve_info") or {}
    vr = vi.get("valve_relays") or {}
    print(f"  settings.fill_valve_label  = {d.get('settings',{}).get('fill_valve_label')!r}")
    print(f"  settings.drain_valve_label = {d.get('settings',{}).get('drain_valve_label')!r}")
    print(f"  valve_info.valve_relays keys = {list(vr.keys())!r}")
    fl = d.get('settings',{}).get('fill_valve_label')
    dl = d.get('settings',{}).get('drain_valve_label')
    print(f"  relays[fill_valve_label] = {vr.get(fl)!r}  (key={fl!r}, match={fl in vr})")
    print(f"  relays[drain_valve_label]= {vr.get(dl)!r}  (key={dl!r}, match={dl in vr})")
    # bytes-level comparison
    for k in vr.keys():
        if 'Fill' in k:
            print(f"  emit key {k!r}  hex={k.encode().hex()}")
        if 'Drain' in k:
            print(f"  emit key {k!r}  hex={k.encode().hex()}")
sio.disconnect()
PY

echo
echo "=== Step 3: zone1's cached state from Fill.dr ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
events = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    events.append(data)
sio.connect("http://fill.dr:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"])
deadline = time.time() + 5
while time.time() < deadline and not events:
    time.sleep(0.1)
if events:
    vr = (events[0].get("valve_info") or {}).get("valve_relays") or {}
    print("  Fill.dr emits valve_relays keys:", sorted(vr.keys()))
    # Find anything that contains "Zone 1"
    for k, v in vr.items():
        if "Zone 1" in k or "1 Fill" in k:
            print(f"  match: {k!r} = {v}  hex={k.encode().hex()}")
sio.disconnect()
PY
