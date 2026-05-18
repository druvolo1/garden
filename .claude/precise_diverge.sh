#!/bin/bash
# Take a snapshot of (a) fill.dr's API for valve 1, (b) zone1's emitted
# Zone 1 Fill via WS, at multiple times during and after a toggle.
set +e

PY=~/garden/venv/bin/python3

"$PY" - <<'PY'
import socketio, requests, time, threading

# Latest event from zone1
latest = {"z1": "(none)", "z1_ts": None, "n": 0}

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("status_update", namespace="/status")
def on_evt(data):
    vr = (data.get("valve_info") or {}).get("valve_relays") or {}
    z1 = vr.get("Zone 1 Fill", {}).get("status", "?")
    latest["z1"] = z1
    latest["z1_ts"] = time.time()
    latest["n"] += 1

sio.connect("http://zone1.dr:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"])
print(f"Connected, waiting 1s for initial state...")
time.sleep(1.5)

def sample(label):
    fill_status = requests.get("http://fill.dr:8000/api/valve_relay/all_status", timeout=3).json()
    fill_v1 = fill_status["valves"]["1"]["status"]
    age = (time.time() - latest["z1_ts"]) if latest["z1_ts"] else 999
    print(f"{label:20s}  fill.dr/api v1={fill_v1:3s}  zone1 ws Z1Fill={latest['z1']:3s}  evt#={latest['n']:2d}  evt_age={age:.2f}s")

sample("PRE-OFF")
print(">>> POST /api/valve_relay/1/off on fill.dr")
requests.post("http://fill.dr:8000/api/valve_relay/1/off", timeout=5)
time.sleep(0.5);  sample("OFF + 0.5s")
time.sleep(0.5);  sample("OFF + 1.0s")
time.sleep(1.0);  sample("OFF + 2.0s")
time.sleep(1.0);  sample("OFF + 3.0s")

print(">>> POST /api/valve_relay/1/on on fill.dr")
requests.post("http://fill.dr:8000/api/valve_relay/1/on", timeout=5)
time.sleep(0.5);  sample("ON  + 0.5s")
time.sleep(0.5);  sample("ON  + 1.0s")
time.sleep(1.0);  sample("ON  + 2.0s")

sio.disconnect()
PY
