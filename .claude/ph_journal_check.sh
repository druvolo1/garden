#!/bin/bash
# On a Pi: dump pH-relevant journal events since the rollout (~25 min back).
set +e
host=$(hostname)
echo "===== $host ====="
journalctl -u garden.service --since '25 min ago' --no-pager 2>/dev/null | \
  grep -iE "stuck_reading|persistent_unstable|Unrealistic pH|unrealistic_reading|No pH reading|Issue cleared|out_of_range|PH_USB_OFFLINE|Cannot open.*ph|Error.*ph|Accepted new pH" | \
  awk '{
    # count by type, print first/last/count
  }' || true
echo "  -- counts since rollout --"
journalctl -u garden.service --since '25 min ago' --no-pager 2>/dev/null | grep -iE "stuck_reading|persistent_unstable|unrealistic_reading|No pH reading|out_of_range" | sort | uniq -c | sort -rn | head -10
echo
