-- Phase 2: identity (C05, INV-09), identity-pinned egress (C17, INV-11), sandbox sessions
-- (C03/C17, INV-12), approval decisions and logged rejections (INV-06), credential preflight.
-- Every guard has an adversarial test under tests/invariants or tests/db.

BEGIN;

-- ---------------------------------------------------------------------------
-- Settings guards depend on (a table, so a session cannot override them)
-- ---------------------------------------------------------------------------
CREATE TABLE settings (
  key   text PRIMARY KEY,
  value text NOT NULL
);
INSERT INTO settings VALUES
  ('profile_root', '/var/lib/revenueos/profiles/'),
  ('identity_session_max_age_s', '300');

CREATE FUNCTION setting(p_key text) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT value FROM settings WHERE key = p_key
$$;

-- ---------------------------------------------------------------------------
-- INV-09: own email, phone, calendar and browser profile; never a human's
-- ---------------------------------------------------------------------------
ALTER TABLE agent_identities ADD COLUMN address text;
ALTER TABLE agent_identities ADD COLUMN meta jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE agent_identities ADD COLUMN rotated_from uuid REFERENCES agent_identities(id);
ALTER TABLE agent_identities ADD COLUMN retired_at timestamptz;
ALTER TABLE agent_identities ADD CONSTRAINT identity_status_valid
  CHECK (status IN ('active', 'retired', 'pending'));
CREATE UNIQUE INDEX agent_identities_unique_active_address
  ON agent_identities (kind, lower(address)) WHERE status = 'active' AND address IS NOT NULL;

-- Paths a human browser uses on Linux, macOS and Windows.
CREATE TABLE human_profile_patterns (pattern text PRIMARY KEY);
INSERT INTO human_profile_patterns VALUES
  ('/\.config/(google-chrome|chromium|BraveSoftware|microsoft-edge|vivaldi|opera)'),
  ('/\.mozilla/'), ('/snap/(chromium|firefox)/'),
  ('/Library/Application Support/(Google/Chrome|Chromium|BraveSoftware|Microsoft Edge|Firefox|Arc)'),
  ('/Library/Safari'), ('AppData/(Local|Roaming)/(Google|Microsoft|Mozilla|BraveSoftware)'),
  ('^/(home|Users|root)(/|$)');

