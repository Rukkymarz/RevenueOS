#!/bin/sh
# Create local secrets for the compose stack. Everything lands in infra/secrets (git-ignored).
# Re-running keeps existing values.
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)/secrets"
mkdir -p "$DIR/keychain" "$(dirname "$DIR")/otel/out"
chmod 700 "$DIR" "$DIR/keychain"
chmod 777 "$(dirname "$DIR")/otel/out"   # the collector runs as an unprivileged user
gen() { [ -f "$1" ] || { umask 077; openssl rand -hex 32 > "$1"; }; chmod 600 "$1"; }
gen "$DIR/pg_owner_password"
gen "$DIR/keychain/mcp-echo-probe-token"
gen "$DIR/keychain/upstream-echo-token"
PW="$(cat "$DIR/pg_owner_password")"
umask 077
printf '*:*:*:revenueos_owner:%s\n' "$PW" > "$DIR/pgpass"
printf '127.0.0.1:5432:*:revenueos_owner:%s\n' "$PW" > "$DIR/pgpass_host"
chmod 600 "$DIR/pgpass" "$DIR/pgpass_host"
echo "secrets ready in $DIR"
