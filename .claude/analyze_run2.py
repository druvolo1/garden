#!/usr/bin/env python3
"""Analyze cycle 2 (post-calibration) — drain durations, fill errors, allow flag changes."""
import json, re
from pathlib import Path
from collections import defaultdict, Counter

p = Path(__file__).parent / "afs_calibration_events_run2.jsonl"
events = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
print(f"Total events: {len(events)}")
print(f"By kind: {Counter(e['kind'] for e in events)}")

t0 = events[0]['t']
def rel(t): return f"{t-t0:7.1f}s"

# Extract drain phases
phase_marks = [(e["t"], e["data"].get("plant_ip"), e["data"].get("message", ""))
               for e in events if e["kind"] == "feeding_feedback"]

drains, current = [], None
for t, ip, msg in phase_marks:
    if "Starting drain for plant" in msg:
        m = re.search(r"Starting drain for plant (\S+)", msg)
        if m:
            current = {"ip": m.group(1), "t_start": t, "stop_reason": None, "stop_msg": None, "t_end": None}
            drains.append(current)
    if current is None: continue
    finishers = [
        ("low_initial_volume", "below threshold"),
        ("flow_low",            "considering bucket empty"),
        ("sensor",              "Empty sensor triggered"),
        ("timeout",             "Max drain time"),
        ("abort",               "aborting drain"),
    ]
    for reason, marker in finishers:
        if marker in msg:
            current["stop_reason"] = reason
            current["stop_msg"]    = msg
            current["t_end"]       = t
            current = None
            break

# Get drain phase totals
locals_ = sorted([e for e in events if e["kind"] == "local_status_update"], key=lambda x: x["t"])

print("\n=== Drain phases (cycle 2) ===")
for d in drains:
    dur = (d["t_end"] - d["t_start"]) if d["t_end"] else None
    samples = [e for e in locals_ if d["t_start"] <= e["t"] <= (d["t_end"] or d["t_start"]+1)]
    totals = [s["data"].get("drain_total_volume") for s in samples if s["data"].get("drain_total_volume") is not None]
    flows = [s["data"].get("drain_flow") for s in samples if s["data"].get("drain_flow") is not None]
    end_total = totals[-1] if totals else None
    dur_s = f"{dur:6.1f}s" if dur is not None else "  ???  "
    reason_s = d['stop_reason'] or "(no stop)"
    print(f"  {d['ip']:18s}  start=+{d['t_start']-t0:6.1f}s  dur={dur_s}  reason={reason_s:20s}  drained={end_total}")

# Fill phases
fills, current = [], None
for t, ip, msg in phase_marks:
    if "Starting fill for plant" in msg:
        m = re.search(r"Starting fill for plant (\S+)", msg)
        if m:
            current = {"ip": m.group(1), "t_start": t, "t_end": None, "result": None, "msgs": []}
            fills.append(current)
    if current is None: continue
    current["msgs"].append((t, msg))
    if "Fill complete for plant" in msg:
        current["t_end"] = t; current["result"] = "complete"; current = None
    elif "Fill valve on error" in msg or "Failed.*Fill valve" in msg:
        current["t_end"] = t; current["result"] = "fill_valve_error"; current = None
    elif "Stopped" in msg and "during filling" in msg:
        current["t_end"] = t; current["result"] = "stopped"; current = None

print("\n=== Fill phases (cycle 2) ===")
for f in fills:
    dur = (f["t_end"] - f["t_start"]) if f["t_end"] else None
    print(f"  {f['ip']:18s}  start=+{f['t_start']-t0:6.1f}s  dur={dur}  result={f['result']}")
    # Show the failure-related msgs
    for t, m in f["msgs"][:30]:
        if any(k in m for k in ["Fill valve", "Failed", "interrupted", "error", "Error"]):
            print(f"    +{t-f['t_start']:5.1f}s  {m}")

# Look at any "allow_remote_feeding" or "Not allowed" decisions
print("\n=== 'Not allowed' / allow_remote_feeding messages ===")
for t, ip, msg in phase_marks:
    if "not allowed" in msg.lower() or "allow_remote_feeding" in msg.lower():
        print(f"  +{t-t0:7.1f}s [{ip}]  {msg[:120]}")
