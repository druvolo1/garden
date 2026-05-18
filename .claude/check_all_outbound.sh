#!/bin/bash
set +e
echo "=== $(hostname) outbound :8000 ==="
ss -tn 'dst :8000' 2>/dev/null | grep -v 'State' | while read line; do
  peer=$(echo "$line" | awk '{print $5}')
  case "$peer" in
    172.16.1.239:*) echo "  fill.dr  ($peer)" ;;
    172.16.1.30:*)  echo "  drain.dr ($peer)" ;;
    *)              echo "  other    ($peer)" ;;
  esac
done
