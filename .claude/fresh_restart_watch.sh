#!/bin/bash
set +e

# Enable websocket debug FIRST
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
p.write_text(json.dumps(d, indent=4))
PY

echo "=== Stop garden.service and wait 15s ==="
echo password | sudo -S systemctl stop garden.service
sleep 15

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0"
echo "=== Start garden.service ==="
echo password | sudo -S systemctl start garden.service

# Now wait for the FIRST aggregator attempts (triggered by polling/etc)
# and poke it manually with a curl to force on_connect.
sleep 4
curl -s -m 3 -o /dev/null http://127.0.0.1:8000/api/valve_relay/all_status &
sleep 3

echo "=== Outbound after init ==="
ss -tn 'dst :8000' 2>/dev/null

echo "=== First [AGG] log entries since restart ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "AGG\]" | head -30

# disable debug
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
p.write_text(json.dumps(d, indent=4))
PY
