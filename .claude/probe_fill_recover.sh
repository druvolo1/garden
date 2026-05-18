#!/bin/bash
# Check current state of fill.dr's relay. If silent, try a few command
# variants for OFF to find one the board accepts.
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
time.sleep(1.0)  # give the board a moment

def query(label, query_byte=b'\xFF', wait=0.6):
    s.reset_input_buffer()
    s.write(query_byte)
    time.sleep(wait)
    buf = b''
    deadline = time.time() + 1.5
    while time.time() < deadline:
        chunk = s.read(256)
        if not chunk: break
        buf += chunk
    text = buf.decode('ascii', errors='replace')
    print(f"  [{label}] {len(buf)}B raw={text!r}")
    return buf, text

print("=== Initial probe (board may have been left in weird state) ===")
query("probe-fresh", b'\xFF')

print("\n=== Try the query byte the BASELINE responded to: 0xFF ===")
query("probe-2", b'\xFF')

print("\n=== Send a newline (some ASCII relays wake on newline) ===")
query("probe-3-newline", b'\r\n')

print("\n=== Try 'status\\r\\n' ===")
query("probe-4-status", b'status\r\n')

print("\n=== Try '?\\r\\n' ===")
query("probe-5-q", b'?\r\n')

print("\n=== Try the ON CH1 command and see if board wakes up ===")
s.write(b'\xA0\x01\x01\xA2'); time.sleep(0.4)
query("after ON ch1", b'\xFF')

print("\n=== Try ASCII OFF variants ===")
for variant in [b'CH1OFF\r\n', b'CH1: OFF\r\n', b'C1OFF\r\n', b'R1OFF\r\n', b'1OFF\r\n', b'OFF1\r\n', b'OFF 1\r\n', b'off 1\r\n']:
    s.write(variant); time.sleep(0.3)
    _, t = query(f"after {variant!r}", b'\xFF')

print("\n=== Try the old standard binary OFF with delays/retries ===")
s.write(b'\xA0\x01\x00\xA1'); time.sleep(1.0)
query("after binary OFF (slow)", b'\xFF', wait=1.0)

print("\n=== Final: open-circuit test - any byte we send, what comes back? ===")
for b in [b'\x00', b'\xFE', b'\xFD', b'\x55']:
    s.reset_input_buffer()
    s.write(b); time.sleep(0.5)
    r = s.read(256)
    print(f"  sent {b.hex()} -> {len(r)}B {r.hex(' ')!r} {r.decode('ascii', errors='replace')!r}")

s.close()
PY

echo "=== START feeding.service ==="
echo password | sudo -S systemctl start feeding.service
sleep 2
systemctl is-active feeding.service
echo "=== DONE ==="
