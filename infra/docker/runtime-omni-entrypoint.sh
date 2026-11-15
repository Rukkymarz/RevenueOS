#!/bin/sh
# Real desktop for the runtime: virtual X display, window manager, and a VNC server bound to
# the container's loopback only (human takeover attaches through the console, spec 3.5).
set -eu
# python-xlib (pyautogui) insists on an Xauthority file; the display has no TCP listener and no
# auth, so an empty file is correct.
touch "${HOME:-/home/revenueos}/.Xauthority"
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 50); do xdpyinfo -display :1 >/dev/null 2>&1 && break; sleep 0.1; done
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display :1 -localhost -forever -shared -nopw -quiet >/tmp/x11vnc.log 2>&1 &
# Chromium trusts the identity-pinned egress CA through the per-user NSS store, so the
# OpenMuse browser verifies MITM'd HTTPS instead of ignoring certificate errors.
if [ -f /run/revenueos/keychain/egress-ca-cert ]; then
  mkdir -p "${HOME:-/home/revenueos}/.pki/nssdb"
  certutil -d "sql:${HOME:-/home/revenueos}/.pki/nssdb" -N --empty-password 2>/dev/null || true
  certutil -d "sql:${HOME:-/home/revenueos}/.pki/nssdb" -A -t "C,," -n revenueos-egress \
    -i /run/revenueos/keychain/egress-ca-cert 2>/dev/null || true
fi
exec "$@"
