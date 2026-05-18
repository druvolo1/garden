#!/bin/bash
# Run on drain.dr: stop service, enable valve debug, start gunicorn, wait,
# then dump the parse_hardware_response output so we can see the actual reply
# format of the new NOYITO board.
set +e

LOG=/tmp/valve_debug.log
PIDFILE=/tmp/valve_debug.pid

echo "=== HOSTNAME ==="
hostname

echo "=== STOP garden.service (so it doesn't fight us for the USB port) ==="
echo password | sudo -S systemctl stop garden.service
sleep 1
systemctl is-active garden.service

echo "=== ENABLE valve_relay_service debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = True
p.write_text(json.dumps(d, indent=4))
print(p.read_text())
PY

echo "=== Free any stale processes on port 8000 / old log/pid ==="
[ -f "$PIDFILE" ] && kill "$(cat $PIDFILE)" 2>/dev/null
rm -f "$LOG" "$PIDFILE"
fuser -k 8000/tcp 2>/dev/null
sleep 1

echo "=== LAUNCH gunicorn detached, redirected to $LOG ==="
cd ~/garden || exit 1
( bash -c 'source venv/bin/activate && exec gunicorn -w 1 -k eventlet wsgi:app --bind 0.0.0.0:8000 --log-level=debug' > "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDFILE" )
sleep 1
echo "PID=$(cat $PIDFILE)"
pgrep -af gunicorn | head

echo "=== Wait 8s for polling cycles to run ==="
sleep 8

echo "=== Confirm gunicorn is still up ==="
pgrep -af gunicorn | head

echo "=== Tail of valve debug log: parse_hardware_response lines ==="
echo "----- ALL hex-dump lines: -----"
grep "parse_hardware_response received raw" "$LOG"
echo "----- ALL Updated valve_status lines: -----"
grep "Updated valve_status" "$LOG"
echo "----- last 60 lines of log overall (in case of error): -----"
tail -60 "$LOG"
