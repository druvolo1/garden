#!/bin/bash
# Install the new status_namespace.py from /tmp/status_namespace.py.new
# and restart garden.service.
set +e

NEW=/tmp/status_namespace.py.new
TGT=~/garden/status_namespace.py

echo "=== HOSTNAME: $(hostname) ==="
if [ ! -f "$NEW" ] || [ ! -f "$TGT" ]; then
  echo "  missing file"
  exit 0
fi

[ -f "$TGT.bak2" ] || cp -p "$TGT" "$TGT.bak2"

if cmp -s "$NEW" "$TGT"; then
  echo "  already up-to-date"
else
  cp "$NEW" "$TGT"
  echo "  installed; md5: $(md5sum "$TGT" | awk '{print $1}')"
fi

# Spot-check both fixes are present
grep -q 'namespaces=\["/status"\]' "$TGT"           && echo '  namespaces=["/status"]: yes' || echo '  namespaces=["/status"]: MISSING'
grep -q '_socketio.emit("valve_update"' "$TGT"      && echo '  emit("valve_update"):    yes' || echo '  emit("valve_update"):    MISSING'

echo "--- Restart garden.service ---"
echo password | sudo -S systemctl restart garden.service
sleep 3
systemctl is-active garden.service
ss -ltn | awk '$4 ~ /:8000$/ {print "  port 8000:", $0}'
echo "=== DONE on $(hostname) ==="
