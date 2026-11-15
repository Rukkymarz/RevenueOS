-- Phase 3: NAVA agent OS (C03). Every tool call is a managed system call that passes the same
-- 12 gateway steps in order; locks, quotas, snapshots and rollback are part of the call. Also the
-- A2A message bus, four-tier memory, durable plans and JIT subagents.
-- The 21 NAVA invariants (N01..N21) are listed in docs/NAVA.md, each with its enforcing object
-- and test (tests/nava/).

BEGIN;

CREATE TYPE syscall_status AS ENUM ('running', 'committed', 'rolled_back', 'denied', 'failed');

-- N01..N17: the managed system call --------------------------------------------------------
CREATE TABLE syscalls (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id      uuid NOT NULL REFERENCES agents(id),
  task_id       uuid NOT NULL REFERENCES tasks(id),
  tool          text NOT NULL,
  args_hash     text NOT NULL CHECK (args_hash ~ '^[0-9a-f]{64}$'),
  mutating      boolean NOT NULL,
  risk_class    risk_class,
  mode          text NOT NULL DEFAULT 'auto' CHECK (mode IN ('ask', 'auto', 'yolo')),
  status        syscall_status NOT NULL DEFAULT 'running',
  reason        text,
  receipt_id    uuid REFERENCES tool_calls(id),
  snapshot_hash text,
  restored_hash text,
  started_at    timestamptz NOT NULL DEFAULT now(),
  ended_at      timestamptz,
  CHECK ((status = 'running') = (ended_at IS NULL)),
  -- N14: a rollback restores exactly the snapshotted state
  CHECK (status <> 'rolled_back' OR (snapshot_hash IS NOT NULL AND restored_hash = snapshot_hash)),
  -- N06: critical never commits
  CHECK (NOT (status = 'committed' AND risk_class = 'critical'))
);
CREATE INDEX syscalls_agent_running ON syscalls (agent_id) WHERE status = 'running';

CREATE TABLE syscall_steps (
  syscall_id uuid NOT NULL REFERENCES syscalls(id),
  step       smallint NOT NULL CHECK (step BETWEEN 1 AND 12),
  name       text NOT NULL,
  outcome    text NOT NULL CHECK (outcome IN ('pass', 'fail', 'skip')),
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (syscall_id, step)
);
CREATE TRIGGER trg_syscall_steps_append_only BEFORE UPDATE OR DELETE ON syscall_steps
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE nava_step_names (step smallint PRIMARY KEY, name text NOT NULL UNIQUE);
INSERT INTO nava_step_names VALUES
  (1, 'validate'), (2, 'authenticate'), (3, 'authorize'), (4, 'classify'), (5, 'policy'),
  (6, 'approval'), (7, 'quota'), (8, 'lock'), (9, 'snapshot'), (10, 'execute'),
  (11, 'verify'), (12, 'record');

-- N01: steps arrive in order 1..12 with their canonical names; nothing after a failed step
-- except the closing record step.
CREATE FUNCTION syscall_step_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last smallint; failed boolean; sc syscalls%ROWTYPE; appr text;
BEGIN
  IF EXISTS (SELECT 1 FROM syscalls WHERE id = NEW.syscall_id AND status <> 'running') THEN
    RAISE EXCEPTION 'N02: syscall already ended';
  END IF;
  IF (SELECT name FROM nava_step_names WHERE step = NEW.step) IS DISTINCT FROM NEW.name THEN
    RAISE EXCEPTION 'N01: step % must be named %', NEW.step, (SELECT name FROM nava_step_names WHERE step = NEW.step);
  END IF;
  SELECT max(step), bool_or(outcome = 'fail') INTO last, failed FROM syscall_steps WHERE syscall_id = NEW.syscall_id;
  IF coalesce(failed, false) THEN
    IF NEW.step <> 12 THEN
      RAISE EXCEPTION 'N01: after a failed step only step 12 (record) may follow';
    END IF;
  ELSIF NEW.step <> coalesce(last, 0) + 1 THEN
    RAISE EXCEPTION 'N01: step % out of order (last was %)', NEW.step, coalesce(last, 0);
  END IF;
  IF NEW.step = 10 AND NEW.outcome <> 'skip' THEN
    SELECT * INTO sc FROM syscalls WHERE id = NEW.syscall_id;
    IF sc.risk_class IS NULL THEN
      RAISE EXCEPTION 'N05: execute before risk classification';
    END IF;
    IF sc.risk_class = 'critical' THEN
      RAISE EXCEPTION 'N06: critical calls never execute';
    END IF;
    IF sc.risk_class = 'high' OR (sc.risk_class = 'medium' AND sc.mode = 'ask') THEN
      SELECT (detail ->> 'approval_id') INTO appr FROM syscall_steps
       WHERE syscall_id = sc.id AND step = 6 AND outcome = 'pass';
      IF appr IS NULL OR NOT EXISTS (
           SELECT 1 FROM approvals a WHERE a.id = appr::uuid AND a.status = 'used'
              AND a.tool_call_args_hash = sc.args_hash AND a.task_id = sc.task_id
              AND (a.tool IS NULL OR a.tool IN (sc.tool, regexp_replace(sc.tool, '^omni\.', '')))) THEN
        RAISE EXCEPTION 'N07: % call in % mode executes only with a consumed approval bound to its args, task and tool',
          sc.risk_class, sc.mode;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
