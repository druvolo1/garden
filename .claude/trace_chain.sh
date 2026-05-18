#!/bin/bash
# Trace the fill.dr -> zone1.dr aggregation chain during a valve toggle.
set +e

enable_debug() {
  python3 - <<PY
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = True
d['valve_relay_service'] = True
p.write_text(json.dumps(d, indent=4))
PY
}

disable_debug() {
  python3 - <<PY
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['websocket'] = False
d['valve_relay_service'] = False
p.write_text(json.dumps(d, indent=4))
PY
}

case "$1" in
  enable)  enable_debug ;;
  disable) disable_debug ;;
  fill_log)
    SINCE=$2
    journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
      grep -E "Emitting (granular valve_update|status_update)|Valve 1 polled|parse_hardware_response received" | tail -30
    ;;
  zone1_log)
    SINCE=$2
    echo "  --- [AGG] events received from Fill.dr ---"
    journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
      grep -E "AGG\] on_remote_status_update from Fill.dr" | tail -30
    echo "  --- Zone1's OWN emit_status_update calls ---"
    journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
      grep -E "Emitting status_update|Change detected|No changes detected" | tail -30
    echo "  --- get_cached_remote_states(Fill.dr) lookups (showing the keys it returned) ---"
    journalctl -u garden.service --since "$SINCE" --no-pager 2>/dev/null | \
      grep -E "get_cached_remote_states\(Fill" | tail -10
    ;;
esac
