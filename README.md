# RevenueOS

Self-hosted, open-source-first multi-agent business operating system.
Specification: "RevenueOS build specification v2".

## Status: Phase 1 complete

| Built | Where |
| --- | --- |
| Core Postgres schema (all spec tables) with enforcement triggers | `db/migrations/0001_core.sql` |
| Task state machine enforced in the database | `task_state_guard()` |
| Hash-chained, append-only, serialized audit ledger | `audit_chain()`, `audit_verify()` |
| Hash-bound, expiring, single-use approvals | `consume_approval()` |
| Component map: 87 components, 6 buses, workflow hops | `config/components.yaml` |
| Typed contracts for every connection | `packages/contracts/schemas/connections.json` |
| Adversarial invariant suite + connectivity suite | `tests/` |
| Compose (Postgres, migrations, OpenBao, OTel), CI | `infra/compose.yaml`, `.github/workflows/ci.yml` |

## Run the tests

```sh
# needs Postgres 16 and: pip install pytest pyyaml jsonschema
export REVENUEOS_PG_HOST=localhost REVENUEOS_PG_PORT=5432 REVENUEOS_PG_USER=postgres
pytest tests -q
```

## Run the stack

```sh
mkdir -p infra/secrets && openssl rand -hex 24 > infra/secrets/pg_owner_password
echo "postgres:5432:revenueos:revenueos_owner:$(cat infra/secrets/pg_owner_password)" > infra/secrets/pgpass
chmod 600 infra/secrets/*
docker compose -f infra/compose.yaml up
```
