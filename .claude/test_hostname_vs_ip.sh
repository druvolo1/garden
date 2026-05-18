#!/bin/bash
set +e
PY=~/garden/venv/bin/python3

"$PY" - <<'PY'
# Simulate eventlet env like gunicorn
import eventlet
eventlet.monkey_patch()

import socketio, time

def test(label, target):
    sio = socketio.Client(logger=False, engineio_logger=False)
    got = []
    @sio.on("status_update", namespace="/status")
    def _(d): got.append(1)
    try:
        sio.connect(target, socketio_path="/socket.io",
                    transports=["websocket","polling"],
                    namespaces=["/status"], wait_timeout=5)
        time.sleep(1)
        print(f"  {label:30s}  -> CONNECTED (events: {len(got)})")
        sio.disconnect()
    except Exception as e:
        print(f"  {label:30s}  -> FAILED: {type(e).__name__}: {e}")

test("http://drain.dr:8000 (hostname)",  "http://drain.dr:8000")
test("http://172.16.1.30:8000 (IP)",     "http://172.16.1.30:8000")
test("http://drain.dr:8000 again",       "http://drain.dr:8000")
PY
