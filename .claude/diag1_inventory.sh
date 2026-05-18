#!/bin/bash
# Inventory: identify which code is actually controlling the relay on this Pi.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== ALL ENABLED *.service WITH gunicorn or python ==="
for unit in $(systemctl list-unit-files --type=service --state=enabled --no-legend --no-pager | awk '{print $1}'); do
  ex=$(systemctl cat "$unit" 2>/dev/null | grep -E "^ExecStart=" | head -1)
  if echo "$ex" | grep -qiE "gunicorn|wsgi|python.*Auto-Feeding|python.*garden"; then
    echo "--- $unit ---"
    echo "$ex"
    systemctl is-active "$unit"
  fi
done

echo "=== RUNNING gunicorn PROCESSES ==="
ps -eo pid,ppid,user,cmd | grep -E "gunicorn|wsgi" | grep -v grep

echo "=== LISTEN PORTS 8000/8001 ==="
ss -ltn | awk 'NR==1 || /:8000|:8001/'

echo "=== WHO OWNS THE USB SERIAL ==="
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
for p in $(pgrep -f "wsgi:app"); do
  echo "--- pid $p ---"
  ls -l /proc/$p/cwd 2>/dev/null
  ls -l /proc/$p/fd 2>/dev/null | grep -E "ttyUSB|ttyACM" || true
done

echo "=== Auto-Feeding-System LAYOUT ==="
ls -la ~/Auto-Feeding-System/services/valve_relay_service.py ~/Auto-Feeding-System/data/ ~/Auto-Feeding-System/wsgi.py ~/Auto-Feeding-System/venv/bin/gunicorn 2>&1
echo "--- AFS settings.json usb_roles ---"
python3 -c "import json,pathlib; p=pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'; print(json.dumps(json.loads(p.read_text()).get('usb_roles',{}),indent=2))" 2>&1

echo "=== ~/garden settings.json usb_roles ==="
python3 -c "import json,pathlib; p=pathlib.Path.home()/'garden/data/settings.json'; print(json.dumps(json.loads(p.read_text()).get('usb_roles',{}),indent=2))" 2>&1

echo "=== DONE ==="
