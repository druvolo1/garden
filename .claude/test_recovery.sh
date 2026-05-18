#!/bin/bash
# Simulate a USB disconnect/reconnect on fill.dr's relay port (1-1.3) and
# verify garden.service recovers via _reset_serial_connection.
set +e

echo "=== Enable valve debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = True
p.write_text(json.dumps(d, indent=4))
PY

T0=$(date '+%Y-%m-%d %H:%M:%S')
echo "T0=$T0"
sleep 1

echo "=== BEFORE: ttyUSB nodes ==="
ls -l /dev/ttyUSB* /dev/serial/by-path/ 2>&1

echo "=== Unbind USB 1-1.3 (relay board) ==="
echo password | sudo -S sh -c 'echo "1-1.3" > /sys/bus/usb/drivers/usb/unbind'
sleep 2

echo "=== DURING unbind: ttyUSB nodes ==="
ls -l /dev/ttyUSB* /dev/serial/by-path/ 2>&1

echo "=== Rebind USB 1-1.3 ==="
echo password | sudo -S sh -c 'echo "1-1.3" > /sys/bus/usb/drivers/usb/bind'
sleep 3

echo "=== AFTER rebind: ttyUSB nodes ==="
ls -l /dev/ttyUSB* /dev/serial/by-path/ 2>&1

echo "=== Garden gunicorn fd ==="
for p in $(pgrep -f 'garden.*wsgi:app'); do
  ls -l /proc/$p/fd 2>/dev/null | grep -E "ttyUSB|ttyACM" || true
done

echo "=== Wait 2 more seconds for recovery loop to catch up ==="
sleep 2

echo "=== Valve journal since $T0 ==="
journalctl -u garden.service --since "$T0" --no-pager 2>/dev/null | \
  grep -E "\[Valve\]" | tail -30

echo "=== /api/valve_relay/all_status (should still respond and be coherent) ==="
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -m json.tool | head -20

echo "=== Test a toggle: turn valve 1 OFF, wait, ON ==="
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/1/off; echo
sleep 6  # allow cooldown
curl -s -X POST http://127.0.0.1:8000/api/valve_relay/1/on; echo
sleep 2
curl -s http://127.0.0.1:8000/api/valve_relay/all_status | python3 -c "import json,sys;d=json.load(sys.stdin);print('valve 1 is now:', d['valves']['1']['status'])"

echo "=== Disable debug ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/debug_settings.json'
d = json.loads(p.read_text())
d['valve_relay_service'] = False
p.write_text(json.dumps(d, indent=4))
PY
echo "=== DONE ==="
