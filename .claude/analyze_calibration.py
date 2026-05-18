#!/usr/bin/env python3
"""Parse afs_calibration_events.jsonl, slice into per-zone drain phases, and
report what each drain looked like."""
import json, sys, re
from pathlib import Path
from collections import defaultdict

p = Path(__file__).parent / "afs_calibration_events.jsonl"
events = []
for line in p.read_text().splitlines():
    if not line.strip():
        continue
    try:
        events.append(json.loads(line))
    except Exception:
        pass

print(f"Total events: {len(events)}")
print(f"Event kinds:")
kinds = defaultdict(int)
for e in events:
    kinds[e["kind"]] += 1
for k, c in kinds.items():
    print(f"  {k}: {c}")

# Walk feeding_feedback events to find each zone's drain start, monitoring start, and stop reason.
zones_in_order = []     # zone_ip in the order they appeared in feedback
phase_marks = []        # (t, ip, marker_text)

start_re_drain = re.compile(r"Starting drain for plant (\S+)")
stop_re_low    = re.compile(r"Drain flow dropped below .* considering bucket empty.*?for (\S+)$|considering bucket empty.*? plant (\S+)")
stop_re_sensor = re.compile(r"Empty sensor triggered.*?for (\S+),.*?completing drain")
stop_re_max    = re.compile(r"Max drain time .*? reached for (\S+)")
stop_re_initlow= re.compile(r"Initial drain flow .*? below activation threshold.*? for (\S+), considering bucket empty")
fill_start_re  = re.compile(r"Starting fill for plant (\S+)|fill.*for (\S+)", re.IGNORECASE)

for e in events:
    if e["kind"] != "feeding_feedback":
        continue
    msg = e["data"].get("message", "")
    pip = e["data"].get("plant_ip")
    phase_marks.append((e["t"], pip, msg))

# Identify drain start/end for each plant
drains = []   # list of dicts: ip, t_start, t_end, stop_reason, stop_msg
current_drain = None
for t, ip, msg in phase_marks:
    if "Starting drain for plant" in msg:
        m = start_re_drain.search(msg)
        if m:
            current_drain = {"ip": m.group(1), "t_start": t, "stop_reason": None, "stop_msg": None, "t_end": None}
            drains.append(current_drain)
    if current_drain is None:
        continue
    if "considering bucket empty" in msg:
        if "below activation threshold" in msg:
            current_drain["stop_reason"] = "initial_flow_low"
        else:
            current_drain["stop_reason"] = "flow_low"
        current_drain["stop_msg"] = msg
        current_drain["t_end"] = t
        current_drain = None
    elif "Empty sensor triggered" in msg and "completing drain" in msg:
        current_drain["stop_reason"] = "empty_sensor"
        current_drain["stop_msg"] = msg
        current_drain["t_end"] = t
        current_drain = None
    elif "Max drain time" in msg and "reached" in msg:
        current_drain["stop_reason"] = "timeout"
        current_drain["stop_msg"] = msg
        current_drain["t_end"] = t
        current_drain = None
    elif "aborting drain" in msg:
        current_drain["stop_reason"] = "abort_no_flow"
        current_drain["stop_msg"] = msg
        current_drain["t_end"] = t
        current_drain = None

print("\n=== Drain phases ===")
for d in drains:
    dur = (d["t_end"] - d["t_start"]) if d["t_end"] else None
    print(f"  {d['ip']:18s}  start={d['t_start']:.0f}  end={d['t_end']:.0f}  dur={dur:.1f}s  reason={d['stop_reason']}")

# Now bucket local_status_update events into each drain phase and look at drain_flow.
local_events = [e for e in events if e["kind"] == "local_status_update"]
local_events.sort(key=lambda e: e["t"])

print("\n=== Per-zone drain flow profiles ===")
for d in drains:
    if not d["t_end"]:
        continue
    samples = [e for e in local_events if d["t_start"] <= e["t"] <= d["t_end"]]
    flows = [s["data"].get("drain_flow") for s in samples if s["data"].get("drain_flow") is not None]
    totals = [s["data"].get("drain_total_volume") for s in samples if s["data"].get("drain_total_volume") is not None]
    if not flows:
        print(f"  {d['ip']:18s}  NO FLOW SAMPLES")
        continue
    peak = max(flows)
    end_flow = flows[-1] if flows else None
    final_total = totals[-1] if totals else None
    print(f"  {d['ip']:18s}  samples={len(samples):3d}  peak={peak:.2f}  end={end_flow:.2f}  total_drained={final_total}  reason={d['stop_reason']}")
    # Per-second-or-so timeline summarized
    if len(samples) > 1:
        # Print samples at roughly even time intervals
        n = min(len(samples), 14)
        idx = [i * (len(samples) - 1) // (n - 1) for i in range(n)]
        timeline = []
        for i in idx:
            ti = samples[i]["t"] - d["t_start"]
            fl = samples[i]["data"].get("drain_flow")
            tot = samples[i]["data"].get("drain_total_volume")
            timeline.append(f"t={ti:5.1f}s flow={fl} tot={tot}")
        for line in timeline:
            print(f"      {line}")
    # And the surrounding context — last 5 feedback msgs before the stop
    feedbacks = [(t, m) for t, ip2, m in phase_marks if d["t_start"] <= t <= d["t_end"] and (ip2 == d["ip"] or ip2 is None)]
    print(f"    --- last 6 feedback msgs ---")
    for t, m in feedbacks[-6:]:
        print(f"      +{t - d['t_start']:5.1f}s  {m}")
