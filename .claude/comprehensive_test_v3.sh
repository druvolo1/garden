#!/bin/bash
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

"$PY" - <<'PY'
import socketio, requests, time

zones = [
    ("Zone 1 Fill", "Zone 1 Drain", 1, 1),
    ("Zone 2 Fill", "Zone 2 Drain", 2, 2),
    ("Zone 3 Fill", "Zone 3 Drain", 3, 3),
    ("Zone 5 Fill", "Zone 5 Drain", 5, 5),
    ("Zone 6 Fill", "Zone 6 Drain", 6, 6),
    ("Zone 7 Fill", "Zone 7 Drain", 7, 7),
]

plants_by_label = {}
update_count = [0]

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("plants_update", namespace="/status")
def on_pu(data):
    update_count[0] += 1
    for p in (data.get("plants") or []):
        vi  = p.get("valve_info") or {}
        fl  = vi.get("fill_valve_label")
        dl  = vi.get("drain_valve_label")
        if not fl:
            continue
        vr  = vi.get("valve_relays") or {}
        plants_by_label[fl] = {
            "fill":   (vr.get(fl) or {}).get("status"),
            "drain":  (vr.get(dl) or {}).get("status"),
        }

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)

# Warm up — wait for at least 2 plants_update so we know AFS's emit interval is captured
deadline = time.time() + 15
while time.time() < deadline and update_count[0] < 2:
    time.sleep(0.5)
print(f"Warmup: {update_count[0]} plants_update events received before testing")
print(f"AFS plants_by_label: {sorted(plants_by_label.keys())}\n")

def wait_state(fill_label, *, want_fill=None, want_drain=None, max_wait=12.0):
    deadline = time.time() + max_wait
    n0 = update_count[0]
    while time.time() < deadline:
        st = plants_by_label.get(fill_label, {})
        ok_f = (want_fill  is None) or (st.get("fill")  == want_fill)
        ok_d = (want_drain is None) or (st.get("drain") == want_drain)
        if ok_f and ok_d:
            return True, st, update_count[0] - n0
        time.sleep(0.25)
    return False, plants_by_label.get(fill_label, {}), update_count[0] - n0

def post(url):
    try:
        r = requests.post(url, timeout=5)
        return r.json().get("status") == "success"
    except Exception as e:
        print(f"  POST {url} FAILED: {e}")
        return False

# Pacing: cooldown is 5s on same valve. AFS emit interval ~3-5s.
# Wait at least 7s between consecutive same-valve toggles.

results = []
for fill_label, drain_label, fill_id, drain_id in zones:
    print(f"--- {fill_label} ---")
    if fill_label not in plants_by_label:
        results.append((fill_label, "SKIP - not in AFS"))
        continue

    fails = []
    # FILL ON
    post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/on")
    ok, st, evts = wait_state(fill_label, want_fill="on")
    print(f"  fill  ON  -> {st.get('fill'):3s}  ({evts} events, {'OK' if ok else 'FAIL'})")
    if not ok: fails.append("fill ON")
    time.sleep(7)

    # FILL OFF
    post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/off")
    ok, st, evts = wait_state(fill_label, want_fill="off")
    print(f"  fill  OFF -> {st.get('fill'):3s}  ({evts} events, {'OK' if ok else 'FAIL'})")
    if not ok: fails.append("fill OFF")
    time.sleep(7)

    # DRAIN ON
    post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/on")
    ok, st, evts = wait_state(fill_label, want_drain="on")
    print(f"  drain ON  -> {st.get('drain'):3s}  ({evts} events, {'OK' if ok else 'FAIL'})")
    if not ok: fails.append("drain ON")
    time.sleep(7)

    # DRAIN OFF
    post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/off")
    ok, st, evts = wait_state(fill_label, want_drain="off")
    print(f"  drain OFF -> {st.get('drain'):3s}  ({evts} events, {'OK' if ok else 'FAIL'})")
    if not ok: fails.append("drain OFF")
    time.sleep(7)

    results.append((fill_label, "ALL 4 OK" if not fails else "FAILED: " + ", ".join(fails)))

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
for k, v in results:
    print(f"  {k}: {v}")
sio.disconnect()
PY
