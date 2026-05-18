#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

echo "=== With EVENTLET_NO_GREENDNS=1: 30x rapid resolve under eventlet ==="
EVENTLET_NO_GREENDNS=1 "$PY" - <<'PY'
import os
print(f"  EVENTLET_NO_GREENDNS={os.environ.get('EVENTLET_NO_GREENDNS')}")
import eventlet
eventlet.monkey_patch()
import socket, time

names = ['drain.dr', 'Fill.dr', 'Drain.dr', 'fill.dr']
for n in names:
    fails = 0
    times = []
    for i in range(20):
        t0 = time.time()
        try:
            socket.gethostbyname(n)
            times.append((time.time() - t0)*1000)
        except Exception:
            fails += 1
            times.append((time.time() - t0)*1000)
    print(f"  {n:12s}: fails={fails}/20  min={min(times):.1f}ms  max={max(times):.1f}ms  avg={sum(times)/len(times):.1f}ms")
PY

echo
echo "=== With EVENTLET_NO_GREENDNS=1: 10x python-socketio connect to drain.dr ==="
EVENTLET_NO_GREENDNS=1 "$PY" - <<'PY'
import eventlet
eventlet.monkey_patch()
import socketio, time
ok = 0; fail = 0; tt = []
for i in range(10):
    sio = socketio.Client(logger=False, engineio_logger=False)
    t0 = time.time()
    try:
        sio.connect("http://drain.dr:8000", socketio_path="/socket.io",
                    transports=["websocket","polling"],
                    namespaces=["/status"], wait_timeout=5)
        ok += 1
        e = (time.time()-t0)*1000
        tt.append(e)
        sio.disconnect()
    except Exception as ex:
        fail += 1
        e = (time.time()-t0)*1000
        tt.append(e)
print(f"  {ok}/10 OK   timings min={min(tt):.0f}ms max={max(tt):.0f}ms avg={sum(tt)/len(tt):.0f}ms")
PY
