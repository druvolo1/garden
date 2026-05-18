#!/bin/bash
# Extended test: confirm ON eventually completes after the 5s cooldown
set +e

PY=~/garden/venv/bin/python3

"$PY" - <<'PY'
import socketio, requests, time

latest = {"z1": "(none)", "z1_ts": None, "n": 0}

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("status_update", namespace="/status")
def on_evt(data):
    vr = (data.get("valve_info") or {}).get("valve_relays") or {}
    latest["z1"] = vr.get("Zone 1 Fill", {}).get("status", "?")
    latest["z1_ts"] = time.time()
    latest["n"] += 1

sio.connect("http://zone1.dr:8000", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"])
time.sleep(1.5)

def sample(label):
    fill_status = requests.get("http://fill.dr:8000/api/valve_relay/all_status", timeout=3).json()
    fill_v1 = fill_status["valves"]["1"]["status"]
    age = (time.time() - latest["z1_ts"]) if latest["z1_ts"] else 999
    print(f"{label:24s}  fill.dr/api v1={fill_v1:3s}  zone1 ws Z1Fill={latest['z1']:3s}  evt#={latest['n']:2d}  evt_age={age:.2f}s")

# Make sure we start with valve OFF (no cooldown)
print(">>> Initial OFF to start clean (may already be off)")
requests.post("http://fill.dr:8000/api/valve_relay/1/off", timeout=5)
time.sleep(6)  # let cooldown elapse
sample("CLEAN START")

print(">>> POST /api/valve_relay/1/on")
requests.post("http://fill.dr:8000/api/valve_relay/1/on", timeout=5)
for i in [0.5, 1, 2, 3, 5, 7]:
    time.sleep(i if i==0.5 else i - (0.5 if i==1 else (i-1) if i>1 else 0))
    sample(f"ON  + {i}s")

# Quick OFF→ON cycle to see cooldown
print(">>> Quick OFF then ON")
requests.post("http://fill.dr:8000/api/valve_relay/1/off", timeout=5)
time.sleep(1)
sample("OFF +1s")
requests.post("http://fill.dr:8000/api/valve_relay/1/on", timeout=5)
for i in [1, 3, 5, 7, 9]:
    time.sleep(2)
    sample(f"ON  +{i}s after OFF")

sio.disconnect()
PY
