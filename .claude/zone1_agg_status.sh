#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
p.write_text(json.dumps(d, indent=4))
PY

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0  -- watching for 10s"
sleep 10

echo "=== zone1 [AGG] events from Fill.dr in last 10s ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\].*Fill\.dr" | tail -10 || echo "  (none — zone1 not receiving)"

echo
echo "=== zone1 [AGG] events from drain.dr in last 10s ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -iE "AGG\].*drain\.dr" | tail -10 || echo "  (none)"

echo
echo "=== Connection attempts / errors in last 10s ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\] (Attempting|Connected|Disconnected|Connect error|Failed|Already connected)" | tail -20

echo
echo "=== Reachability from zone1 to fill.dr ports 8000 and 8001 ==="
curl -s -m 3 -o /dev/null -w "fill.dr:8000 /api/valve_relay/all_status -> HTTP %{http_code}\n" http://fill.dr:8000/api/valve_relay/all_status
curl -s -m 3 -o /dev/null -w "fill.dr:8001 / -> HTTP %{http_code}\n" http://fill.dr:8001/
curl -s -m 3 -o /dev/null -w "drain.dr:8000 /api/valve_relay/all_status -> HTTP %{http_code}\n" http://drain.dr:8000/api/valve_relay/all_status

echo
echo "=== Disable debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
p.write_text(json.dumps(d, indent=4))
PY
