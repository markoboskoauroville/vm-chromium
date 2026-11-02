#!/bin/bash
# Stage 1 checks on chromium-vm (run with sudo). Prints OK/FAIL per check.
. /etc/chromium-vm.conf
pass=0; fail=0
ok()  { echo "OK   $*"; pass=$((pass+1)); }
bad() { echo "FAIL $*"; fail=$((fail+1)); }

systemctl is-active -q chromium-vm-xvnc    && ok "Xvnc service running"     || bad "Xvnc service not running"
systemctl is-active -q chromium-vm-session && ok "session service running"  || bad "session service not running"
systemctl is-enabled -q chromium-vm-xvnc && systemctl is-enabled -q chromium-vm-session \
  && ok "both start at boot" || bad "not enabled for boot"

listen=$(ss -Hltn "sport = :$VNC_PORT" | awk '{print $4}')
[ "$listen" = "$VNC_IP:$VNC_PORT" ] && ok "listens only on $VNC_IP:$VNC_PORT" || bad "listens on: ${listen:-nothing}"

pgrep -u "$VM_USER" -f '(chromium|chrome).*--start-maximized' >/dev/null && ok "Chromium running" || bad "Chromium not running"

others=$(sudo -u "$VM_USER" DISPLAY=":$DISPLAY_NUM" xdotool search --onlyvisible --name . 2>/dev/null \
  | while read -r id; do sudo -u "$VM_USER" DISPLAY=":$DISPLAY_NUM" xprop -id "$id" WM_CLASS 2>/dev/null; done \
  | grep -viE 'chromium|google-chrome' | grep -v 'not found' | sort -u)
[ -z "$others" ] && ok "nothing but Chromium on the screen" || bad "other windows: $others"

if [ "${1:-}" = --restart-test ]; then
  echo "     closing Chromium..."
  pkill -u "$VM_USER" -f '(chromium|chrome).*--start-maximized' -o
  for _ in $(seq 20); do sleep 1; pgrep -u "$VM_USER" -f '(chromium|chrome).*--start-maximized' >/dev/null && break; done
  pgrep -u "$VM_USER" -f '(chromium|chrome).*--start-maximized' >/dev/null && ok "Chromium came back after close" || bad "Chromium did not come back"
fi
echo "$pass OK, $fail FAIL"
[ "$fail" = 0 ]
