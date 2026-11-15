#!/bin/sh
# Resolve AgenticMail's secrets by reference (keychain files) into its environment at start;
# nothing is written to disk or logged.
set -eu
KC="${REVENUEOS_KEYCHAIN_DIR:-/run/revenueos/keychain}"
AGENTICMAIL_MASTER_KEY="$(cat "$KC/agenticmail-master-key")"
STALWART_ADMIN_PASSWORD="$(cat "$KC/stalwart-admin-password")"
# Set explicitly: when unset, AgenticMail generates one and prints it to its log
# (packages/api/src/routes/inbound.ts). The trace secret scan caught that leak.
AGENTICMAIL_INBOUND_SECRET="$(cat "$KC/agenticmail-inbound-secret")"
export AGENTICMAIL_MASTER_KEY STALWART_ADMIN_PASSWORD AGENTICMAIL_INBOUND_SECRET
exec "$@"
