#!/bin/bash
# Migrate every Pi to use .local mDNS names in settings.
# - Installs avahi-utils if missing.
# - Backs up settings.json (and AFS settings.json on fill.dr) once to .bak_mdns.
# - Replaces *.dr names and known Pi IPs with *.local equivalents in the JSON.
# - Restarts garden.service (and feeding.service on fill.dr).
# Idempotent: safe to re-run.
set +e

echo "=== HOSTNAME: $(hostname) ==="

echo "--- avahi-utils ---"
if ! command -v avahi-resolve-host-name >/dev/null 2>&1; then
  echo "  installing avahi-utils..."
  echo password | sudo -S apt-get install -y avahi-utils >/tmp/apt.log 2>&1
  command -v avahi-resolve-host-name >/dev/null 2>&1 && echo "  OK" || { echo "  FAILED to install"; tail -5 /tmp/apt.log; }
else
  echo "  already installed"
fi

migrate_settings() {
  local SETTINGS="$1"
  local LABEL="$2"
  if [ ! -f "$SETTINGS" ]; then
    echo "  [$LABEL] no $SETTINGS, skipping"
    return
  fi

  [ -f "$SETTINGS.bak_mdns" ] || cp -p "$SETTINGS" "$SETTINGS.bak_mdns"

  python3 - "$SETTINGS" "$LABEL" <<'PY'
import json, sys, re

path, label = sys.argv[1], sys.argv[2]
with open(path) as f:
    s = json.load(f)

# (case-insensitive name) -> canonical .local form. IP -> .local mappings too.
mapping = {
    'fill.dr':       'Fill.local',
    'drain.dr':      'Drain.local',
    'zone1.dr':      'Zone1.local',
    'zone2.dr':      'Zone2.local',
    'zone3.dr':      'Zone3.local',
    'zone5.dr':      'Zone5.local',
    'zone6.dr':      'Zone6.local',
    'zone7.dr':      'Zone7.local',
    'veg.dr':        'Veg.local',
    '172.16.1.239':  'Fill.local',
    '172.16.1.30':   'Drain.local',
    '172.16.1.178':  'Zone1.local',
    '172.16.1.22':   'Zone2.local',
    '172.16.1.23':   'Zone3.local',
    '172.16.1.25':   'Zone5.local',
    '172.16.1.26':   'Zone6.local',
    '172.16.1.27':   'Zone7.local',
    '172.16.1.28':   'Veg.local',
}
# Build lowercase lookup
lookup = {k.lower(): v for k, v in mapping.items()}

def remap(val):
    if not isinstance(val, str):
        return val, False
    new = lookup.get(val.lower(), val)
    return new, new != val

changes = []
def walk(obj, parent_key=None, path_str="$"):
    if isinstance(obj, dict):
        return {k: walk(v, k, f"{path_str}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v, parent_key, f"{path_str}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, str):
        # Only replace if the parent key looks like a hostname/ip field, OR the
        # string itself looks like a known target. Avoid touching unrelated
        # strings (Telegram URLs, etc).
        host_fields = (
            'fill_valve_ip', 'drain_valve_ip', 'water_valve_ip',
            'fill_pump_ip', 'drain_pump_ip',
            'host_ip', 'ip', 'feed_pump_ip',
        )
        should_remap = (parent_key in host_fields) or (obj.lower() in lookup)
        # additional_plants list elements have parent_key='additional_plants'
        if parent_key == 'additional_plants':
            should_remap = True
        if should_remap:
            new, ch = remap(obj)
            if ch:
                changes.append(f"  {path_str}: {obj!r} -> {new!r}")
            return new
    return obj

new = walk(s)

# Don't rewrite feed_pump.ip if it's the Shelly (172.16.1.119) which is not a Pi.
# That IP wasn't in our mapping, so it should pass through unchanged. But let's
# double-check feed_pump.ip is preserved if it was a Shelly.
shelly_ip = s.get('feed_pump', {}).get('ip')
if isinstance(shelly_ip, str) and shelly_ip not in lookup:
    if new.get('feed_pump', {}).get('ip') != shelly_ip:
        # paranoia: should never happen with our remap logic
        new.setdefault('feed_pump', {})['ip'] = shelly_ip

if changes:
    print(f"  [{label}] {len(changes)} change(s):")
    for c in changes:
        print(c)
    with open(path, 'w') as f:
        json.dump(new, f, indent=4)
else:
    print(f"  [{label}] already migrated (no changes)")
PY
}

echo "--- garden settings ---"
migrate_settings ~/garden/data/settings.json "garden"

if [ "$(hostname)" = "Fill" ]; then
  echo "--- Auto-Feeding-System settings ---"
  migrate_settings ~/Auto-Feeding-System/data/settings.json "AFS"
fi

echo "--- Restart garden.service ---"
echo password | sudo -S systemctl restart garden.service
sleep 4
systemctl is-active garden.service

if [ "$(hostname)" = "Fill" ]; then
  echo "--- Restart feeding.service ---"
  echo password | sudo -S systemctl restart feeding.service
  sleep 4
  systemctl is-active feeding.service
fi

echo "=== DONE on $(hostname) ==="
