#!/bin/bash
# Run on fill.dr: actively command CH1, CH2, CH3, CH4 ON one at a time (with
# user's authorization — water off, drain pump unpowered), watch the status
# response after each, then turn everything off and confirm.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== STOP feeding.service ==="
echo password | sudo -S systemctl stop feeding.service
sleep 1
systemctl is-active feeding.service

~/Auto-Feeding-System/venv/bin/python3 - <<'PY'
import json, pathlib, serial, time, re

settings = json.loads((pathlib.Path.home()/'Auto-Feeding-System/data/settings.json').read_text())
dev = settings['usb_roles']['valve_relay']
s = serial.Serial(dev, baudrate=9600, timeout=1.5)
time.sleep(0.3)

def status(label):
    s.reset_input_buffer()
    s.write(b'\xFF')
    time.sleep(0.5)
    buf = b''
    deadline = time.time() + 1.0
    while time.time() < deadline:
        chunk = s.read(256)
        if not chunk: break
        buf += chunk
    text = buf.decode('ascii', errors='replace')
    matches = re.findall(r'(CH\d+):\s*(ON|OFF)', text)
    print(f"  [{label}] {len(buf)}B: {matches}  raw={text!r}")
    return matches

def on(ch):
    cmd = bytes([0xA0, ch, 0x01, 0xA0 + ch + 1])
    s.write(cmd)
    time.sleep(0.4)

def off(ch):
    cmd = bytes([0xA0, ch, 0x00, 0xA0 + ch])
    s.write(cmd)
    time.sleep(0.4)

status("BASELINE")

for ch in [1, 2, 3, 4]:
    print(f"\n--- Turning ON channel {ch} ---")
    on(ch)
    status(f"after ON ch{ch}")
    print(f"--- Turning OFF channel {ch} ---")
    off(ch)
    status(f"after OFF ch{ch}")

print("\n--- Final: all OFF burst ---")
for ch in range(1, 9):
    off(ch)
status("FINAL all-off")

s.close()
PY

echo "=== START feeding.service ==="
echo password | sudo -S systemctl start feeding.service
sleep 2
systemctl is-active feeding.service
echo "=== DONE ==="
