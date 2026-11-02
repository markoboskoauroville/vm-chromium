#!/bin/bash
# PLAN.md Stage 1.2: time from launch to Chromium's first visible window, deb vs snap, on a throwaway Xvnc :9
# (local only, so the real screen :1 is untouched). Run as the login user, not root.
#   ./stage1/measure-chromium-start.sh            # measures whatever of /usr/bin/chromium and /snap/bin/chromium exists
# To measure both: the deb comes with setup.sh; add the snap with `sudo snap install chromium` (it lives beside the deb).
set -uo pipefail
RUNS=${RUNS:-3}
Xvnc :9 -localhost -SecurityTypes None -geometry 1920x1080 -depth 24 >/dev/null 2>&1 &
X=$!; trap 'kill $X 2>/dev/null' EXIT
export DISPLAY=:9
for _ in $(seq 50); do xdpyinfo >/dev/null 2>&1 && break; sleep 0.2; done

measure() { # $1 name, $2 binary
  [ -x "$2" ] || { echo "$1: $2 not installed"; return; }
  for run in $(seq "$RUNS"); do
    dir=$(mktemp -d)
    t0=$(date +%s.%N)
    "$2" --user-data-dir="$dir/p" --no-first-run --no-default-browser-check --password-store=basic about:blank >/dev/null 2>&1 &
    pid=$!
    xdotool search --sync --onlyvisible --class chromium >/dev/null 2>&1
    t1=$(date +%s.%N)
    printf '%s run %d: %.2f s\n' "$1" "$run" "$(echo "$t1 - $t0" | bc)"
    kill "$pid" 2>/dev/null; pkill -f -- "--user-data-dir=$dir/p" 2>/dev/null; sleep 2; rm -rf "$dir"
  done
}
command -v bc >/dev/null || { echo "needs bc: sudo apt install bc"; exit 1; }
measure deb  /usr/bin/chromium
measure snap /snap/bin/chromium
