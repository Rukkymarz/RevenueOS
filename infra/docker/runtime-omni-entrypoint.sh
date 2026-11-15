#!/bin/sh
# Real desktop for the runtime: virtual X display, window manager, and a VNC server bound to
# the container's loopback only (human takeover attaches through the console, spec 3.5).
set -eu
Xvfb :1 -screen 0 1280x800x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 50); do xdpyinfo -display :1 >/dev/null 2>&1 && break; sleep 0.1; done
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display :1 -localhost -forever -shared -nopw -quiet >/tmp/x11vnc.log 2>&1 &
exec "$@"
