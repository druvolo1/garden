#!/bin/bash
# Push the updated feeding_service.py and apply the new drain_flow_settings.
# Backs up to .bak_drain_cal on first run.
set +e
NEW=/tmp/feeding_service.py.new
TGT=~/Auto-Feeding-System/services/feeding_service.py

echo "=== HOSTNAME: $(hostname) ==="

if [ ! -f "$NEW" ]; then
  echo "  no $NEW pushed, skipping code update"
else
  [ -f "$TGT.bak_drain_cal" ] || cp -p "$TGT" "$TGT.bak_drain_cal"
  if cmp -s "$NEW" "$TGT"; then
    echo "  feeding_service.py already up-to-date"
  else
    cp "$NEW" "$TGT"
    echo "  installed feeding_service.py; md5: $(md5sum "$TGT" | awk '{print $1}')"
  fi
  grep -q 'min_initial_volume' "$TGT" && echo '  has accumulated-volume check: yes' || echo '  has accumulated-volume check: MISSING'
fi

echo "--- Update drain_flow_settings (also backs up first time) ---"
SETT=~/Auto-Feeding-System/data/settings.json
[ -f "$SETT.bak_drain_cal" ] || cp -p "$SETT" "$SETT.bak_drain_cal"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'
s = json.loads(p.read_text())
old = s.get('drain_flow_settings', {})
new = {
    "activation_flow_rate": 0.1,
    "min_flow_rate":        0.1,
    "activation_delay":      30,
    "min_flow_check_delay":  60,
    "max_drain_time":       600,
}
print(f"  OLD drain_flow_settings: {json.dumps(old)}")
s['drain_flow_settings'] = new
print(f"  NEW drain_flow_settings: {json.dumps(new)}")
p.write_text(json.dumps(s, indent=4))
PY

echo "--- Restart feeding.service ---"
echo password | sudo -S systemctl restart feeding.service
sleep 5
systemctl is-active feeding.service
echo "=== DONE on $(hostname) ==="
