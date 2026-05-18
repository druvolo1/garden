#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== dnspython installed? ==="
$PY -c "import dns.resolver; print('dnspython', dns.__version__)" 2>&1
echo
echo "=== eventlet greendns available? ==="
$PY -c "import eventlet.support.greendns; print('greendns OK')" 2>&1

echo
echo "=== /etc/resolv.conf ==="
cat /etc/resolv.conf

echo
echo "=== 30x rapid resolve of drain.dr / Fill.dr / Drain.dr / Drain.local INSIDE eventlet ==="
$PY - <<'PY'
import eventlet
eventlet.monkey_patch()
import socket, time

names = ['drain.dr', 'Fill.dr', 'Drain.dr', 'Drain.local', 'fill.dr']
for n in names:
    times = []
    fails = []
    for i in range(20):
        t0 = time.time()
        try:
            ip = socket.gethostbyname(n)
            times.append((time.time() - t0) * 1000)
        except Exception as e:
            fails.append(str(e))
            times.append((time.time() - t0) * 1000)
    avg = sum(times)/len(times)
    mn = min(times); mx = max(times)
    print(f"  {n:15s}  20 lookups: min={mn:.1f}ms avg={avg:.1f}ms max={mx:.1f}ms fails={len(fails)}")
    if fails:
        print(f"    sample fails: {fails[:3]}")
PY

echo
echo "=== getaddrinfo for drain.dr inside eventlet (incl. IPv6) ==="
$PY - <<'PY'
import eventlet
eventlet.monkey_patch()
import socket
for fam in [(socket.AF_UNSPEC, 'UNSPEC'), (socket.AF_INET, 'INET'), (socket.AF_INET6, 'INET6')]:
    try:
        r = socket.getaddrinfo('drain.dr', 8000, fam[0], socket.SOCK_STREAM)
        print(f"  {fam[1]}: {[(a[0].name, a[4]) for a in r]}")
    except Exception as e:
        print(f"  {fam[1]}: ERROR {e}")
PY

echo
echo "=== 10x python-socketio connect to drain.dr by hostname, capture timings ==="
$PY - <<'PY'
import eventlet
eventlet.monkey_patch()
import socketio, time
ok = 0; fail = 0
for i in range(10):
    sio = socketio.Client(logger=False, engineio_logger=False)
    t0 = time.time()
    try:
        sio.connect("http://drain.dr:8000", socketio_path="/socket.io",
                    transports=["websocket","polling"],
                    namespaces=["/status"], wait_timeout=5)
        ok += 1
        elapsed = time.time() - t0
        print(f"  attempt {i+1}: OK in {elapsed*1000:.0f}ms")
        sio.disconnect()
    except Exception as e:
        fail += 1
        elapsed = time.time() - t0
        print(f"  attempt {i+1}: FAIL in {elapsed*1000:.0f}ms ({type(e).__name__}: {e})")
    time.sleep(0.3)
print(f"\n  Summary: {ok}/10 connects OK")
PY
