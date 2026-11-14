-- Phase 1 seed: the probe agent and task used by the trace and egress acceptance tests.
-- Idempotent. The task stays in DRAFT; receipts attach to it.
INSERT INTO agents(id, name, role, framework, budget_monthly)
VALUES ('7a1c2e30-0001-4000-8000-000000000001', 'probe-agent', 'probe', 'langgraph', 10)
ON CONFLICT (id) DO NOTHING;
INSERT INTO tasks(id, objective, task_class, acceptance_criteria)
VALUES ('7a1c2e30-0002-4000-8000-000000000001', 'Phase 1 trace and egress probe', 'probe', '[{"check":"span_chain"}]')
ON CONFLICT (id) DO NOTHING;
