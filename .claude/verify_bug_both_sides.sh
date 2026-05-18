#!/bin/bash
# Run from any machine with ssh access. Enable websocket debug on both
# fill.dr and zone1.dr, then toggle valve 4, then dump both journals.
set +e

# Pass the role: "setup", "toggle", "capture"
ROLE=$1

if [ "$ROLE" = "setup" ]; then
  echo "=== Enable websocket debug locally ($(hostname)) ==="
  python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
d['status_namespace'] = True
p.write_text(json.dumps(d, indent=4))
PY
  cat ~/garden/data/debug_settings.json

elif [ "$ROLE" = "toggle" ]; then
  echo "=== T0 ==="; date '+%Y-%m-%d %H:%M:%S'
  sleep 1
  echo "=== Toggle valve 4 ON on fill.dr ==="
  curl -s -X POST http://fill.dr:8000/api/valve_relay/4/on; echo
  sleep 2
  echo "=== Toggle valve 4 OFF on fill.dr ==="
  curl -s -X POST http://fill.dr:8000/api/valve_relay/4/off; echo
  sleep 3

elif [ "$ROLE" = "capture" ]; then
  SINCE=$2
  echo "=== JOURNAL on $(hostname) since $SINCE ==="
  journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
    grep -E "Emitting granular valve_update|Emitting status_update|AGG\]|valve_relays|on_remote_status_update" | tail -60

elif [ "$ROLE" = "teardown" ]; then
  echo "=== Disable websocket debug ($(hostname)) ==="
  python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
d['status_namespace'] = False
p.write_text(json.dumps(d, indent=4))
PY
fi
