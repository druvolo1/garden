#!/bin/bash
# Enable debug live on fill.dr's garden.service, tail journal for ~15s of
# polling cycles, then disable debug. No service restart needed.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== ENABLE valve_relay_service debug (live, no restart) ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = True
p.write_text(json.dumps(d, indent=4))
print(p.read_text())
PY

echo "=== Mark time and wait 15s for polling cycles ==="
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "since: $START_TIME"
sleep 15

echo "=== DISABLE debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = False
p.write_text(json.dumps(d, indent=4))
PY

echo "=== Journal: parse_hardware_response lines since $START_TIME ==="
journalctl -u garden.service --since "$START_TIME" --no-pager 2>/dev/null | grep -E "parse_hardware_response received raw|Updated valve_status|Valve.*changed" | tail -40

echo "=== /api/valve_relay/all_status right now ==="
curl -s -m 3 http://127.0.0.1:8000/api/valve_relay/all_status | python3 -m json.tool

echo "=== DONE ==="