EXCEPTION WHEN raise_exception THEN
  PERFORM audit_reject('nava.step_rejected', NEW.syscall_id::text, jsonb_build_object('step', NEW.step, 'reason', SQLERRM));
  RAISE;
END $$;
CREATE TRIGGER trg_syscall_step_guard BEFORE INSERT ON syscall_steps FOR EACH ROW EXECUTE FUNCTION syscall_step_guard();

-- N02: one terminal outcome, reached once, and only after the record step; N15/N16: a commit
-- needs a passed verify step and a receipt.
CREATE FUNCTION syscall_status_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'running' THEN
    RAISE EXCEPTION 'N02: syscall % already ended (%)', OLD.id, OLD.status;
  END IF;
  IF NEW.status = 'running' THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM syscall_steps WHERE syscall_id = NEW.id AND step = 12) THEN
    RAISE EXCEPTION 'N01: syscall cannot end before step 12 (record)';
  END IF;
  IF NEW.status = 'committed' THEN
    IF (SELECT count(*) FROM syscall_steps WHERE syscall_id = NEW.id AND outcome IN ('pass', 'skip')) <> 12 THEN
      RAISE EXCEPTION 'N15: commit needs all 12 steps passed (or skipped where not applicable)';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM syscall_steps WHERE syscall_id = NEW.id AND step = 11 AND outcome = 'pass') THEN
      RAISE EXCEPTION 'N15: commit needs a passed verify step';
    END IF;
    IF NEW.mutating AND NOT EXISTS (SELECT 1 FROM syscall_steps WHERE syscall_id = NEW.id AND step = 9 AND outcome = 'pass') THEN
      RAISE EXCEPTION 'N13: a mutation needs a snapshot before it executes';
    END IF;
    IF NEW.receipt_id IS NULL OR NOT EXISTS (
         SELECT 1 FROM tool_calls t WHERE t.id = NEW.receipt_id AND t.args_hash = NEW.args_hash
            AND t.agent_id = NEW.agent_id AND t.task_id = NEW.task_id) THEN
      RAISE EXCEPTION 'N16: commit needs its own receipt (same agent, task and args hash)';
    END IF;
  END IF;
  NEW.ended_at := now();
  RETURN NEW;
EXCEPTION WHEN raise_exception OR check_violation THEN
  PERFORM audit_reject('nava.syscall_rejected', OLD.id::text, jsonb_build_object('reason', SQLERRM));
  RAISE;
END $$;
CREATE TRIGGER trg_syscall_status_guard BEFORE UPDATE ON syscalls FOR EACH ROW EXECUTE FUNCTION syscall_status_guard();

CREATE FUNCTION syscall_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> 'running' THEN
    PERFORM audit_append(NEW.agent_id::text, 'nava.' || NEW.status, NEW.id::text,
      jsonb_build_object('tool', NEW.tool, 'task_id', NEW.task_id, 'risk_class', NEW.risk_class,
                         'reason', NEW.reason, 'receipt_id', NEW.receipt_id));
    DELETE FROM nava_locks WHERE syscall_id = NEW.id;   -- N11: no lock outlives its call
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_syscall_audit AFTER UPDATE OF status ON syscalls FOR EACH ROW EXECUTE FUNCTION syscall_audit();

-- N03: only an active agent may open a syscall.
CREATE FUNCTION syscall_caller_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM agents WHERE id = NEW.agent_id AND status = 'active') THEN
    RAISE EXCEPTION 'N03: agent % is not active', NEW.agent_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_syscall_caller_guard BEFORE INSERT ON syscalls FOR EACH ROW EXECUTE FUNCTION syscall_caller_guard();

