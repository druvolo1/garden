#!/bin/bash
# Run on fill.dr (uses AFS's venv). Connects to AFS WS, then for each zone
# toggles fill and drain at their respective masters and verifies AFS sees
# the change.
set +e
PY=~/Auto-Feeding-System/venv/bin/python3

"$PY" - <<'PY'
import socketio, requests, time

# zone_key -> (fill_valve_id_on_fill.dr, drain_valve_id_on_drain.dr)
zones = [
    ("Zone1.local", 1, 1),
    ("Zone2.local", 2, 2),
    ("Zone3.local", 3, 3),
    ("Zone5.local", 5, 5),
    ("Zone6.local", 6, 6),
    ("Zone7.local", 7, 7),
]

# Latest AFS state — keyed by plant 'ip' field (matches additional_plants entries)
latest = {}

sio = socketio.Client(logger=False, engineio_logger=False)

@sio.on("plants_update", namespace="/status")
def on_pu(data):
    for p in (data.get("plants") or []):
        key = p.get("ip") or "local"
        vi  = p.get("valve_info") or {}
        vr  = vi.get("valve_relays") or {}
        fl  = vi.get("fill_valve_label")
        dl  = vi.get("drain_valve_label")
        fs  = (vr.get(fl) or {}).get("status") if fl else None
        ds  = (vr.get(dl) or {}).get("status") if dl else None
        latest[key] = {"fill": fs, "drain": ds, "fill_label": fl, "drain_label": dl}

sio.connect("http://127.0.0.1:8001", socketio_path="/socket.io",
            transports=["websocket","polling"], namespaces=["/status"], wait_timeout=5)
print("Connected to AFS, waiting 2s for initial plants_update...")
time.sleep(2)

print(f"AFS knows these plants: {sorted(latest.keys())}\n")

def afs_check(zone_key, want_fill=None, want_drain=None, max_wait=4.0):
    """Wait until AFS shows the expected state for zone_key, or timeout."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        st = latest.get(zone_key, {})
        ok_f = (want_fill  is None) or (st.get("fill")  == want_fill)
        ok_d = (want_drain is None) or (st.get("drain") == want_drain)
        if ok_f and ok_d:
            return True, st
        time.sleep(0.25)
    return False, latest.get(zone_key, {})

def post(url):
    try:
        r = requests.post(url, timeout=4)
        return r.json().get("status") == "success"
    except Exception as e:
        print(f"  POST {url} FAILED: {e}")
        return False

results = []
for zone_key, fill_id, drain_id in zones:
    print(f"--- {zone_key}  (fill={fill_id}, drain={drain_id}) ---")
    if zone_key not in latest:
        print(f"  AFS does not know this zone, skipping")
        results.append((zone_key, "SKIP - not in AFS"))
        continue

    # FILL ON
    if not post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/on"):
        results.append((zone_key, "fill on POST failed"))
        continue
    ok, st = afs_check(zone_key, want_fill="on")
    print(f"  fill ON  -> AFS fill={st.get('fill')}  {'OK' if ok else 'FAIL'}")
    if not ok:
        results.append((zone_key, f"fill ON expected on, got {st.get('fill')}"))
        continue
    time.sleep(5)  # cooldown

    # FILL OFF
    post(f"http://Fill.local:8000/api/valve_relay/{fill_id}/off")
    ok, st = afs_check(zone_key, want_fill="off")
    print(f"  fill OFF -> AFS fill={st.get('fill')}  {'OK' if ok else 'FAIL'}")
    if not ok:
        results.append((zone_key, f"fill OFF expected off, got {st.get('fill')}"))
        continue
    time.sleep(5)

    # DRAIN ON
    if not post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/on"):
        results.append((zone_key, "drain on POST failed"))
        continue
    ok, st = afs_check(zone_key, want_drain="on")
    print(f"  drain ON -> AFS drain={st.get('drain')}  {'OK' if ok else 'FAIL'}")
    if not ok:
        results.append((zone_key, f"drain ON expected on, got {st.get('drain')}"))
        continue
    time.sleep(5)

    # DRAIN OFF
    post(f"http://Drain.local:8000/api/valve_relay/{drain_id}/off")
    ok, st = afs_check(zone_key, want_drain="off")
    print(f"  drain OFF-> AFS drain={st.get('drain')} {'OK' if ok else 'FAIL'}")
    if not ok:
        results.append((zone_key, f"drain OFF expected off, got {st.get('drain')}"))
        continue
    time.sleep(5)

    results.append((zone_key, "ALL 4 OK"))

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
for k, v in results:
    print(f"  {k}: {v}")

sio.disconnect()
PY
