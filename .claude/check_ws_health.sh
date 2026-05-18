#!/bin/bash
# Run from any Pi. Test websocket connectivity to fill.dr.
set +e
PY=~/garden/venv/bin/python3
[ ! -x "$PY" ] && PY=python3

echo "=== From $(hostname): TCP/HTTP check ==="
ss -tn 'dst :8000' 2>/dev/null | head -20
echo "--- HTTP probe ---"
curl -s -m 3 -o /dev/null -w "fill.dr:8000 GET /status -> HTTP %{http_code}\n" http://fill.dr:8000/socket.io/?transport=polling

echo
echo "=== Open sockets to fill.dr:8000 (from $(hostname)) ==="
ss -tnp 'dst :8000' 2>/dev/null | head -20

echo
echo "=== Fresh websocket connect attempt to fill.dr/status ==="
"$PY" - <<'PY'
import socketio, time, traceback
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("status_update", namespace="/status")
def on_evt(data):
    got.append(data)

try:
    print("  connecting...")
    sio.connect("http://fill.dr:8000", socketio_path="/socket.io",
                transports=["websocket","polling"], namespaces=["/status"], wait_timeout=8)
    print("  connected OK")
    deadline = time.time() + 4
    while time.time() < deadline and not got:
        time.sleep(0.1)
    if got:
        vr = (got[0].get("valve_info") or {}).get("valve_relays") or {}
        print(f"  got status_update: keys={list(vr.keys())[:4]}...")
    else:
        print("  no event received in 4s")
    sio.disconnect()
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}")
PY
