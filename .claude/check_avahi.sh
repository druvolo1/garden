#!/bin/bash
set +e
echo "=== HOSTNAME: $(hostname) ==="
which avahi-resolve-host-name || echo "  avahi-resolve-host-name NOT installed"
which avahi-browse              >/dev/null && echo "  avahi-browse present" || echo "  avahi-browse NOT present"
systemctl is-active avahi-daemon
echo "--- resolves of all 9 .local names ---"
for n in Fill.local Drain.local Zone1.local Zone2.local Zone3.local Zone5.local Zone6.local Zone7.local Veg.local; do
  if which avahi-resolve-host-name >/dev/null 2>&1; then
    r=$(timeout 3 avahi-resolve-host-name -4 "$n" 2>&1)
  else
    r=$(timeout 3 getent hosts "$n" 2>&1)
  fi
  echo "  $n -> ${r:-(no result)}"
done
