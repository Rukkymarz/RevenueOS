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
gen "$DIR/keychain/egress-identity-hmac"   # signs identity-pinned egress (supervisor -> egress-authz)
# API bearer tokens (spec 2.5 RBAC). The API reads only their sha256 digests from api-principals.
gen "$DIR/keychain/api-token-owner"         # human:owner  - approver, auditor
gen "$DIR/keychain/api-token-probe-agent"   # agent:probe  - requester
digest() { printf '%s' "$(cat "$1")" | openssl dgst -sha256 -r | cut -d' ' -f1; }
umask 077
printf '[{"token_sha256":"%s","principal":"human:owner","roles":["approver","auditor"]},{"token_sha256":"%s","principal":"agent:probe","roles":["requester"]}]\n' \
  "$(digest "$DIR/keychain/api-token-owner")" "$(digest "$DIR/keychain/api-token-probe-agent")" > "$DIR/keychain/api-principals"
chmod 600 "$DIR/keychain/api-principals"
PW="$(cat "$DIR/pg_owner_password")"
umask 077
printf '*:*:*:revenueos_owner:%s\n' "$PW" > "$DIR/pgpass"
printf '127.0.0.1:5432:*:revenueos_owner:%s\n' "$PW" > "$DIR/pgpass_host"
chmod 600 "$DIR/pgpass" "$DIR/pgpass_host"
# Containers run as this (non-root) host user so they can read the 0600/0700 secrets above.
printf 'REVENUEOS_UID=%s\n' "$(id -u)" > "$(dirname "$DIR")/.env"
echo "secrets ready in $DIR"
