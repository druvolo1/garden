#!/bin/bash
echo "=== valve_labels and usb_roles in ~/garden/data/settings.json ==="
python3 - <<'PY'
import json, pathlib
s = json.loads((pathlib.Path.home()/'garden/data/settings.json').read_text())
print(json.dumps({'valve_labels': s.get('valve_labels'),
                  'usb_roles': s.get('usb_roles')}, indent=2))
PY
echo "=== debug_settings.json before change ==="
cat ~/garden/data/debug_settings.json
