#!/bin/bash
# Re-probe fill.dr: capture the FULL ASCII status reply (read 256 bytes),
# show before/after the standard binary OFF sequence, and also probe with a
# couple of common ASCII command variants to see if the board responds.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== STOP feeding.service ==="
echo password | sudo -S systemctl stop feeding.service
sleep 1
systemctl is-active feeding.service

echo "=== PROBE relay (long read, multiple variants) ==="
~/Auto-Feeding-System/venv/bin/python3 - <<'PY'
import json, pathlib, serial, time

settings = json.loads((pathlib.Path.home()/'Auto-Feeding-System/data/settings.json').read_text())
dev = settings['usb_roles']['valve_relay']
print(f"Opening: {dev}")
s = serial.Serial(dev, baudrate=9600, timeout=1.5)
time.sleep(0.3)

def read_all(label):
    s.reset_input_buffer()
    # send the standard query
    s.write(b'\xFF')
    time.sleep(0.5)
    buf = b''
    deadline = time.time() + 1.5
    while time.time() < deadline:
        chunk = s.read(256)
        if not chunk:
            break
        buf += chunk
    print(f"--- {label} ---")
    print(f"  hex ({len(buf)} bytes): {buf.hex(' ')}")
    try:
        text = buf.decode('ascii', errors='replace').replace('\r','\\r').replace('\n','\\n\n      ')
        print(f"  ascii:\n      {text}")
    except Exception as e:
        print(f"  decode err: {e}")
    return buf

# Snapshot 1: current state
b1 = read_all("STATE 1 (before)")

print("\n=== Trying BINARY OFF (current AFS format) for all 8 channels ===")
for ch in range(1, 9):
    cmd = bytes([0xA0, ch, 0x00, 0xA0 + ch])
    s.write(cmd)
    time.sleep(0.05)
    print(f"  wrote: {cmd.hex(' ')}  (binary OFF ch{ch})")
time.sleep(0.5)
b2 = read_all("STATE 2 (after binary OFF burst)")

print("\n=== Trying ASCII commands (common variants) ===")
for cmd_str in ['CH4OFF\r\n', 'R04OFF\r\n', 'all off\r\n', 'off04\r\n', 'channel4off\r\n']:
    s.write(cmd_str.encode())
    time.sleep(0.15)
    extra = s.read(64)
    print(f"  sent {cmd_str!r} -> echo: {extra.hex(' ') if extra else '(no echo)'} ascii={extra.decode('ascii', errors='replace')!r}")
b3 = read_all("STATE 3 (after ASCII attempts)")

print("\n=== Sending nothing, just a fresh 0xFF query ===")
b4 = read_all("STATE 4 (fresh query)")

s.close()

print("\n=== INTERPRETATION ===")
import re
def interp(buf, label):
    text = buf.decode('ascii', errors='ignore')
    matches = re.findall(r'(CH\d+):\s*(ON|OFF)', text)
    print(f"  {label}: {matches if matches else '(no CHx: ON/OFF lines parsed)'}")
for label, buf in [("STATE 1", b1), ("STATE 2", b2), ("STATE 3", b3), ("STATE 4", b4)]:
    interp(buf, label)
PY

echo "=== START feeding.service ==="
echo password | sudo -S systemctl start feeding.service
sleep 2
systemctl is-active feeding.service
echo "=== DONE ==="
