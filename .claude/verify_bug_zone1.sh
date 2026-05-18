#!/bin/bash
# On zone1.dr: enable websocket+status_namespace debug if it exists,
# capture journal during a valve toggle issued on fill.dr.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== Enable websocket debug on zone1 (so [AGG] lines show) ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
d['status_namespace'] = True
p.write_text(json.dumps(d, indent=4))
print(p.read_text())
PY

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0"
echo "Sleeping 2s before toggle..."
sleep 2

echo "=== Toggle valve 4 ON on fill.dr (via remote curl) ==="
curl -s -X POST http://fill.dr:8000/api/valve_relay/4/on
sleep 2

echo "=== Toggle valve 4 OFF on fill.dr ==="
curl -s -X POST http://fill.dr:8000/api/valve_relay/4/off
sleep 4

echo "=== ZONE1 journal since $T0 -- on_remote_status_update entries ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | grep -E "AGG\] on_remote_status_update|valve_update|valve_info|valve_relays|Emitting status_update" | tail -60

echo "=== Disable debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
d['status_namespace'] = False
p.write_text(json.dumps(d, indent=4))
PY

echo "=== DONE ==="
