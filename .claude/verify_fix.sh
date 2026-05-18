#!/bin/bash
# Verify the fix: enable websocket debug on fill.dr and zone1.dr, toggle
# valve 4, then confirm zone1's aggregator only ever sees full payloads
# (i.e. no payload keys list = [type, valve_id, label, status, timestamp]).
set +e

ROLE=$1

if [ "$ROLE" = "on" ] || [ "$ROLE" = "off" ]; then
  python3 - <<PY
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket']        = ('$ROLE' == 'on')
d['status_namespace'] = ('$ROLE' == 'on')
p.write_text(json.dumps(d, indent=4))
PY

elif [ "$ROLE" = "toggle" ]; then
  echo "=== Toggle valve 4 ON on fill.dr ==="
  curl -s -X POST http://fill.dr:8000/api/valve_relay/4/on; echo
  sleep 3
  echo "=== Toggle valve 4 OFF on fill.dr ==="
  curl -s -X POST http://fill.dr:8000/api/valve_relay/4/off; echo
  sleep 3

elif [ "$ROLE" = "fill_capture" ]; then
  SINCE=$2
  echo "=== fill.dr emit log since $SINCE ==="
  journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
    grep -E "Emitting (granular valve_update|status_update)|Valve [0-9].*changed" | tail -20

elif [ "$ROLE" = "zone1_capture" ]; then
  SINCE=$2
  echo "=== zone1 aggregator log since $SINCE ==="
  echo "  --- look for [AGG] on_remote_status_update lines (these are 'I got an event'): ---"
  journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
    grep -E "AGG\] on_remote_status_update" | head -30
  echo
  echo "  --- look for partial-payload keys (BAD if seen): ---"
  journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
    grep -E "on_remote_status_update.*keys: \[.*'valve_id'" | head -10 || echo "  (none — good)"
  echo
  echo "  --- look for full-payload keys (expected): ---"
  journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
    grep -E "on_remote_status_update.*keys: \[.*'valve_info'" | head -10
fi
