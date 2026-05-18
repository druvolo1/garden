#!/bin/bash
# Filter feeding_log.jsonl down to mixing-relevant entries.
LOG=~/Auto-Feeding-System/data/logs/feeding_log.jsonl
# Pull entries mentioning feed mixing / target volume / drain complete / fill complete + last N days
# We want to find cycles where nutrient_concentration was != 0.
python3 - <<'PY'
import json, sys
from pathlib import Path
import datetime

with open(Path.home()/'Auto-Feeding-System/data/logs/feeding_log.jsonl') as f:
    lines = f.readlines()

# Group entries by date to find when cycles ran
print(f"=== feeding_log line count: {len(lines)} ===")
print(f"=== first ts: {json.loads(lines[0]).get('timestamp')} ===")
print(f"=== last ts:  {json.loads(lines[-1]).get('timestamp')} ===")

# Find entries that mention "Starting feed mixing for" or "Target feed volume" or "Starting drain" or "Fill complete"
key_phrases = ('Starting feed mixing', 'Target feed volume', 'Starting drain', 'Fill complete', 'Drain complete', 'Starting feeding sequence', 'Reset all total', 'Flow readings for plant', 'Skipped', 'aborting', 'Failed')

interesting = []
for ln in lines:
    try:
        e = json.loads(ln)
        msg = e.get('message','')
        if any(k in msg for k in key_phrases):
            interesting.append(e)
    except: pass

print(f"=== Interesting entries: {len(interesting)} ===")
# Show last 200 of them
for e in interesting[-200:]:
    ts = e.get('timestamp','')[:19]
    ip = e.get('plant_ip','')
    msg = e.get('message','')[:160]
    print(f"  {ts}  {ip:18s}  {msg}")
PY
