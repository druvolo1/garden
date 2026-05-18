#!/bin/bash
# Install app.py + api/settings.py, restart garden.service.
set +e
for pair in "/tmp/app.py.new:/home/dave/garden/app.py" \
            "/tmp/settings.py.new:/home/dave/garden/api/settings.py"; do
  src=${pair%%:*}
  tgt=${pair#*:}
  if [ ! -f "$src" ]; then
    echo "  skip $tgt (no $src)"
    continue
  fi
  [ -f "$tgt.bak_v089" ] || cp -p "$tgt" "$tgt.bak_v089"
  cp "$src" "$tgt"
  echo "  installed $tgt  md5=$(md5sum "$tgt" | awk '{print $1}')"
done
grep -E "CURRENT_VERSION\s*=" /home/dave/garden/api/settings.py | head -1
echo password | sudo -S systemctl restart garden.service
sleep 5
systemctl is-active garden.service
