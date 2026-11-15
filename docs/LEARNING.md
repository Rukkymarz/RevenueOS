# Learning loop

How RevenueOS improves itself without regressing. The loop is built in Phase 12 (C13
learning); this file states the rules it must meet, which INV-14 tests enforce.

## Rules

1. **Only verified outcomes teach.** Training signal comes from tasks with a `QC_PASSED`
   verification record and a complete evidence bundle (INV-01, INV-15). Unverified or
   `DO_NOT_FILE` outcomes are excluded.
2. **Every change is a candidate, not a deploy.** A new or changed skill, prompt, routing rule
   or tool preference is recorded as a change record with the prior version kept.
3. **Canary, then holdout.** The candidate runs on a canary cohort while a holdout keeps the
   current version. Promotion needs measured causal lift on the holdout comparison and no
   regression on the eval suite (Phase 8 assets).
4. **Human review.** A promotion needs a human review of the change record.
5. **Reversible.** Every promotion stores a rollback pointer; rollback restores the prior skill
   version in one step and is itself audited.
6. **Measured by cost per verified outcome.** The headline metric is
   `v_cost_per_verified_outcome` (DuckDB mirror, Phase 1 schema), not task count.

## What exists now (Phase 1)

- Verified-only views: `v_verified_*` in Postgres and `v_verified_tasks`,
  `v_cost_per_verified_outcome` in the DuckDB mirror (`db/duckdb/0001_mirror.sql`).
- INV-14 test is a strict `xfail` until Phase 12 lands the promotion gate.

## Acceptance (Phase 12)

Promotion gate blocks a regressing candidate; rollback restores the prior version.
