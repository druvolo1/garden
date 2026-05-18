#!/bin/bash
# Connect to a remote /status websocket as a client, wait for one
# status_update event, dump the valve_info portion. Usage: dump_ws.sh <host>
set +e

HOST=$1
[ -z "$HOST" ] && { echo "need host arg"; exit 1; }

# Use the local venv from any garden install on this Pi (has python-socketio)
PY=~/garden/venv/bin/python3
[ ! -x "$PY" ] && PY=python3

echo "=== Dumping status_update from $HOST ==="
"$PY" - "$HOST" <<'PY'
import sys, json, time
import socketio

host = sys.argv[1]
sio = socketio.Client(logger=False, engineio_logger=False)
result = {"got_event": False}

@sio.on("status_update", namespace="/status")
def on_evt(data):
    if result["got_event"]:
        return
    result["got_event"] = True
    # Print key parts
    print(f"--- {host} status_update payload ---")
    print(f"top-level keys: {list(data.keys())}")
    vi = data.get("valve_info") or {}
    print(f"valve_info keys: {list(vi.keys())}")
    print(f"valve_info.fill_valve_label: {vi.get('fill_valve_label')!r}")
    print(f"valve_info.drain_valve_label: {vi.get('drain_valve_label')!r}")
    print(f"valve_info.fill_valve_ip:    {vi.get('fill_valve_ip')!r}")
    print(f"valve_info.drain_valve_ip:   {vi.get('drain_valve_ip')!r}")
    vr = vi.get("valve_relays") or {}
    print(f"valve_info.valve_relays ({len(vr)} entries):")
    for k, v in vr.items():
        print(f"  {k!r}: {v}")
    sio.disconnect()

try:
    sio.connect(f"http://{host}:8000", socketio_path="/socket.io",
                transports=["websocket","polling"], namespaces=["/status"])
    for _ in range(20):
        if result["got_event"]:
            break
        time.sleep(0.25)
    if not result["got_event"]:
        print("(timeout waiting for status_update event)")
finally:
    try: sio.disconnect()
    except: pass
PY
