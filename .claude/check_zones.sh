#!/bin/bash
# Check each zone Pi's view of valve feedback from a host that can reach them.
# This runs ON one of the Pis (which is on the same LAN as the zones).
set +e

for z in zone1 zone2 zone3 zone5 zone6 zone7; do
  echo "================================================"
  echo "=== $z.dr ==="
  echo "================================================"
  # 1) is the host even up?
  if ! getent hosts $z.dr > /dev/null 2>&1; then
    if ! ping -c 1 -W 1 $z.dr > /dev/null 2>&1; then
      echo "  $z.dr unreachable"
      continue
    fi
  fi

  # 2) HTTP /api/valve_relay/all_status
  echo "--- /api/valve_relay/all_status ---"
  curl -s -m 4 -o /tmp/_z.json -w "HTTP %{http_code} %{size_download}B %{time_total}s\n" http://$z.dr:8000/api/valve_relay/all_status
  python3 -m json.tool /tmp/_z.json 2>/dev/null | head -30

  # 3) settings: what valves are assigned to this zone? (need to ssh, skip
  #    unless we want to.) Instead, infer from the API output above.

  # 4) Quick check what fill_valve/drain_valve labels they see via /api
  echo "--- /api/settings (fill/drain mode and assignment) ---"
  curl -s -m 4 http://$z.dr:8000/api/settings 2>/dev/null | python3 -c "import json,sys; s=json.load(sys.stdin); print(json.dumps({k:s.get(k) for k in ['fill_valve_mode','fill_valve_ip','fill_valve','fill_valve_label','drain_valve_mode','drain_valve_ip','drain_valve','drain_valve_label']}, indent=2))" 2>/dev/null || echo "  (could not parse settings)"
done
echo "================================================"
echo "DONE"
