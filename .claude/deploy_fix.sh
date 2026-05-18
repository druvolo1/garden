#!/bin/bash
# Apply the emit_valve_update event-name fix to ~/garden/status_namespace.py
# and restart garden.service. Idempotent.
set +e

FILE=~/garden/status_namespace.py
OLD='_socketio.emit("status_update", valve_update_payload'
NEW='_socketio.emit("valve_update", valve_update_payload'

echo "=== HOSTNAME: $(hostname) ==="

if [ ! -f "$FILE" ]; then
  echo "  $FILE not found, skipping"
  exit 0
fi

# Show the current line before
echo "--- BEFORE ---"
grep -n 'valve_update_payload' "$FILE" | head -3

if grep -q "$NEW" "$FILE"; then
  echo "  already patched; nothing to do"
else
  # Use a safe replacement that disambiguates by the payload var name
  sed -i "s|$OLD|$NEW|" "$FILE"
  echo "--- AFTER ---"
  grep -n 'valve_update_payload' "$FILE" | head -3
fi

echo "--- Restart garden.service ---"
echo password | sudo -S systemctl restart garden.service
sleep 3
systemctl is-active garden.service
echo "  port 8000 listening?"
ss -ltn | awk '$4 ~ /:8000$/ {print "  yes:", $0}'

echo "=== DONE on $(hostname) ==="
