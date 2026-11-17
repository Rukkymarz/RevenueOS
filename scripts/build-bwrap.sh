#!/bin/sh
# Build Bubblewrap from the commit pinned in config/sources.yaml and install it to /usr/local/bin.
# Used by CI and developer machines; the compose image builds the same commit (python.Dockerfile).
# Needs: git meson ninja-build gcc libcap-dev pkg-config.
set -eu
SHA="${BWRAP_SHA:-1fb0aa26d3eb66254f7742e704add7f82f41a582}"
SRC="$(mktemp -d)"
git clone -q https://github.com/containers/bubblewrap "$SRC"
git -C "$SRC" checkout -q "$SHA"
meson setup "$SRC/build" "$SRC" -Dman=disabled -Dselinux=disabled -Dtests=false -Dbash_completion=disabled \
  -Dzsh_completion=disabled -Dpython="$(command -v python3)" >/dev/null
ninja -C "$SRC/build" bwrap >/dev/null
${SUDO:-sudo} install -m 0755 "$SRC/build/bwrap" /usr/local/bin/bwrap
/usr/local/bin/bwrap --version
