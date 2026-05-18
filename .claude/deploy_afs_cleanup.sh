#!/bin/bash
# Apply all the queued AFS edits + flow_check_delay setting change.
set +e

PI_HOME=/home/dave
BASE=$PI_HOME/Auto-Feeding-System

# Files we pushed
for src_dest in \
  "/tmp/feeding_service.py.new:$BASE/services/feeding_service.py" \
  "/tmp/feed_mixing_service.py.new:$BASE/services/feed_mixing_service.py" \
  "/tmp/feed_pump_service.py.new:$BASE/services/feed_pump_service.py" \
  "/tmp/settings.py.new:$BASE/api/settings.py" \
  "/tmp/settings.html.new:$BASE/templates/settings.html" \
; do
  src=${src_dest%%:*}
  tgt=${src_dest#*:}
  if [ -f "$src" ]; then
    [ -f "$tgt.bak_msg_cal" ] || cp -p "$tgt" "$tgt.bak_msg_cal"
    if cmp -s "$src" "$tgt"; then
      echo "  $tgt: already up-to-date"
    else
      cp "$src" "$tgt"
      echo "  $tgt: installed  md5=$(md5sum "$tgt" | awk '{print $1}')"
    fi
  fi
done

echo "--- Set min_flow_check_delay = 20 ---"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'Auto-Feeding-System/data/settings.json'
s = json.loads(p.read_text())
d = s.get('drain_flow_settings', {})
old = d.get('min_flow_check_delay')
d['min_flow_check_delay'] = 20
s['drain_flow_settings'] = d
p.write_text(json.dumps(s, indent=4))
print(f"  min_flow_check_delay: {old} -> 20")
print(f"  current drain_flow_settings: {json.dumps(d)}")
PY

echo "--- Restart feeding.service ---"
echo password | sudo -S systemctl restart feeding.service
sleep 5
systemctl is-active feeding.service
echo "=== DONE ==="
