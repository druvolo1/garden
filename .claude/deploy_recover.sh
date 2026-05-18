#!/bin/bash
# Apply the auto-recovery edits by replacing ~/garden/services/valve_relay_service.py
# from a pushed file at /tmp/valve_relay_service.py.new, then restart garden.service.
set +e

NEW=/tmp/valve_relay_service.py.new
TGT=~/garden/services/valve_relay_service.py

echo "=== HOSTNAME: $(hostname) ==="

if [ ! -f "$NEW" ]; then
  echo "  no $NEW pushed, skipping"
  exit 0
fi
if [ ! -f "$TGT" ]; then
  echo "  $TGT not present, skipping"
  exit 0
fi

# Make a backup once per session
[ -f "$TGT.bak" ] || cp -p "$TGT" "$TGT.bak"

# Compare and apply
if cmp -s "$NEW" "$TGT"; then
  echo "  already up-to-date"
else
  cp "$NEW" "$TGT"
  echo "  installed new $TGT"
  echo "    md5: $(md5sum "$TGT" | awk '{print $1}')"
fi

# Verify both recovery helpers are present
grep -q '_reset_serial_connection' "$TGT" && echo "  _reset_serial_connection: yes" || echo "  _reset_serial_connection: MISSING"
grep -q '_flush_all_pending'        "$TGT" && echo "  _flush_all_pending:        yes" || echo "  _flush_all_pending:        MISSING"

echo "--- Restart garden.service ---"
echo password | sudo -S systemctl restart garden.service
sleep 3
systemctl is-active garden.service
ss -ltn | awk '$4 ~ /:8000$/ {print "  port 8000 listening:", $0}'
echo "=== DONE on $(hostname) ==="
