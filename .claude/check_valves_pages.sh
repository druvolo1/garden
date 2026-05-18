#!/bin/bash
set +e

HOST=$(hostname)
echo "=== HOSTNAME: $HOST ==="

echo "=== gunicorn services running ==="
systemctl is-active garden.service
systemctl is-active feeding.service 2>/dev/null

echo "=== curl http://127.0.0.1:8000/valves (HTTP code + first 200 chars of body) ==="
curl -s -m 4 -o /tmp/_valves.html -w "HTTP %{http_code}, %{size_download}B, %{time_total}s\n" http://127.0.0.1:8000/valves
echo "--- body head ---"
head -c 400 /tmp/_valves.html 2>/dev/null
echo
echo "--- look for valve status in body ---"
grep -oE '(valve[_-]?[0-9]|"valve_status"|class="[^"]*valve[^"]*"|on|off)' /tmp/_valves.html | head -30

echo "=== curl http://127.0.0.1:8000/api/valve_relay/all_status (if exists) ==="
for path in /api/valve_relay/all_status /api/valves /api/valve_status /api/valves/status /valves/status /api/valve_relay/status; do
  code=$(curl -s -m 3 -o /tmp/_api.html -w "%{http_code}" http://127.0.0.1:8000$path)
  body=$(head -c 200 /tmp/_api.html 2>/dev/null)
  echo "  $path -> $code  body: $body"
done

echo "=== Endpoints in garden code that look valve-related ==="
grep -rEn "@.*route.*valve|valve.*route|/api/valve|valve_relay" ~/garden --include="*.py" 2>/dev/null | grep -v venv | head -40

echo "=== garden's settings.json usb_roles ==="
python3 -c "import json,pathlib; print(json.dumps(json.loads((pathlib.Path.home()/'garden/data/settings.json').read_text()).get('usb_roles', {}), indent=2))"

echo "=== garden's valve_labels ==="
python3 -c "import json,pathlib; print(json.dumps(json.loads((pathlib.Path.home()/'garden/data/settings.json').read_text()).get('valve_labels', {}), indent=2))"

echo "=== List USB serial by-path ==="
ls -la /dev/serial/by-path/ 2>&1
