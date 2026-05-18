#!/bin/bash
# Run on fill.dr: enable valve_relay_service debug, watch the journal during
# an OFF/ON toggle, capture parse_hardware_response hex.
set +e

python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = True
d['websocket']           = True
p.write_text(json.dumps(d, indent=4))
PY

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0"
sleep 1

echo "=== TURN VALVE 1 OFF on fill.dr ==="
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/1/off; echo
sleep 4

echo "=== TURN VALVE 1 ON on fill.dr ==="
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/1/on; echo
sleep 3

echo "=== FULL valve_relay_service journal since $T0 ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "\[Valve\]" | tail -60

echo "=== Disable debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = False
d['websocket']           = False
p.write_text(json.dumps(d, indent=4))
PY

echo "=== ALSO check for water_level/auto_dosing acting on valves ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -iE "water_level|auto_dosing|fill.*on|fill.*off|reasserting|Turn.*ON|Turn.*OFF" | tail -20
