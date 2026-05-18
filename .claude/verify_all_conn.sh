#!/bin/bash
set +e
echo "=== $(hostname) outbound :8000 connections ==="
ss -tn 'dst :8000' 2>/dev/null | tail -n +2 | while read line; do
  peer=$(echo "$line" | awk '{print $5}')
  ip=${peer%:*}
  case "$ip" in
    172.16.1.239)  echo "  -> Fill.local   ($peer)" ;;
    172.16.1.30)   echo "  -> Drain.local  ($peer)" ;;
    172.16.1.178)  echo "  -> Zone1.local  ($peer)" ;;
    172.16.1.22)   echo "  -> Zone2.local  ($peer)" ;;
    172.16.1.23)   echo "  -> Zone3.local  ($peer)" ;;
    172.16.1.25)   echo "  -> Zone5.local  ($peer)" ;;
    172.16.1.26)   echo "  -> Zone6.local  ($peer)" ;;
    172.16.1.27)   echo "  -> Zone7.local  ($peer)" ;;
    172.16.1.28)   echo "  -> Veg.local    ($peer)" ;;
    *)             echo "  -> ???          ($peer)" ;;
  esac
done

# Also AFS on fill.dr port 8001 → its plant_clients
if [ "$(hostname)" = "Fill" ]; then
  echo "=== AFS (fill.dr:8001) plant connections ==="
  # AFS connects out on its own; check outbound :8000 was already covered above
  # Just list AFS gunicorn's outbound :8000 too (it'll be in the same list)
  echo "(AFS connections are :8000 outbound, shown above mixed with garden)"
fi