CREATE FUNCTION identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE root text := setting('profile_root');
BEGIN
  IF NEW.kind = 'browser_profile' THEN
    IF NEW.profile_path !~ '^/' OR NEW.profile_path ~ '(^|/)\.\.?(/|$)' OR NEW.profile_path ~ '//' THEN
      RAISE EXCEPTION 'INV-09: profile path must be absolute and normalized: %', NEW.profile_path;
    END IF;
    IF EXISTS (SELECT 1 FROM human_profile_patterns p WHERE NEW.profile_path ~ p.pattern) THEN
      RAISE EXCEPTION 'INV-09: % is a human browser profile location', NEW.profile_path;
    END IF;
    IF left(NEW.profile_path, length(root)) <> root THEN
      RAISE EXCEPTION 'INV-09: profile path % is outside the agent profile root %', NEW.profile_path, root;
    END IF;
  END IF;
  IF NEW.status = 'active' THEN
    IF NEW.kind = 'email' AND (NEW.address IS NULL OR NEW.address !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$') THEN
      RAISE EXCEPTION 'INV-09: an active email identity needs a valid address';
    END IF;
    IF NEW.kind = 'phone' AND (NEW.address IS NULL OR NEW.address !~ '^\+[1-9][0-9]{6,14}$') THEN
      RAISE EXCEPTION 'INV-09: an active phone identity needs an E.164 number';
    END IF;
    IF NEW.kind = 'calendar' AND (NEW.address IS NULL OR NEW.address !~ '^https?://') THEN
      RAISE EXCEPTION 'INV-09: an active calendar identity needs a CalDAV URL';
    END IF;
  END IF;
  IF NEW.status = 'retired' AND NEW.retired_at IS NULL THEN
    NEW.retired_at := now();
  END IF;
  RETURN NEW;
EXCEPTION WHEN raise_exception THEN
  PERFORM audit_reject('identity.rejected', coalesce(NEW.agent_id::text, '?'),
                       jsonb_build_object('kind', NEW.kind, 'reason', SQLERRM));
  RAISE;
END $$;
CREATE TRIGGER trg_identity_guard BEFORE INSERT OR UPDATE ON agent_identities
  FOR EACH ROW EXECUTE FUNCTION identity_guard();

CREATE FUNCTION identity_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM audit_append('identity-service', 'identity.' || NEW.status, NEW.agent_id::text,
    jsonb_build_object('identity_id', NEW.id, 'kind', NEW.kind, 'provider', NEW.provider,
                       'address', NEW.address, 'profile_path', NEW.profile_path,
                       'rotated_from', NEW.rotated_from));
  RETURN NEW;
END $$;
CREATE TRIGGER trg_identity_log AFTER INSERT OR UPDATE OF status ON agent_identities
  FOR EACH ROW EXECUTE FUNCTION identity_log();

-- An agent may not execute a task without its own active email and browser profile.
CREATE FUNCTION executor_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state = 'EXECUTING' AND OLD.state IS DISTINCT FROM 'EXECUTING' THEN
    IF NOT EXISTS (SELECT 1 FROM agent_identities
                    WHERE agent_id = NEW.executor_agent_id AND kind = 'email' AND status = 'active')
       OR NOT EXISTS (SELECT 1 FROM agent_identities
                    WHERE agent_id = NEW.executor_agent_id AND kind = 'browser_profile' AND status = 'active') THEN
      RAISE EXCEPTION 'INV-09: executor % lacks its own active email and browser profile', NEW.executor_agent_id;
    END IF;
  END IF;
  RETURN NEW;
EXCEPTION WHEN raise_exception THEN
  PERFORM audit_reject('task.rejected', NEW.id::text, jsonb_build_object('reason', SQLERRM));
  RAISE;
END $$;
-- Named to sort after trg_task_state_guard: an illegal transition is reported as such first.
CREATE TRIGGER trg_task_state_identity_guard BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION executor_identity_guard();

-- ---------------------------------------------------------------------------
-- INV-11: per-agent / per-task egress rules, secret bindings, pinned sessions, log
-- ---------------------------------------------------------------------------
CREATE TABLE egress_rules (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id   uuid NOT NULL REFERENCES agents(id),
  task_id    uuid REFERENCES tasks(id),                 -- NULL = all of the agent's tasks
  host       text NOT NULL CHECK (host = lower(host) AND host ~ '^[a-z0-9.-]+(:[0-9]{1,5})?$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (agent_id, task_id, host)
);

CREATE TABLE secret_bindings (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  secret_ref text NOT NULL CHECK (secret_ref ~ '^(vault|keychain)://'),
  host       text NOT NULL CHECK (host = lower(host)),
  header     text NOT NULL CHECK (header ~ '^[a-z0-9-]+$'),
  format     text NOT NULL DEFAULT '{}' CHECK (position('{}' in format) > 0),
  agent_ids  uuid[],                                    -- NULL = any agent allowed to reach the host
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (host, header)
);

-- A session is the unit of identity pinning: the supervisor's forwarder signs every request
-- with the session id, and egress-authz accepts it only while the row is open and its agent
-- and task match the request.
CREATE TABLE egress_sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    uuid NOT NULL REFERENCES agents(id),
  task_id     uuid REFERENCES tasks(id),
  socket_path text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  closed_at   timestamptz
);

CREATE TABLE egress_log (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       uuid REFERENCES egress_sessions(id),
  agent_id         uuid REFERENCES agents(id),
  task_id          uuid REFERENCES tasks(id),
  method           text NOT NULL,
  host             text NOT NULL,
  path_hash        text NOT NULL,
  decision         text NOT NULL CHECK (decision IN ('allow', 'deny')),
  reason           text NOT NULL,
  injected_secrets integer NOT NULL DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX egress_log_agent ON egress_log (agent_id, created_at);
CREATE TRIGGER trg_egress_log_append_only BEFORE UPDATE OR DELETE ON egress_log
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE FUNCTION egress_log_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM audit_append(coalesce(NEW.agent_id::text, 'unknown'), 'egress.' || NEW.decision, NEW.host,
    jsonb_build_object('egress_id', NEW.id, 'reason', NEW.reason, 'method', NEW.method,
                       'task_id', NEW.task_id, 'session_id', NEW.session_id,
                       'path_sha256', NEW.path_hash, 'injected_secrets', NEW.injected_secrets));
  RETURN NEW;
END $$;
CREATE TRIGGER trg_egress_log_audit AFTER INSERT ON egress_log
  FOR EACH ROW EXECUTE FUNCTION egress_log_audit();

-- ---------------------------------------------------------------------------
-- INV-12: sandbox sessions; a commit to the real workspace is an approved boundary
-- ---------------------------------------------------------------------------
CREATE TABLE sandbox_sessions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id       uuid NOT NULL REFERENCES agents(id),
  task_id        uuid REFERENCES tasks(id),
  backend        text NOT NULL CHECK (backend IN ('bubblewrap', 'seatbelt')),
  yolo           boolean NOT NULL DEFAULT false,
  workspace      text NOT NULL,
  shadow_path    text NOT NULL,
  command_hash   text NOT NULL CHECK (command_hash ~ '^[0-9a-f]{64}$'),
  status         text NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running', 'finished', 'failed', 'blocked', 'timeout', 'committed', 'discarded')),
  exit_code      integer,
  reason         text,
  changeset_hash text,
  approval_id    uuid REFERENCES approvals(id),
  started_at     timestamptz NOT NULL DEFAULT now(),
  ended_at       timestamptz,
  CHECK (status <> 'committed' OR (approval_id IS NOT NULL AND changeset_hash IS NOT NULL))
);

CREATE FUNCTION sandbox_commit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status = 'committed' AND OLD.status <> 'committed' THEN
    IF OLD.status <> 'finished' THEN
      RAISE EXCEPTION 'INV-12: only a finished session can be committed (was %)', OLD.status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM approvals a WHERE a.id = NEW.approval_id AND a.status = 'used'
                     AND a.tool_call_args_hash = NEW.changeset_hash) THEN
      RAISE EXCEPTION 'INV-12: workspace commit needs a consumed approval bound to its changeset';
    END IF;
  END IF;
  IF OLD.status IN ('committed', 'discarded', 'blocked') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'INV-12: session is closed (%)', OLD.status;
  END IF;
  RETURN NEW;
