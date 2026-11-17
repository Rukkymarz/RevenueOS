-- Phase 4: tool discovery and governance (C04). agent-discover is the registry of record for
-- what is installed and connected; these tables are the governance of record: which servers
-- exist, their policy score, their approval status (INV-10), which task may use them, and an
-- append-only log of everything that happened to them.

BEGIN;

-- INV-10 needs to know what a production task is. Default is production (fail closed): an
-- experimental server is usable only on a task explicitly marked experimental.
ALTER TABLE tasks ADD COLUMN environment text NOT NULL DEFAULT 'production'
  CHECK (environment IN ('experimental', 'production'));

ALTER TABLE tool_installations
  ADD COLUMN agent_id      uuid REFERENCES agents(id),          -- the server's own identity: its secret and egress scope (4.7)
  ADD COLUMN install_spec  jsonb NOT NULL DEFAULT '{}'::jsonb,  -- transport, command/url, env key -> secret ref, egress hosts
  ADD COLUMN active        boolean NOT NULL DEFAULT false,      -- enabled in agent-discover
  ADD COLUMN observe_until timestamptz,                         -- earliest promotion time (Addendum F: 14 days)
  ADD COLUMN approved_at   timestamptz,
  ADD COLUMN updated_at    timestamptz NOT NULL DEFAULT now(),
  ADD CONSTRAINT tool_installations_health CHECK (health_status IN ('UNKNOWN', 'HEALTHY', 'UNHEALTHY', 'QUARANTINED')),
  ADD CONSTRAINT tool_installations_active_healthy CHECK (NOT active OR health_status IN ('UNKNOWN', 'HEALTHY'));

-- Promotion guard: leaving `experimental` needs an approver (0001 CHECK) and, when an observation
-- window was set, the window must have ended. Status never moves backwards to skip the window,
-- and the window is fixed at install for every role, owners included.
CREATE FUNCTION tool_installation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> OLD.status THEN
    IF OLD.status = 'experimental' AND NEW.status = 'production' THEN
      RAISE EXCEPTION 'INV-10: % must be approved before production', OLD.mcp_server_name;
    END IF;
    IF OLD.status = 'experimental' AND OLD.observe_until IS NOT NULL AND now() < OLD.observe_until THEN
      RAISE EXCEPTION 'INV-10: % is under observation until %', OLD.mcp_server_name, OLD.observe_until;
    END IF;
    IF NEW.status = 'experimental' THEN
      NEW.approved_by := NULL; NEW.approved_at := NULL;
    ELSIF OLD.status = 'experimental' THEN
      NEW.approved_at := now();
    END IF;
  END IF;
  IF NEW.observe_until IS DISTINCT FROM OLD.observe_until THEN
    RAISE EXCEPTION 'INV-10: the observation window of % is fixed at install', OLD.mcp_server_name;
  END IF;
  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER trg_tool_installation_guard BEFORE UPDATE ON tool_installations
  FOR EACH ROW EXECUTE FUNCTION tool_installation_guard();

-- Append-only log: installs, policy denials, blocked activations, health and sandbox violations.
CREATE TABLE tool_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mcp_server_name text NOT NULL,
  installation_id uuid REFERENCES tool_installations(id),
  task_id         uuid REFERENCES tasks(id),
  agent_id        uuid REFERENCES agents(id),
  kind            text NOT NULL CHECK (kind IN (
                    'searched', 'policy_denied', 'installed', 'learned', 'approved', 'promoted', 'demoted',
                    'activated', 'deactivated', 'activation_blocked', 'call_blocked',
                    'health_ok', 'health_failed',
                    'egress_blocked', 'secret_read_blocked', 'sandbox_write_blocked',
                    'secret_read', 'sandbox_escape', 'quarantined')),
  detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tool_events_server ON tool_events (mcp_server_name, created_at);
CREATE TRIGGER trg_tool_events_append_only BEFORE UPDATE OR DELETE ON tool_events
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- INV-10 in the database: the one question every caller asks, and the one place it is answered.
CREATE FUNCTION tool_activation_refusal(p_server text, p_task uuid) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT CASE
    WHEN i.id IS NULL THEN 'server is not installed'
    WHEN t.id IS NULL THEN 'unknown task'
    WHEN i.health_status IN ('UNHEALTHY', 'QUARANTINED') THEN 'server is ' || lower(i.health_status)
    WHEN t.environment = 'production' AND i.status = 'experimental'
      THEN 'INV-10: experimental server cannot be used by a production task'
    ELSE NULL
  END
  FROM (SELECT 1) one
  LEFT JOIN LATERAL (SELECT * FROM tool_installations WHERE mcp_server_name = p_server
                      ORDER BY created_at DESC LIMIT 1) i ON true
  LEFT JOIN tasks t ON t.id = p_task
$$;

-- An activation is a server made usable for one task. The trigger makes a forbidden one impossible
-- whatever the caller is.
CREATE TABLE tool_activations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  installation_id uuid NOT NULL REFERENCES tool_installations(id),
  task_id         uuid NOT NULL REFERENCES tasks(id),
  agent_id        uuid REFERENCES agents(id),
  activated_at    timestamptz NOT NULL DEFAULT now(),
  deactivated_at  timestamptz
);
CREATE UNIQUE INDEX tool_activations_live ON tool_activations (installation_id, task_id) WHERE deactivated_at IS NULL;
CREATE FUNCTION tool_activation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE why text;
BEGIN
  SELECT tool_activation_refusal(i.mcp_server_name, NEW.task_id) INTO why
    FROM tool_installations i WHERE i.id = NEW.installation_id;
  IF why IS NOT NULL THEN
    RAISE EXCEPTION 'activation refused: %', why;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_tool_activation_guard BEFORE INSERT ON tool_activations
  FOR EACH ROW EXECUTE FUNCTION tool_activation_guard();

-- 4.4 curated discovery sources and what was ingested from them.
CREATE TABLE discovery_sources (
  name        text PRIMARY KEY,
  kind        text NOT NULL CHECK (kind IN ('registry', 'awesome-list', 'snapshot')),
  url         text NOT NULL,
  commit_sha  text,
  entries     integer NOT NULL DEFAULT 0,
  ingested_at timestamptz
);
CREATE TABLE discovery_entries (
  source      text NOT NULL REFERENCES discovery_sources(name),
  name        text NOT NULL,
  repo        text,
  description text NOT NULL DEFAULT '',
  stars       integer,
  last_push   date,
  license     text,
  PRIMARY KEY (source, name)
);
CREATE INDEX discovery_entries_name ON discovery_entries (lower(name));

-- Only the new tables: a blanket grant would undo 0003's revokes on its append-only tables.
GRANT SELECT, INSERT ON tool_events TO revenueos_app;
GRANT SELECT, INSERT, UPDATE ON tool_activations, discovery_sources TO revenueos_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON discovery_entries TO revenueos_app;

COMMIT;
