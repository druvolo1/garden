#!/bin/bash
set +e
NEW=/tmp/ph_service.py.new
TGT=/home/dave/garden/services/ph_service.py
if [ ! -f "$NEW" ]; then
  echo "  missing $NEW"
  exit 1
fi
[ -f "$TGT.bak_ph_fix" ] || cp -p "$TGT" "$TGT.bak_ph_fix"
cp "$NEW" "$TGT"
echo "installed:"
md5sum "$TGT"
echo "PH_STUCK_THRESHOLD references: $(grep -c PH_STUCK_THRESHOLD "$TGT")"
echo "_reading_status references:    $(grep -c _reading_status "$TGT")"
echo "--- restart garden.service ---"
echo password | sudo -S systemctl restart garden.service
sleep 5
systemctl is-active garden.service