EXCEPTION WHEN raise_exception OR check_violation THEN
  PERFORM audit_reject('sandbox.rejected', OLD.id::text, jsonb_build_object('reason', SQLERRM));
  RAISE;
END $$;
CREATE TRIGGER trg_sandbox_commit_guard BEFORE UPDATE ON sandbox_sessions
  FOR EACH ROW EXECUTE FUNCTION sandbox_commit_guard();

CREATE FUNCTION sandbox_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
    PERFORM audit_append(NEW.agent_id::text, 'sandbox.' || NEW.status, NEW.id::text,
      jsonb_build_object('task_id', NEW.task_id, 'yolo', NEW.yolo, 'backend', NEW.backend,
                         'command_hash', NEW.command_hash, 'exit_code', NEW.exit_code,
                         'reason', NEW.reason, 'changeset_hash', NEW.changeset_hash));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_sandbox_log AFTER INSERT OR UPDATE ON sandbox_sessions
  FOR EACH ROW EXECUTE FUNCTION sandbox_log();

-- ---------------------------------------------------------------------------
-- INV-06: approval requests, decisions, and consumption with a logged reason
-- ---------------------------------------------------------------------------
ALTER TABLE approvals ADD COLUMN mcp_server   text;
ALTER TABLE approvals ADD COLUMN tool         text;
ALTER TABLE approvals ADD COLUMN args_preview jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE approvals ADD COLUMN risk_class   risk_class;
ALTER TABLE approvals ADD COLUMN decided_at   timestamptz;

