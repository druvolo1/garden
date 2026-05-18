#!/bin/bash
# Toggle valve 4 (Res Fill) ON->OFF on fill.dr, capture parse_hardware_response
# hex and API state at each step. Live (debug flag, no restart). Service stays
# running so zone Pi websockets stay connected.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== Enable valve_relay debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = True
p.write_text(json.dumps(d, indent=4))
PY

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0"

echo
echo "=== STATE BEFORE ==="
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -m json.tool | grep -A 2 '"4"'

echo
echo "=== TURN VALVE 4 ON ==="
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/4/on | python3 -m json.tool
sleep 3

echo "=== STATE AFTER ON ==="
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -m json.tool | grep -A 2 '"4"'

echo
echo "=== TURN VALVE 4 OFF ==="
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/4/off | python3 -m json.tool
sleep 4

echo "=== STATE AFTER OFF ==="
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -m json.tool | grep -A 2 '"4"'

echo
echo "=== JOURNAL since $T0: hex responses + state changes ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "parse_hardware_response received raw|Updated valve_status|Sending|polled as|changed from|Detected" | tail -60

echo
echo "=== Disable debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = False
p.write_text(json.dumps(d, indent=4))
PY

echo "=== DONE ==="
