#!/bin/bash
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

echo "=== fill.dr outbound :8001 (AFS's plant clients are inbound to zones, on :8000) ==="
ss -tn 'dst :8000' 2>/dev/null

echo
echo "=== Connect to AFS and wait 15s for plants_update ==="
"$PY" - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
plants_seen = []
@sio.on("plants_update", namespace="/status")
def on_pu(data):
    plants_seen.append(data)

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)

for _ in range(30):
    time.sleep(0.5)
    if plants_seen and (plants_seen[-1].get("plants") or []):
        break

if not plants_seen:
    print("  No plants_update event received in 15s")
else:
    last = plants_seen[-1]
    plants = last.get("plants") or []
    print(f"  plants_update received {len(plants_seen)} times; last has {len(plants)} plants:")
    for p in plants:
        ip = p.get("ip", "local")
        online = p.get("is_online")
        vi = p.get("valve_info") or {}
        fl = vi.get("fill_valve_label")
        dl = vi.get("drain_valve_label")
        vr = vi.get("valve_relays") or {}
        fs = (vr.get(fl) or {}).get("status") if fl else None
        ds = (vr.get(dl) or {}).get("status") if dl else None
        print(f"    {ip:15s}  online={online}  fill[{fl}]={fs}  drain[{dl}]={ds}")
sio.disconnect()
PY

echo
echo "=== AFS journal (last 20s) ==="
journalctl -u feeding.service --since '20 seconds ago' --no-pager 2>/dev/null | \
  grep -iE "plant|Connected|Failed|resolve|mDNS" | tail -30
