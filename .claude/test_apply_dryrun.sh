#!/bin/bash
# READ-ONLY diagnostic — does NOT modify the working tree.
set +e
cd /home/dave/garden || exit 1
echo "=== HOSTNAME: $(hostname) ==="
echo "--- HEAD ---"
git log -1 --oneline
echo
echo "--- The 2 incoming commits ---"
git log --oneline HEAD..origin/main
echo
echo "--- Files touched by incoming commits ---"
git diff --name-only HEAD..origin/main
echo
echo "--- Locally-modified files ---"
git diff --name-only
echo
echo "--- Overlap (these would conflict on git pull) ---"
comm -12 \
  <(git diff --name-only HEAD..origin/main | sort) \
  <(git diff --name-only | sort)
