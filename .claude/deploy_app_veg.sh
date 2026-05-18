#!/bin/bash
set +e
NEW=/tmp/app.py.new
TGT=/home/dave/garden/app.py
if [ ! -f "$NEW" ]; then echo "  missing $NEW"; exit 1; fi
[ -f "$TGT.bak_cal_log" ] || cp -p "$TGT" "$TGT.bak_cal_log"
cp "$NEW" "$TGT"
md5sum "$TGT"
echo "in_cal refs: $(grep -c in_cal "$TGT")"
echo password | sudo -S systemctl restart garden.service
sleep 5
systemctl is-active garden.service
