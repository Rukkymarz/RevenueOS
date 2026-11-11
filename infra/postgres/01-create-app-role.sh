#!/usr/bin/env bash
set -euo pipefail
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"
if [ "${#APP_DB_PASSWORD}" -lt 24 ]; then
  echo 'APP_DB_PASSWORD must be at least 24 characters' >&2
  exit 1
fi
# psql literal escaping uses :'app_password', not shell interpolation.
psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -v app_password="${APP_DB_PASSWORD}" <<'SQL'
CREATE ROLE revenueos_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE revenueos TO revenueos_app;
SQL

# Production uses the same PostgreSQL server but an isolated database and
# dedicated login for Keycloak. Credentials never enter SQL via interpolation.
if [ -n "${KEYCLOAK_DB_PASSWORD:-}" ]; then
  if [ "${#KEYCLOAK_DB_PASSWORD}" -lt 24 ]; then
    echo 'KEYCLOAK_DB_PASSWORD must have at least 24 characters' >&2; exit 1
  fi
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -v kc_password="${KEYCLOAK_DB_PASSWORD}" <<'SQL'
CREATE ROLE revenueos_keycloak LOGIN PASSWORD :'kc_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE DATABASE keycloak OWNER revenueos_keycloak;
SQL
fi
