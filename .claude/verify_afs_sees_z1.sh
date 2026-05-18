#!/bin/bash
# On fill.dr, subscribe to fill.dr:8001 (AFS) and dump the plants_update
# that AFS sends to its browser clients. Look for Zone 1 entry and its
# fill valve status.
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("plants_update", namespace="/status")
def on_pu(data):
    got.append(data)

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
deadline = time.time() + 6
while time.time() < deadline and not got:
    time.sleep(0.2)

if not got:
    print("No plants_update received in 6s")
else:
    plants = got[0].get("plants", [])
    print(f"AFS emitted plants_update with {len(plants)} plant(s):")
    for p in plants:
        ip = p.get('ip', 'local')
        vi = p.get('valve_info') or {}
        fl = vi.get('fill_valve_label')
        dl = vi.get('drain_valve_label')
        vr = vi.get('valve_relays') or {}
        fs = (vr.get(fl) or {}).get('status', 'N/A') if fl else 'N/A'
        ds = (vr.get(dl) or {}).get('status', 'N/A') if dl else 'N/A'
        online = p.get('is_online', '?')
        print(f"  {ip:15s} online={online}  fill[{fl}]={fs}  drain[{dl}]={ds}")
sio.disconnect()
PY
