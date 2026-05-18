#!/bin/bash
F=/home/dave/garden/services/ph_service.py
host=$(hostname)
md5=$(md5sum $F 2>/dev/null | awk '{print $1}')
stuck=$(grep -c PH_STUCK_THRESHOLD $F 2>/dev/null || echo 0)
active=$(systemctl is-active garden.service)
printf "%-8s  md5=%s  stuck_refs=%s  service=%s\n" "$host" "$md5" "$stuck" "$active"
