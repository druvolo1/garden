#!/bin/bash
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

echo "=== AFS settings: concentration + drain_flow_settings + additional_plants ==="
$PY - <<'PY'
import json, pathlib
s = json.loads((pathlib.Path.home()/'Auto-Feeding-System/data/settings.json').read_text())
print(f"  nutrient_concentration: {s.get('nutrient_concentration')}")
print(f"  drain_flow_settings:    {json.dumps(s.get('drain_flow_settings'), indent=4)}")
print(f"  calibration_factors:    {json.dumps(s.get('calibration_factors'))}")
print(f"  additional_plants:      {s.get('additional_plants')}")
print(f"  drain_sensor:           {s.get('drain_sensor', '(unset; defaults to sensor3)')}")
print(f"  fill_sensor:            {s.get('fill_sensor',  '(unset; defaults to sensor1)')}")
PY

echo
echo "=== Each plant's allow_remote_feeding (via AFS plant_data cache) ==="
$PY - <<'PY'
import socketio, time
sio = socketio.Client(logger=False, engineio_logger=False)
got = []
@sio.on("plants_update", namespace="/status")
def on_pu(data):
    got.append(data)

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
deadline = time.time() + 8
while time.time() < deadline and not got:
    time.sleep(0.3)
if got:
    plants = got[0].get("plants") or []
    for p in plants:
        ip = p.get("ip") or p.get("original_host") or "?"
        online = p.get("is_online")
        s = p.get("settings", {}) or {}
        allow = s.get("allow_remote_feeding")
        vi = p.get("valve_info") or {}
        wl = p.get("water_level") or {}
        sensors = {k: v.get("triggered") for k, v in wl.items() if isinstance(v, dict)}
        print(f"  {ip:15s}  online={online}  allow_remote_feeding={allow}")
        print(f"    fill={vi.get('fill_valve_label')!r}  drain={vi.get('drain_valve_label')!r}")
        print(f"    water_level (triggered flags): {sensors}")
sio.disconnect()
PY

echo
echo "=== Current valve states on fill.dr and drain.dr ==="
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f\"  fill[{k}] {v['label']}: {v['status']}\") for k,v in d['valves'].items()]"
curl -s http://Drain.local:8000/api/valve_relay/all_status | python3 -c "import json,sys;d=json.load(sys.stdin);[print(f\"  drain[{k}] {v['label']}: {v['status']}\") for k,v in d['valves'].items()]"

echo
echo "=== Is a feeding sequence already running? ==="
curl -s http://127.0.0.1:8001/api/feeding/status
