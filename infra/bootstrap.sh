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
gen "$DIR/keychain/mcp-allmail-token"
gen "$DIR/keychain/runtime-omni-token"
for d in files terminal python processes system screen gui clipboard apps notify web browser memory bus plans; do
  gen "$DIR/keychain/mcp-nava-$d-token"      # the 15 NAVA MCP servers (spec 3.3)
done
gen "$DIR/keychain/mcp-forage-token"        # Forage, the single manually configured MCP gateway (spec 4.1)
gen "$DIR/keychain/egress-identity-hmac"   # signs identity-pinned egress (supervisor -> egress-authz)
# Mail stack (spec 2.1). Stalwart reads its admin secret from a file, byte for byte: no newline.
[ -f "$DIR/keychain/stalwart-admin-password" ] || { umask 077; printf '%s' "$(openssl rand -hex 24)" > "$DIR/keychain/stalwart-admin-password"; }
[ -f "$DIR/keychain/agenticmail-master-key" ] || { umask 077; printf 'mk_%s' "$(openssl rand -hex 32)" > "$DIR/keychain/agenticmail-master-key"; }
gen "$DIR/keychain/agenticmail-inbound-secret"
chmod 600 "$DIR/keychain/stalwart-admin-password" "$DIR/keychain/agenticmail-master-key"
# Egress CA for inspected HTTPS (INV-11): the sandbox trusts only this CA; its key never enters one.
if [ ! -f "$DIR/keychain/egress-ca-key" ]; then
  umask 077
  CNF="$(mktemp)"
  printf '[req]\ndistinguished_name=dn\nx509_extensions=v3\nprompt=no\n[dn]\nCN=RevenueOS egress CA\n[v3]\nbasicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign,cRLSign,digitalSignature\nsubjectKeyIdentifier=hash\n' > "$CNF"
  openssl ecparam -genkey -name prime256v1 -noout | openssl pkcs8 -topk8 -nocrypt -out "$DIR/keychain/egress-ca-key"
  openssl req -x509 -new -key "$DIR/keychain/egress-ca-key" -sha256 -days 3650 -config "$CNF" -out "$DIR/keychain/egress-ca-cert"
  rm -f "$CNF"
  chmod 600 "$DIR/keychain/egress-ca-key" "$DIR/keychain/egress-ca-cert"
fi
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
