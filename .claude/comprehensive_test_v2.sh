#!/bin/bash
# Run on fill.dr. Look up AFS plants by their fill_valve_label, then toggle
# valves at fill.dr/drain.dr and verify AFS reflects each change.
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

"$PY" - <<'PY'
import socketio, requests, time

# Zones with the on-master valve_id and the expected fill/drain labels
zones = [
    ("Zone 1 Fill", "Zone 1 Drain", 1, 1),
    ("Zone 2 Fill", "Zone 2 Drain", 2, 2),
    ("Zone 3 Fill", "Zone 3 Drain", 3, 3),
    ("Zone 5 Fill", "Zone 5 Drain", 5, 5),
    ("Zone 6 Fill", "Zone 6 Drain", 6, 6),
    ("Zone 7 Fill", "Zone 7 Drain", 7, 7),
]

# Keyed by fill_valve_label -> {fill, drain, last_update}
plants_by_label = {}

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("plants_update", namespace="/status")
def on_pu(data):
    for p in (data.get("plants") or []):
        vi  = p.get("valve_info") or {}
        fl  = vi.get("fill_valve_label")
        dl  = vi.get("drain_valve_label")
        if not fl:
            continue
        vr  = vi.get("valve_relays") or {}
        plants_by_label[fl] = {
            "fill":      (vr.get(fl) or {}).get("status"),
            "drain":     (vr.get(dl) or {}).get("status"),
            "ip":        p.get("ip"),
            "online":    p.get("is_online"),
        }

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
print("Connected to AFS, waiting 4s for initial plants_update...")
time.sleep(4)
print(f"AFS knows plants by label: {sorted(plants_by_label.keys())}\n")

def wait_state(fill_label, *, want_fill=None, want_drain=None, max_wait=4.0):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        st = plants_by_label.get(fill_label, {})
        ok_f = (want_fill  is None) or (st.get("fill")  == want_fill)
        ok_d = (want_drain is None) or (st.get("drain") == want_drain)
        if ok_f and ok_d:
            return True, st
        time.sleep(0.25)
    return False, plants_by_label.get(fill_label, {})

def post(url):
    try:
        r = requests.post(url, timeout=4)
        return r.json().get("status") == "success"
    except Exception as e:
        print(f"  POST {url} FAILED: {e}")
        return False

results = []
for fill_label, drain_label, fill_id, drain_id in zones:
    print(f"--- {fill_label}  ({fill_label[5]}-fill, drain id {drain_id}) ---")
    if fill_label not in plants_by_label:
        print(f"  AFS does not know this plant, skipping")
        results.append((fill_label, "SKIP - not in AFS"))
        continue

    fails = []

    # FILL ON
    if not post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/on"):
        fails.append("fill ON POST failed")
    else:
        ok, st = wait_state(fill_label, want_fill="on")
        print(f"  fill ON   -> AFS fill={st.get('fill'):3s}  {'OK' if ok else 'FAIL'}")
        if not ok: fails.append(f"fill ON expected on, got {st.get('fill')}")
    time.sleep(5)

    # FILL OFF
    post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/off")
    ok, st = wait_state(fill_label, want_fill="off")
    print(f"  fill OFF  -> AFS fill={st.get('fill'):3s}  {'OK' if ok else 'FAIL'}")
    if not ok: fails.append(f"fill OFF expected off, got {st.get('fill')}")
    time.sleep(5)

    # DRAIN ON
    if not post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/on"):
        fails.append("drain ON POST failed")
    else:
        ok, st = wait_state(fill_label, want_drain="on")
        print(f"  drain ON  -> AFS drain={st.get('drain'):3s} {'OK' if ok else 'FAIL'}")
        if not ok: fails.append(f"drain ON expected on, got {st.get('drain')}")
    time.sleep(5)

    # DRAIN OFF
    post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/off")
    ok, st = wait_state(fill_label, want_drain="off")
    print(f"  drain OFF -> AFS drain={st.get('drain'):3s} {'OK' if ok else 'FAIL'}")
    if not ok: fails.append(f"drain OFF expected off, got {st.get('drain')}")
    time.sleep(5)

    results.append((fill_label, "ALL 4 OK" if not fails else " / ".join(fails)))

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
for k, v in results:
    print(f"  {k}: {v}")
sio.disconnect()
PY
