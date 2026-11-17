-- DuckDB analytical mirror (spec section 7): task and cost tables copied from Postgres for
-- timeline and insight queries (Tares and the Phase 11 query set). Postgres stays authoritative;
-- the mirror is rebuilt from it and never written by agents. Verified-only views follow INV-15.
CREATE SCHEMA IF NOT EXISTS mirror;

CREATE TABLE IF NOT EXISTS mirror.tasks (
  id UUID PRIMARY KEY, project_id UUID, slice_id UUID, objective VARCHAR NOT NULL, task_class VARCHAR NOT NULL,
  state VARCHAR NOT NULL, executor_agent_id UUID, verifier_agent_id UUID, verification_id UUID,
  required_oracle_tier VARCHAR, cost_estimate DECIMAL(14,4), cost_actual DECIMAL(14,4),
  created_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ, mirrored_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mirror.verifications (
  id UUID PRIMARY KEY, task_id UUID NOT NULL, verifier_agent_id UUID NOT NULL, method VARCHAR NOT NULL,
  method_class VARCHAR NOT NULL, verdict VARCHAR NOT NULL, tier VARCHAR NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS mirror.tool_calls (
  id UUID PRIMARY KEY, task_id UUID NOT NULL, agent_id UUID NOT NULL, mcp_server VARCHAR NOT NULL, tool VARCHAR NOT NULL,
  args_hash VARCHAR NOT NULL, result_hash VARCHAR, latency_ms INTEGER NOT NULL, cost DECIMAL(14,6) NOT NULL,
  risk_class VARCHAR NOT NULL, approval_id UUID, verdict VARCHAR NOT NULL, created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS mirror.budgets (
  agent_id UUID NOT NULL, period VARCHAR NOT NULL, "limit" DECIMAL(14,4) NOT NULL, used DECIMAL(14,4) NOT NULL,
  reserved DECIMAL(14,4) NOT NULL, PRIMARY KEY (agent_id, period)
);
CREATE TABLE IF NOT EXISTS mirror.timeline_events (
  id UUID PRIMARY KEY, thing_type VARCHAR NOT NULL, thing_id VARCHAR NOT NULL, event_type VARCHAR NOT NULL,
  payload JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL
);

-- INV-15: insight reads only tasks that completed with a PASS verification.
CREATE OR REPLACE VIEW mirror.v_verified_tasks AS
  SELECT t.* FROM mirror.tasks t JOIN mirror.verifications v ON v.id = t.verification_id
  WHERE t.state = 'COMPLETED' AND v.verdict = 'PASS';
CREATE OR REPLACE VIEW mirror.v_cost_per_verified_outcome AS
  SELECT t.task_class, count(*) AS outcomes, sum(t.cost_actual) AS cost,
         sum(t.cost_actual) / nullif(count(*), 0) AS cost_per_outcome
  FROM mirror.v_verified_tasks t GROUP BY t.task_class;