-- N21: JIT subagents: synthesized per objective, never broader than their parent, expiring.
CREATE TABLE nava_subagents (
  agent_id        uuid PRIMARY KEY REFERENCES agents(id),
  parent_agent_id uuid NOT NULL REFERENCES agents(id),
  objective       text NOT NULL,
  expires_at      timestamptz NOT NULL,
  CHECK (agent_id <> parent_agent_id)
);
CREATE FUNCTION nava_expire_subagents() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
  UPDATE agents SET status = 'killed', updated_at = now()
   WHERE id IN (SELECT agent_id FROM nava_subagents WHERE expires_at <= now()) AND status <> 'killed';
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- N04: capabilities. An agent may call a tool unless a deny rule matches; subagents only within
-- their parent's grants (N21).
CREATE TABLE nava_denies (
  agent_id     uuid NOT NULL REFERENCES agents(id),
  tool_pattern text NOT NULL CHECK (tool_pattern ~ '^[a-z0-9_.*-]+$'),
  PRIMARY KEY (agent_id, tool_pattern)
);
CREATE FUNCTION nava_allowed(p_agent uuid, p_tool text) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT NOT EXISTS (
    SELECT 1 FROM nava_denies d
     WHERE p_tool LIKE replace(d.tool_pattern, '*', '%')
       AND d.agent_id IN (WITH RECURSIVE chain(id) AS (
             SELECT p_agent UNION SELECT s.parent_agent_id FROM nava_subagents s JOIN chain c ON s.agent_id = c.id)
           SELECT id FROM chain))
$$;

-- N08: quotas per agent (concurrent running syscalls, calls per minute).
CREATE TABLE nava_quotas (
  agent_id       uuid PRIMARY KEY REFERENCES agents(id),
  max_concurrent integer NOT NULL DEFAULT 4 CHECK (max_concurrent > 0),
  max_per_minute integer NOT NULL DEFAULT 120 CHECK (max_per_minute > 0)
);
CREATE FUNCTION nava_quota_check(p_agent uuid) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT CASE
    WHEN (SELECT count(*) FROM syscalls WHERE agent_id = p_agent AND status = 'running')
         > coalesce((SELECT max_concurrent FROM nava_quotas WHERE agent_id = p_agent), 4)
      THEN 'concurrency quota exceeded'
    WHEN (SELECT count(*) FROM syscalls WHERE agent_id = p_agent AND started_at > now() - interval '1 minute')
         > coalesce((SELECT max_per_minute FROM nava_quotas WHERE agent_id = p_agent), 120)
      THEN 'rate quota exceeded'
    WHEN (SELECT status FROM agents WHERE id = p_agent) = 'budget_halted' THEN 'budget halted (INV-08)'
  END
$$;

-- N10..N12: resource locks. One holder per resource; released when the syscall ends.
CREATE TABLE nava_locks (
  resource    text PRIMARY KEY,
  syscall_id  uuid NOT NULL REFERENCES syscalls(id),
  acquired_at timestamptz NOT NULL DEFAULT now(),
  ord         integer NOT NULL
);
-- N12: a syscall's locks are taken in sorted resource order (deadlock-free).
CREATE FUNCTION nava_lock_order_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM nava_locks WHERE syscall_id = NEW.syscall_id AND resource >= NEW.resource) THEN
    RAISE EXCEPTION 'N12: locks must be acquired in sorted order (% after a later resource)', NEW.resource;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_nava_lock_order BEFORE INSERT ON nava_locks FOR EACH ROW EXECUTE FUNCTION nava_lock_order_guard();

-- N18/N19: A2A IPC bus. The sender is the authenticated caller; a recipient reads only its own
-- messages; messages are immutable and ordered per channel.
CREATE TABLE a2a_messages (
  seq        bigserial PRIMARY KEY,
  channel    text NOT NULL CHECK (channel ~ '^[a-z0-9:_./-]{1,128}$'),
  from_agent uuid NOT NULL REFERENCES agents(id),
  to_agent   uuid NOT NULL REFERENCES agents(id),
  task_id    uuid REFERENCES tasks(id),
  body       jsonb NOT NULL,
  sent_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (octet_length(body::text) <= 65536)
);
CREATE INDEX a2a_inbox ON a2a_messages (to_agent, seq);
CREATE TRIGGER trg_a2a_append_only BEFORE UPDATE OR DELETE ON a2a_messages FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE FUNCTION a2a_send(p_from uuid, p_to uuid, p_channel text, p_body jsonb, p_task uuid DEFAULT NULL)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE s bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM agents WHERE id = p_from AND status = 'active') THEN
    RAISE EXCEPTION 'N18: sender % is not an active agent', p_from;
  END IF;
  INSERT INTO a2a_messages(channel, from_agent, to_agent, task_id, body) VALUES (p_channel, p_from, p_to, p_task, p_body)
  RETURNING seq INTO s;
  RETURN s;
