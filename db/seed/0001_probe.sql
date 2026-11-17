-- Phase 1 seed: the probe agent and task used by the trace and egress acceptance tests.
-- Idempotent. The task stays in DRAFT; receipts attach to it.
INSERT INTO agents(id, name, role, framework, budget_monthly)
VALUES ('7a1c2e30-0001-4000-8000-000000000001', 'probe-agent', 'probe', 'langgraph', 10)
ON CONFLICT (id) DO NOTHING;
INSERT INTO tasks(id, objective, task_class, acceptance_criteria)
VALUES ('7a1c2e30-0002-4000-8000-000000000001', 'Phase 1 trace and egress probe', 'probe', '[{"check":"span_chain"}]')
ON CONFLICT (id) DO NOTHING;
-- Phase 2 (INV-09): the probe agent owns its identities; egress rules and bindings live in Postgres.
INSERT INTO agent_identities(id, agent_id, kind, provider, address)
VALUES ('7a1c2e30-0003-4000-8000-000000000001', '7a1c2e30-0001-4000-8000-000000000001', 'email', 'stalwart',
        'probe-agent@agents.revenueos.test')
ON CONFLICT (id) DO NOTHING;
INSERT INTO agent_identities(id, agent_id, kind, provider, profile_path)
VALUES ('7a1c2e30-0003-4000-8000-000000000002', '7a1c2e30-0001-4000-8000-000000000001', 'browser_profile', 'chromium',
        '/var/lib/revenueos/profiles/7a1c2e30-0001-4000-8000-000000000001/default')
ON CONFLICT (id) DO NOTHING;
INSERT INTO egress_rules(agent_id, task_id, host, created_by)
VALUES ('7a1c2e30-0001-4000-8000-000000000001', NULL, 'upstream-echo:8080', 'seed')
ON CONFLICT DO NOTHING;
INSERT INTO secret_bindings(secret_ref, host, header, format, agent_ids)
VALUES ('keychain://upstream-echo-token', 'upstream-echo:8080', 'authorization', 'Bearer {}',
        ARRAY['7a1c2e30-0001-4000-8000-000000000001']::uuid[])
ON CONFLICT (host, header, secret_ref) DO NOTHING;
