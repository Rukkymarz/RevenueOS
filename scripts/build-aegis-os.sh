#!/bin/sh
# Build aegis-os (C03, named — docs/PINS.md) from the commit pinned in config/sources.yaml and
# install it to /usr/local/bin. Used by CI and developer machines; the compose image builds the
# same commit (python.Dockerfile, stage `aegis`).
# Needs: git, a Rust toolchain (cargo/rustc), a C compiler + pkg-config (rusqlite's bundled
# SQLite and ring both compile native code).
set -eu
SHA="${AEGIS_OS_SHA:-d9bdfa978d721cae0dc2bfa277ed371c9db60c5a}"
SRC="$(mktemp -d)"
git clone -q https://github.com/heurion-org/aegis-os "$SRC"
git -C "$SRC" checkout -q "$SHA"
( cd "$SRC" && cargo build --release --locked -p aos-cli )
${SUDO:-sudo} install -m 0755 "$SRC/target/release/aos-cli" /usr/local/bin/aegis-os
/usr/local/bin/aegis-os --version
