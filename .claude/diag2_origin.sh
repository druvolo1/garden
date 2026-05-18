#!/bin/bash
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== systemctl list ALL gunicorn services (enabled or active) ==="
for unit in $(systemctl list-unit-files --type=service --no-legend --no-pager | awk '{print $1}'); do
  ex=$(systemctl cat "$unit" 2>/dev/null | grep -E "^ExecStart=" | head -1)
  if echo "$ex" | grep -qiE "gunicorn|wsgi"; then
    state=$(systemctl is-active "$unit")
    enabled=$(systemctl is-enabled "$unit" 2>/dev/null)
    echo "$unit | active=$state | enabled=$enabled"
    echo "  $ex"
  fi
done

echo "=== Listen ports ==="
ss -ltn | awk 'NR==1 || /LISTEN/' | head -20

echo "=== git origin/branch in ~/garden ==="
( cd ~/garden 2>/dev/null && echo "remote:" && git remote -v 2>&1 && echo "branch:" && git rev-parse --abbrev-ref HEAD 2>&1 && echo "head:" && git log -1 --oneline 2>&1 ) || echo "no ~/garden git"

echo "=== git origin/branch in ~/Auto-Feeding-System ==="
( cd ~/Auto-Feeding-System 2>/dev/null && echo "remote:" && git remote -v 2>&1 && echo "branch:" && git rev-parse --abbrev-ref HEAD 2>&1 && echo "head:" && git log -1 --oneline 2>&1 ) || echo "no ~/AFS git"

echo "=== Other interesting dirs in ~ ==="
ls -1 ~ 2>/dev/null

echo "=== AFS HTTP /api/valve_relay/status (port 8001) ==="
curl -s -m 3 http://127.0.0.1:8001/api/valve_relay/status 2>&1 || echo "no response"
echo
echo "=== AFS HTTP / (port 8001 root) ==="
curl -s -m 3 http://127.0.0.1:8001/ 2>&1 | head -40

echo "=== AFS routes (grep app.route in AFS code) ==="
grep -rE "app.route|@app\." ~/Auto-Feeding-System --include="*.py" 2>/dev/null | head -30

echo "=== garden HTTP if anything on 8000 ==="
ss -ltn | grep ":8000" && curl -s -m 3 http://127.0.0.1:8000/ 2>&1 | head -10

echo "=== DONE ==="
