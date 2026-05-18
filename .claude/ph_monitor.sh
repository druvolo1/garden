#!/bin/bash
# Run on any Pi. Polls /api/ph/latest on each of the 7 zones with probes for
# DUR_S seconds, samples every SAMPLE_S seconds. Reports per-zone summary.
set +e
DUR_S=${1:-180}   # default 3 minutes
SAMPLE_S=${2:-5}  # poll every 5 seconds

PY=python3
ZONES="Zone1.local Zone2.local Zone3.local Zone5.local Zone6.local Zone7.local Veg.local"

OUT=/tmp/ph_samples.csv
echo "ts,zone,ph,reading_status,stuck_status" > $OUT

end=$(($(date +%s) + DUR_S))
count=0
while [ $(date +%s) -lt $end ]; do
  for z in $ZONES; do
    body=$(curl -s -m 3 "http://$z:8000/api/ph/latest" 2>/dev/null)
    ph=$(echo "$body" | $PY -c "import json,sys; d=json.load(sys.stdin); print(d.get('ph','NA'))" 2>/dev/null || echo "ERR")
    # status_namespace exposes status via /api/error/status if it has one, but
    # let's just sample pH for now. Status events are visible in journals.
    echo "$(date +%s),$z,$ph,," >> $OUT
  done
  count=$((count+1))
  sleep $SAMPLE_S
done

echo
echo "=== Sampled $count rounds, $(wc -l < $OUT) data points ==="
echo
$PY - <<PY
import csv, statistics
from collections import defaultdict

data = defaultdict(list)
with open("$OUT") as f:
    next(f)
    for row in csv.reader(f):
        ts, zone, ph = row[0], row[1], row[2]
        try:
            data[zone].append(float(ph))
        except: pass

print(f"{'Zone':<14s}  {'samples':>7s}  {'min':>6s}  {'max':>6s}  {'mean':>6s}  {'stdev':>6s}  {'unique':>6s}  {'note':<20s}")
print("-" * 90)
for zone in sorted(data.keys()):
    vals = data[zone]
    if not vals:
        print(f"{zone:<14s}  {'0':>7s}  (no readings)")
        continue
    mn, mx = min(vals), max(vals)
    mean = sum(vals)/len(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    unique = len(set(round(v,3) for v in vals))
    note = ""
    if unique == 1:
        note = "STUCK?"
    elif sd < 0.005:
        note = "very stable"
    elif sd > 0.5:
        note = "VERY NOISY"
    elif sd > 0.2:
        note = "noisy"
    print(f"{zone:<14s}  {len(vals):>7d}  {mn:>6.3f}  {mx:>6.3f}  {mean:>6.3f}  {sd:>6.3f}  {unique:>6d}  {note:<20s}")
PY
