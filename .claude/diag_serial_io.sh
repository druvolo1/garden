#!/bin/bash
# Diagnose the serial I/O error on fill.dr's relay
set +e

echo "=== HOSTNAME ==="
hostname

echo "=== Device existence ==="
ls -l /dev/serial/by-path/ 2>&1
ls -l /dev/ttyUSB* 2>&1

echo "=== USB tree ==="
lsusb -t 2>&1 || lsusb

echo "=== Last 40 dmesg entries (USB/tty/cp210x/ch341 events) ==="
echo password | sudo -S dmesg --time-format iso 2>&1 | grep -iE "usb|tty|ftdi|ch340|ch341|cp210|input/output" | tail -40

echo "=== Can we open and write to the relay device? ==="
~/garden/venv/bin/python3 - <<'PY'
import json, pathlib, serial, sys, time
try:
    s = json.loads((pathlib.Path.home()/'garden/data/settings.json').read_text())
    dev = s['usb_roles']['valve_relay']
    print(f"device path: {dev}")
    ser = serial.Serial(dev, baudrate=9600, timeout=1)
    print(f"opened: {ser}")
    time.sleep(0.2)
    ser.write(b'\xFF')
    time.sleep(0.3)
    r = ser.read(10)
    print(f"read {len(r)} bytes: {r.hex(' ')}")
    ser.close()
    print("close OK")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
PY

echo "=== /api/error/status (does the code know it's offline?) ==="
curl -s http://127.0.0.1:8000/api/error/status 2>&1 | python3 -m json.tool 2>/dev/null | head -20
echo

echo "=== AFS (feeding.service) — is it using the same USB hub? ==="
ps -eo pid,ppid,user,cmd | grep -E "gunicorn|wsgi" | grep -v grep
for p in $(pgrep -f wsgi:app); do
  echo "-- pid $p cwd=$(readlink /proc/$p/cwd) --"
  ls -l /proc/$p/fd 2>/dev/null | grep -E "ttyUSB|ttyACM" || true
done
