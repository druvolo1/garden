#!/bin/bash
set +e
NEW=/tmp/dosage_service.py.new
TGT=/home/dave/garden/services/dosage_service.py
if [ ! -f "$NEW" ]; then echo "  missing $NEW"; exit 1; fi
[ -f "$TGT.bak_dose_fix" ] || cp -p "$TGT" "$TGT.bak_dose_fix"
cp "$NEW" "$TGT"
md5sum "$TGT"
grep -c "no_reading" "$TGT" | awk '{print "no_reading refs:", $1}'
echo password | sudo -S systemctl restart garden.service
sleep 5
systemctl is-active garden.service
