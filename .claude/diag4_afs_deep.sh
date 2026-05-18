#!/bin/bash
set +e

echo "=== AFS valve_labels in settings.json ==="
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'
s = json.loads(p.read_text())
print(json.dumps(s, indent=2))
PY

echo "=== AFS app.py (first 200 lines) ==="
head -200 ~/Auto-Feeding-System/app.py

echo "=== Files in AFS root ==="
ls -la ~/Auto-Feeding-System/ 2>&1

echo "=== Files in AFS services/ ==="
ls -la ~/Auto-Feeding-System/services/ 2>&1

echo "=== Files in AFS templates/ ==="
ls -la ~/Auto-Feeding-System/templates/ 2>&1

echo "=== Search AFS for 'output 4', 'output_4', 'output4', or anything that produces 4 outputs ==="
grep -rEn "output ?4|output_4|relay 4|valve 4|range\(1, ?[5-9]\)|range\(0, ?[4-8]\)" ~/Auto-Feeding-System --include="*.py" --include="*.html" --include="*.js" --include="*.json" 2>/dev/null | grep -v venv

echo "=== Look for status emitters / sockets ==="
grep -rEn "emit|status_namespace|socketio" ~/Auto-Feeding-System --include="*.py" 2>/dev/null | grep -v venv | head -40

echo "=== AFS git log (last 10) ==="
( cd ~/Auto-Feeding-System && git log --oneline -10 )

echo "=== AFS git status ==="
( cd ~/Auto-Feeding-System && git status )
