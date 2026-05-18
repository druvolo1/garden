#!/bin/bash
set +e
echo "=== drain.dr journal last 60s, filtered for 172.16.1.178 (zone1) ==="
journalctl -u garden.service --since '60 seconds ago' --no-pager 2>/dev/null | \
  grep -E "172\.16\.1\.178|GET /socket|POST /socket|Bad request|HandshakeError|StatusNamespace: Client connected" | tail -30

echo
echo "=== Recent gunicorn errors / tracebacks ==="
journalctl -u garden.service --since '60 seconds ago' --no-pager 2>/dev/null | \
  grep -iE "error|exception|traceback|refused" | tail -20

echo
echo "=== ss -tan TIME_WAIT count (drain.dr side) for zone1 connections ==="
ss -tan 2>/dev/null | grep "172.16.1.178" | head -10
