#!/bin/bash
set +e
cd /home/dave/garden || exit 1
echo "=== HOSTNAME: $(hostname) ==="
echo "--- git remote -v ---"
git remote -v
echo
echo "--- git config (user-relevant) ---"
git config --get remote.origin.url
git config --get user.email 2>/dev/null
git config --get user.name 2>/dev/null
echo
echo "--- git status (short) ---"
git status --short
echo
echo "--- git fetch (manual, with stderr) ---"
git fetch 2>&1
echo "  fetch exit: $?"
echo
echo "--- git status -uno ---"
git status -uno
echo
echo "--- HEAD vs origin/main ---"
echo "local HEAD:    $(git rev-parse HEAD)"
echo "origin/main:   $(git rev-parse origin/main 2>&1)"
echo "ahead/behind:  $(git rev-list --left-right --count HEAD...origin/main 2>&1)"
echo
echo "--- /api/settings/check_update via curl ---"
curl -s -m 30 http://127.0.0.1:8000/api/settings/check_update
echo
