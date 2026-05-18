#!/bin/bash
# Run on fill.dr: stop feeding.service briefly, open the relay serial
# directly, query status, send all-off, re-query status, restart service.
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== STOP feeding.service ==="
echo password | sudo -S systemctl stop feeding.service
sleep 1
systemctl is-active feeding.service
pgrep -af gunicorn || echo "(no gunicorn running)"

echo "=== PROBE relay directly ==="
~/Auto-Feeding-System/venv/bin/python3 - <<'PY'
import json, pathlib, serial, time, sys

settings = json.loads((pathlib.Path.home()/'Auto-Feeding-System/data/settings.json').read_text())
dev = settings['usb_roles']['valve_relay']
print(f"Opening serial: {dev}")

s = serial.Serial(dev, baudrate=9600, timeout=1)
time.sleep(0.2)

def dump(label):
    s.reset_input_buffer()
    s.write(b'\xFF')
    time.sleep(0.3)
    resp = s.read(16)
    print(f"{label}: len={len(resp)} hex={resp.hex(' ')!r}")
    return resp

before = dump("BEFORE-all-off")

print("Sending OFF to all 8 channels...")
OFF = {
    1: b'\xA0\x01\x00\xA1', 2: b'\xA0\x02\x00\xA2', 3: b'\xA0\x03\x00\xA3',
    4: b'\xA0\x04\x00\xA4', 5: b'\xA0\x05\x00\xA5', 6: b'\xA0\x06\x00\xA6',
    7: b'\xA0\x07\x00\xA7', 8: b'\xA0\x08\x00\xA8',
}
for ch, cmd in OFF.items():
    s.write(cmd)
    time.sleep(0.05)
    print(f"  wrote OFF ch{ch}: {cmd.hex(' ')}")

time.sleep(0.5)
after = dump("AFTER-forced-off")

# Decode interpretation (per old assumption: bytes[0..7] = chans 1..8, 0x01=on)
def decode(label, resp):
    if len(resp) < 8:
        print(f"  {label} too short to decode")
        return
    states = {i+1: ('on' if resp[i] == 1 else ('off' if resp[i] == 0 else f'??(0x{resp[i]:02x})'))
              for i in range(8)}
    print(f"  {label} decoded: {states}")

decode("BEFORE", before)
decode("AFTER", after)

s.close()
PY

echo "=== START feeding.service ==="
echo password | sudo -S systemctl start feeding.service
sleep 2
systemctl is-active feeding.service
echo "=== DONE ==="