-- Single decision, by someone other than the requester, before expiry. Rejected attempts are
-- audited autonomously so the reason survives the rollback.
CREATE FUNCTION approval_decide(p_id uuid, p_approver text, p_approve boolean)
RETURNS approval_status LANGUAGE plpgsql AS $$
DECLARE a approvals%ROWTYPE; result approval_status;
BEGIN
  SELECT * INTO a FROM approvals WHERE id = p_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'INV-06: approval not found'; END IF;
  IF a.status <> 'pending' THEN RAISE EXCEPTION 'INV-06: approval already %', a.status; END IF;
  IF a.expires_at <= now() THEN RAISE EXCEPTION 'INV-06: approval expired'; END IF;
  IF a.requested_by = p_approver THEN
    RAISE EXCEPTION 'INV-06: separation of duties: requester cannot decide';
  END IF;
  result := CASE WHEN p_approve THEN 'approved'::approval_status ELSE 'rejected'::approval_status END;
  UPDATE approvals SET status = result, approved_by = p_approver, decided_at = now() WHERE id = p_id;
  RETURN result;
EXCEPTION WHEN raise_exception THEN
  PERFORM audit_reject('approval.decide_rejected', p_id::text,
                       jsonb_build_object('approver', p_approver, 'reason', SQLERRM));
  RAISE;
END $$;

-- Binds an approval to the exact args hash and, when given, the task and tool it was requested
-- for: an approval for one tool cannot be spent on another tool with identical arguments.
-- True only for an approved, unexpired, unused match; every refusal records why.
CREATE FUNCTION consume_approval(p_approval uuid, p_args_hash text, p_task uuid, p_tool text) RETURNS boolean
LANGUAGE plpgsql AS $$
DECLARE a approvals%ROWTYPE; why text;
BEGIN
  SELECT * INTO a FROM approvals WHERE id = p_approval FOR UPDATE;
  why := CASE
    WHEN NOT FOUND                            THEN 'not found'
    WHEN a.status = 'used'                    THEN 'reuse: already used'
    WHEN a.status <> 'approved'               THEN 'not approved (' || a.status || ')'
    WHEN a.expires_at <= now()                THEN 'expired'
    WHEN a.tool_call_args_hash <> p_args_hash THEN 'args hash mismatch'
    WHEN p_task IS NOT NULL AND a.task_id <> p_task THEN 'bound to a different task'
    WHEN p_tool IS NOT NULL AND a.tool IS NOT NULL AND a.tool <> p_tool THEN 'bound to a different tool'
  END;
  IF why IS NOT NULL THEN
    PERFORM audit_append(coalesce(nullif(current_setting('revenueos.actor', true), ''), session_user),
      'approval.consume_rejected', coalesce(p_approval::text, '?'),
      jsonb_build_object('reason', why, 'presented_hash', p_args_hash, 'task_id', p_task, 'tool', p_tool));
    RETURN false;
  END IF;
  UPDATE approvals SET status = 'used', used_at = now() WHERE id = p_approval;
  RETURN true;
END $$;

-- Replaces the Phase 1 two-argument form (same contract), now with logged reasons.
CREATE OR REPLACE FUNCTION consume_approval(p_approval uuid, p_args_hash text) RETURNS boolean
LANGUAGE sql AS $$ SELECT consume_approval(p_approval, p_args_hash, NULL::uuid, NULL::text) $$;

CREATE FUNCTION approval_expire_sweep() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
  UPDATE approvals SET status = 'expired'
   WHERE status IN ('pending', 'approved') AND expires_at <= now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- ---------------------------------------------------------------------------
-- Credential preflight (READY / UNCONFIGURED / DEGRADED per integration)
-- ---------------------------------------------------------------------------
CREATE FUNCTION credential_report(p_integration text, p_ref text, p_status credential_state)
RETURNS void LANGUAGE sql AS $$
  INSERT INTO credential_status(integration, secret_ref, status, checked_at)
  VALUES (p_integration, p_ref, p_status, now())
  ON CONFLICT (integration, secret_ref) DO UPDATE SET status = EXCLUDED.status, checked_at = now()
$$;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO revenueos_app;
REVOKE UPDATE, DELETE, TRUNCATE ON egress_log FROM revenueos_app;
REVOKE INSERT, UPDATE, DELETE ON settings, human_profile_patterns FROM revenueos_app;

COMMIT;
