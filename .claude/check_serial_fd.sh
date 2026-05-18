#!/bin/bash
set +e
echo "=== HOSTNAME: $(hostname) ==="
echo "=== by-path symlinks and tty nodes ==="
ls -l /dev/serial/by-path/ /dev/ttyUSB* 2>&1

echo "=== garden gunicorn open fds pointing at ttyUSB* ==="
for p in $(pgrep -f 'garden.*wsgi:app'); do
  echo "-- pid $p --"
  ls -l /proc/$p/fd 2>/dev/null | grep -E "ttyUSB|ttyACM" || echo "  (none)"
done

echo "=== recent Polling errors / queued commands ==="
journalctl -u garden.service --since '15 minutes ago' --no-pager 2>/dev/null | \
  grep -E "\[Valve\] Polling error|\[Valve\] Queued|deleted" | tail -20
