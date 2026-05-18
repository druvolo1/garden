#!/bin/bash
# Audit valve-related settings on this Pi. Print just the keys that matter
# for the fill/drain/zone routing.
set +e

echo "=== $(hostname) ==="

python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'garden/data/settings.json'
s = json.loads(p.read_text())

keys = [
  'fill_valve_mode','fill_valve_ip','fill_valve','fill_valve_label',
  'drain_valve_mode','drain_valve_ip','drain_valve','drain_valve_label',
  'system_name','hostname','device_id',
]
out = {k: s.get(k) for k in keys}
out['usb_roles.valve_relay'] = s.get('usb_roles', {}).get('valve_relay')
out['valve_labels']          = s.get('valve_labels')
# common 'remote_devices' or 'remote_hosts' lists if present
for extra in ('remote_devices','remote_hosts','remotes','plant_devices','additional_plants'):
  if extra in s:
    out[extra] = s[extra]
print(json.dumps(out, indent=2))
PY

echo "--- Resolve hostnames to IPs ---"
for h in fill.dr drain.dr Fill.dr Drain.dr fill.local drain.local; do
  ip=$(getent hosts "$h" 2>/dev/null | awk '{print $1}')
  [ -n "$ip" ] && echo "  $h -> $ip" || echo "  $h -> (no DNS/mDNS)"
done

echo "--- My own routable IPs ---"
hostname -I