END $$;

CREATE FUNCTION a2a_receive(p_agent uuid, p_after bigint DEFAULT 0, p_limit integer DEFAULT 100)
RETURNS SETOF a2a_messages LANGUAGE sql STABLE AS $$
  SELECT * FROM a2a_messages WHERE to_agent = p_agent AND seq > p_after ORDER BY seq LIMIT least(p_limit, 500)
$$;

-- N20: four-tier memory. working (per task, cleared at task end), episodic (what happened),
-- semantic (facts), procedural (how-to). Durable tiers need provenance.
CREATE TYPE memory_tier AS ENUM ('working', 'episodic', 'semantic', 'procedural');
CREATE TABLE nava_memory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    uuid NOT NULL REFERENCES agents(id),
  tier        memory_tier NOT NULL,
  task_id     uuid REFERENCES tasks(id),
  key         text NOT NULL,
  value       jsonb NOT NULL,
  source_syscall uuid REFERENCES syscalls(id),
  source_evidence uuid,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (tier <> 'working' OR task_id IS NOT NULL),
  CHECK (tier IN ('working', 'episodic') OR source_syscall IS NOT NULL OR source_evidence IS NOT NULL)
);
CREATE INDEX nava_memory_lookup ON nava_memory (agent_id, tier, key);

CREATE FUNCTION nava_clear_working_memory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state IN ('COMPLETED', 'FAILED_QC', 'CANCELLED') AND OLD.state IS DISTINCT FROM NEW.state THEN
    DELETE FROM nava_memory WHERE tier = 'working' AND task_id = NEW.id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_nava_clear_working AFTER UPDATE OF state ON tasks FOR EACH ROW EXECUTE FUNCTION nava_clear_working_memory();

-- OpenMuse durable task plans: pause / resume / retry survive restarts.
CREATE TYPE plan_status AS ENUM ('running', 'paused', 'completed', 'failed');
CREATE TABLE plans (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id   uuid NOT NULL REFERENCES agents(id),
  task_id    uuid REFERENCES tasks(id),
  objective  text NOT NULL,
  status     plan_status NOT NULL DEFAULT 'running',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE plan_steps (
  plan_id    uuid NOT NULL REFERENCES plans(id),
  idx        integer NOT NULL CHECK (idx >= 0),
  tool       text NOT NULL,
  args       jsonb NOT NULL DEFAULT '{}'::jsonb,
  status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
  attempts   integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
  syscall_id uuid REFERENCES syscalls(id),
  output     jsonb,
  PRIMARY KEY (plan_id, idx)
);

-- Agent credentials for the NAVA gateway: only digests are stored; the token itself goes to the
-- keychain (static agents) or back to the parent once (JIT subagents).
CREATE TABLE nava_tokens (
  digest     text PRIMARY KEY CHECK (digest ~ '^[0-9a-f]{64}$'),
  agent_id   uuid NOT NULL REFERENCES agents(id),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION nava_authenticate(p_digest text) RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT t.agent_id FROM nava_tokens t JOIN agents a ON a.id = t.agent_id
   WHERE t.digest = p_digest AND (t.expires_at IS NULL OR t.expires_at > now()) AND a.status = 'active'
$$;

-- Delegated execution (runtime-omni): the executor runs a tool for a syscall only while that
-- syscall is between snapshot and execute, for the same agent, task, tool and args, and cites the
-- approval the gateway consumed at step 6.
CREATE FUNCTION nava_delegation(p_syscall uuid, p_agent uuid, p_task uuid, p_tool text, p_hash text)
RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT jsonb_build_object('ok', true, 'approval_id',
           (SELECT detail ->> 'approval_id' FROM syscall_steps WHERE syscall_id = s.id AND step = 6 AND outcome = 'pass'),
           'risk_class', s.risk_class, 'mode', s.mode)
    FROM syscalls s
   WHERE s.id = p_syscall AND s.status = 'running' AND s.agent_id = p_agent AND s.task_id = p_task
     AND s.tool IN (p_tool, 'omni.' || p_tool) AND s.args_hash = p_hash
     AND (SELECT max(step) FROM syscall_steps WHERE syscall_id = s.id) = 9
     AND NOT EXISTS (SELECT 1 FROM syscall_steps WHERE syscall_id = s.id AND outcome = 'fail')
$$;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO revenueos_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO revenueos_app;
GRANT DELETE ON nava_locks, nava_memory TO revenueos_app;
REVOKE UPDATE, DELETE ON nava_tokens FROM revenueos_app;
REVOKE UPDATE, DELETE, TRUNCATE ON syscall_steps, a2a_messages FROM revenueos_app;

COMMIT;
