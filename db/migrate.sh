#!/bin/sh
# Applies db/migrations/*.sql in order, once each, recording them in schema_migrations.
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)/migrations"
psql -v ON_ERROR_STOP=1 -X -q -c "CREATE TABLE IF NOT EXISTS schema_migrations(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
for f in "$DIR"/*.sql; do
  name="$(basename "$f")"
  done_already="$(psql -X -A -t -c "SELECT 1 FROM schema_migrations WHERE name = '$name'")"
  if [ -z "$done_already" ]; then
    echo "applying $name"
    psql -v ON_ERROR_STOP=1 -X -q -f "$f"   # each migration wraps itself in BEGIN/COMMIT
    psql -X -q -c "INSERT INTO schema_migrations(name) VALUES ('$name')"
  fi
done
echo "migrations up to date"
# Seeds are idempotent and re-applied on every start.
for s in "$(dirname "$DIR")"/seed/*.sql; do
  [ -f "$s" ] || continue
  echo "seeding $(basename "$s")"
  psql -v ON_ERROR_STOP=1 -X -q -f "$s"
done
