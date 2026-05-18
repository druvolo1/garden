#!/bin/bash
set +e
LOG=/tmp/valve_debug.log
PIDFILE=/tmp/valve_debug.pid

echo "=== Kill manual gunicorn ==="
if [ -f "$PIDFILE" ]; then
  kill "$(cat $PIDFILE)" 2>/dev/null
  sleep 1
fi
fuser -k 8000/tcp 2>/dev/null
sleep 1
pgrep -af gunicorn

echo "=== Disable valve_relay_service debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = False
p.write_text(json.dumps(d, indent=4))
print(p.read_text())
PY

echo "=== Restart garden.service ==="
echo password | sudo -S systemctl start garden.service
sleep 2
systemctl is-active garden.service
echo "--- last 5 status lines ---"
systemctl status garden.service --no-pager -l | tail -8

echo "=== Cleanup tmp files ==="
rm -f /tmp/valve_debug.pid /tmp/diag5.sh /tmp/diag3.sh /tmp/diag2.sh
ls -la /tmp/valve_debug.log 2>&1
echo "(leaving /tmp/valve_debug.log behind in case we want to look at it later)"

echo "=== DONE ==="
