-- RevenueOS Phase 1 core schema.
-- Enforces INV-01, INV-02, INV-03, INV-04 at the database layer, plus the
-- task state machine, the hash-chained audit ledger, and approval single-use
-- (INV-06 storage half). Application checks are defense in depth only.

BEGIN;

-- ---------------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------------
CREATE TYPE agent_status      AS ENUM ('active', 'paused', 'budget_halted', 'killed');
CREATE TYPE identity_kind     AS ENUM ('email', 'phone', 'calendar', 'browser_profile');
CREATE TYPE decomposition_kind AS ENUM ('spec', 'plan', 'rules');
CREATE TYPE task_state AS ENUM (
  'DRAFT', 'RESEARCHED', 'PLANNED', 'AWAITING_APPROVAL', 'EXECUTING',
  'EVIDENCE_SUBMITTED', 'VERIFYING', 'QC_PASSED', 'COMPLETED',
  'BLOCKED', 'FAILED_QC', 'CANCELLED', 'BUDGET_HALTED', 'AWAITING_HUMAN_APPROVAL'
);
-- Ordered weakest -> strongest so tier comparisons work: L1 < L4.
CREATE TYPE oracle_tier       AS ENUM ('L1', 'L2', 'L3', 'L4');
CREATE TYPE verify_method     AS ENUM ('gitreins', 'veripipe', 'evalforge', 'manual');
CREATE TYPE verify_method_class AS ENUM ('deterministic', 'structural', 'terminal_state', 'reproduction', 'llm');
CREATE TYPE verdict           AS ENUM ('PASS', 'FAIL', 'VETO', 'DO_NOT_FILE');
CREATE TYPE risk_class        AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE install_status    AS ENUM ('experimental', 'approved', 'production');
CREATE TYPE resolution_mode   AS ENUM ('upstream', 'upstream-api', 'native');
CREATE TYPE approval_status   AS ENUM ('pending', 'approved', 'rejected', 'used', 'expired');
CREATE TYPE skill_status      AS ENUM ('canary', 'promoted', 'retired');
CREATE TYPE learning_track    AS ENUM ('A', 'B');
CREATE TYPE cohort            AS ENUM ('canary', 'holdout');
CREATE TYPE credential_state  AS ENUM ('READY', 'UNCONFIGURED', 'DEGRADED');
CREATE TYPE gate_status       AS ENUM ('PENDING', 'PASSED', 'FAILED');
CREATE TYPE trainer_kind      AS ENUM ('agentjet', 'openforgerl', 'orchard');

-- ---------------------------------------------------------------------------
-- Agents and identity
-- ---------------------------------------------------------------------------
CREATE TABLE agents (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                text NOT NULL UNIQUE,
  role                text NOT NULL,
  framework           text NOT NULL,
  model_router_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  budget_monthly      numeric(14,4) NOT NULL CHECK (budget_monthly >= 0),
  budget_used         numeric(14,4) NOT NULL DEFAULT 0 CHECK (budget_used >= 0),
  status              agent_status NOT NULL DEFAULT 'active',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_identities (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id     uuid NOT NULL REFERENCES agents(id),
  kind         identity_kind NOT NULL,
  provider     text NOT NULL,
  secret_ref   text,             -- vault path / keychain key, never a literal
  profile_path text UNIQUE,      -- INV-09: no two agents share a browser profile
  status       text NOT NULL DEFAULT 'active',
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CHECK (secret_ref IS NULL OR secret_ref ~ '^(vault|keychain)://'),
  CHECK (kind <> 'browser_profile' OR profile_path IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- Research, premise, projects
-- ---------------------------------------------------------------------------
CREATE TABLE research_runs (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  target                text NOT NULL,
  pack                  text NOT NULL,
  sources               jsonb NOT NULL DEFAULT '[]'::jsonb,
  canvas                jsonb NOT NULL DEFAULT '{}'::jsonb,
  claim_labels_enforced boolean NOT NULL DEFAULT true CHECK (claim_labels_enforced),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sources (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  research_run_id uuid NOT NULL REFERENCES research_runs(id),
  url             text NOT NULL,
  retrieved_at    timestamptz NOT NULL,
  content_hash    text NOT NULL,
  tier            smallint NOT NULL CHECK (tier BETWEEN 1 AND 5)
);

CREATE TABLE premise_bundles (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  research_run_id uuid NOT NULL REFERENCES research_runs(id),
  claims          jsonb NOT NULL,
  missing_data    jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  -- Every claim must carry a label (C07). Full source-match check lives in services/research.
  CHECK (jsonb_typeof(claims) = 'array'),
  CHECK (jsonb_typeof(missing_data) = 'array')
);

CREATE FUNCTION premise_claims_labeled() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c jsonb;
BEGIN
  FOR c IN SELECT * FROM jsonb_array_elements(NEW.claims) LOOP
    IF NOT (c ? 'label') OR (c->>'label') NOT IN ('verified', 'inferred', 'missing') THEN
      RAISE EXCEPTION 'C07: every claim needs label verified|inferred|missing: %', c;
    END IF;
    IF c->>'label' = 'verified'
       AND (NOT (c ? 'source_ids') OR jsonb_array_length(c->'source_ids') = 0) THEN
      RAISE EXCEPTION 'C07: verified claim without source_ids: %', c;
    END IF;
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_premise_claims_labeled BEFORE INSERT OR UPDATE ON premise_bundles
  FOR EACH ROW EXECUTE FUNCTION premise_claims_labeled();

CREATE TABLE projects (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                  text NOT NULL,
  business_line         text NOT NULL,
  premise_bundle_id     uuid REFERENCES premise_bundles(id),
  framework_contract_id uuid,
  status                text NOT NULL DEFAULT 'draft',
  target_revenue        numeric(14,2),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  -- C07: a project cannot leave draft without a premise bundle.
  CHECK (status = 'draft' OR premise_bundle_id IS NOT NULL)
);

CREATE TABLE framework_contracts (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES projects(id),
  framework           text NOT NULL,
  routing_model       text NOT NULL,
  data_layer          text NOT NULL,
  auth_model          text NOT NULL,
  deployment_target   text NOT NULL,
  generator           text NOT NULL,
  acceptance_criteria jsonb NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE projects ADD CONSTRAINT projects_framework_contract_fk
  FOREIGN KEY (framework_contract_id) REFERENCES framework_contracts(id);

CREATE TABLE decompositions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES projects(id),
  kind        decomposition_kind NOT NULL,
  content     text NOT NULL,
  version     integer NOT NULL CHECK (version > 0),
  approved_by text,
  approved_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, kind, version)
);

CREATE TABLE milestones (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES projects(id),
  name        text NOT NULL,
  order_index integer NOT NULL,
  status      text NOT NULL DEFAULT 'open',
  UNIQUE (project_id, order_index)
);

CREATE TABLE slices (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  milestone_id uuid NOT NULL REFERENCES milestones(id),
  name         text NOT NULL,
  order_index  integer NOT NULL,
  status       text NOT NULL DEFAULT 'open',
  UNIQUE (milestone_id, order_index)
);

CREATE TABLE design_directions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL REFERENCES projects(id),
  direction       text NOT NULL,
  rationale       text NOT NULL CHECK (length(rationale) >= 40),  -- D2: written rationale
  palette_oklch   jsonb NOT NULL,
  fonts           jsonb NOT NULL,
  radius_scale    jsonb NOT NULL,
  knowledge_query jsonb NOT NULL,                                  -- D3
  committed_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE websites (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          uuid NOT NULL REFERENCES projects(id),
  repo_path           text NOT NULL,
  preview_url         text,
  design_direction_id uuid REFERENCES design_directions(id),
  gate_status         gate_status NOT NULL DEFAULT 'PENDING',
  gate_report         jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Tasks, state machine, evidence, verification
-- ---------------------------------------------------------------------------
CREATE TABLE tasks (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id           uuid REFERENCES projects(id),
  slice_id             uuid REFERENCES slices(id),
  website_id           uuid REFERENCES websites(id),
  premise_bundle_id    uuid REFERENCES premise_bundles(id),
  objective            text NOT NULL,
  task_class           text NOT NULL,
  acceptance_criteria  jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_oracle_tier oracle_tier NOT NULL DEFAULT 'L2',
  assigned_agent_id    uuid REFERENCES agents(id),
  executor_agent_id    uuid REFERENCES agents(id),
  verifier_agent_id    uuid REFERENCES agents(id),
  state                task_state NOT NULL DEFAULT 'DRAFT',
  resume_state         task_state,
  verification_id      uuid,
  cost_estimate        numeric(14,4),
  cost_actual          numeric(14,4) NOT NULL DEFAULT 0,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  completed_at         timestamptz,
  -- INV-01 (structural half; the trigger proves the verdict)
  CONSTRAINT inv01_completed_has_verification
    CHECK (state <> 'COMPLETED' OR (verification_id IS NOT NULL AND completed_at IS NOT NULL)),
  -- INV-03 (same-row half; the verifications trigger covers the other)
  CONSTRAINT inv03_verifier_not_executor
    CHECK (verifier_agent_id IS NULL OR executor_agent_id IS NULL
           OR verifier_agent_id <> executor_agent_id),
  CHECK (task_class <> 'website' OR website_id IS NOT NULL OR state IN ('DRAFT','RESEARCHED','CANCELLED'))
);
-- Tasks must be born DRAFT.
CREATE FUNCTION task_born_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state <> 'DRAFT' OR NEW.verification_id IS NOT NULL OR NEW.completed_at IS NOT NULL THEN
    RAISE EXCEPTION 'state machine: tasks are created in DRAFT with no verification';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_task_born_draft BEFORE INSERT ON tasks
  FOR EACH ROW EXECUTE FUNCTION task_born_draft();

CREATE TABLE task_events (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id    uuid NOT NULL REFERENCES tasks(id),
  event_type text NOT NULL,
  actor      text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     uuid NOT NULL REFERENCES tasks(id),
  kind        text NOT NULL,
  uri         text NOT NULL,
  hash        text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
  oracle_tier oracle_tier NOT NULL,
  produced_by text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE verifications (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id           uuid NOT NULL REFERENCES tasks(id),
  verifier_agent_id uuid NOT NULL REFERENCES agents(id),
  method            verify_method NOT NULL,
  method_class      verify_method_class NOT NULL,
  verdict           verdict NOT NULL,
  tier              oracle_tier NOT NULL,
  details           jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  -- INV-04, row-local form
  CONSTRAINT inv04_llm_never_confirms CHECK (NOT (method_class = 'llm' AND verdict = 'PASS'))
);
ALTER TABLE tasks ADD CONSTRAINT tasks_verification_fk
  FOREIGN KEY (verification_id) REFERENCES verifications(id);

-- INV-03: verifier identity must differ from the task's executor, at insert time.
CREATE FUNCTION verification_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE exec_id uuid;
BEGIN
  SELECT executor_agent_id INTO exec_id FROM tasks WHERE id = NEW.task_id;
  IF exec_id IS NULL THEN
    RAISE EXCEPTION 'INV-03: task % has no executor; cannot verify', NEW.task_id;
  END IF;
  IF NEW.verifier_agent_id = exec_id THEN
    RAISE EXCEPTION 'INV-03: verifier equals executor on task %', NEW.task_id;
  END IF;
  IF NEW.method_class = 'llm' AND NEW.verdict = 'PASS' THEN
    RAISE EXCEPTION 'INV-04: an LLM verifier may veto but never confirm';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_verification_guard BEFORE INSERT ON verifications
  FOR EACH ROW EXECUTE FUNCTION verification_guard();

-- Allowed main-path and branch transitions. Pause states (BLOCKED,
-- BUDGET_HALTED, AWAITING_HUMAN_APPROVAL) resume only to resume_state.
CREATE TABLE task_transitions (
  from_state task_state NOT NULL,
  to_state   task_state NOT NULL,
  PRIMARY KEY (from_state, to_state)
);
INSERT INTO task_transitions VALUES
  ('DRAFT','RESEARCHED'), ('RESEARCHED','PLANNED'), ('PLANNED','AWAITING_APPROVAL'),
  ('AWAITING_APPROVAL','EXECUTING'), ('EXECUTING','EVIDENCE_SUBMITTED'),
  ('EVIDENCE_SUBMITTED','VERIFYING'), ('VERIFYING','QC_PASSED'), ('VERIFYING','FAILED_QC'),
  ('FAILED_QC','EXECUTING'), ('QC_PASSED','COMPLETED');

CREATE FUNCTION task_is_active(s task_state) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT s IN ('DRAFT','RESEARCHED','PLANNED','AWAITING_APPROVAL','EXECUTING',
               'EVIDENCE_SUBMITTED','VERIFYING','QC_PASSED','FAILED_QC')
$$;
CREATE FUNCTION task_is_paused(s task_state) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
  SELECT s IN ('BLOCKED','BUDGET_HALTED','AWAITING_HUMAN_APPROVAL')
$$;

CREATE FUNCTION task_state_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  ok boolean := false;
  v  verifications%ROWTYPE;
BEGIN
  IF NEW.state = OLD.state THEN
    -- Non-state updates may not smuggle in completion fields.
    IF NEW.verification_id IS DISTINCT FROM OLD.verification_id AND OLD.state <> 'VERIFYING' THEN
      RAISE EXCEPTION 'state machine: verification_id may be linked only while VERIFYING';
    END IF;
    IF NEW.completed_at IS DISTINCT FROM OLD.completed_at THEN
      RAISE EXCEPTION 'state machine: completed_at is set only by the COMPLETED transition';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.state IN ('COMPLETED','CANCELLED') THEN
    RAISE EXCEPTION 'state machine: % is terminal', OLD.state;
  END IF;

  -- Legality
  IF NEW.state = 'CANCELLED' THEN
    ok := true;
  ELSIF task_is_paused(NEW.state) THEN
    ok := task_is_active(OLD.state);
    IF ok THEN NEW.resume_state := OLD.state; END IF;
  ELSIF task_is_paused(OLD.state) THEN
    ok := (NEW.state = OLD.resume_state)
          OR (OLD.state = 'BLOCKED' AND NEW.state = 'EXECUTING' AND OLD.resume_state = 'FAILED_QC');
    IF ok THEN NEW.resume_state := NULL; END IF;
  ELSE
    ok := EXISTS (SELECT 1 FROM task_transitions
                   WHERE from_state = OLD.state AND to_state = NEW.state);
  END IF;
  IF NOT ok THEN
    RAISE EXCEPTION 'state machine: illegal transition % -> %', OLD.state, NEW.state;
  END IF;

  -- Guards per transition
  IF NEW.state = 'RESEARCHED' AND NEW.premise_bundle_id IS NULL THEN
    RAISE EXCEPTION 'C07: premise bundle required to enter RESEARCHED';
  END IF;

  IF NEW.state = 'PLANNED' THEN
    IF jsonb_typeof(NEW.acceptance_criteria) <> 'array'
       OR jsonb_array_length(NEW.acceptance_criteria) = 0 THEN
      RAISE EXCEPTION 'C11: machine-checkable acceptance criteria required to enter PLANNED';
    END IF;
    IF NEW.task_class = 'website' AND NOT EXISTS (
         SELECT 1 FROM projects p WHERE p.id = NEW.project_id AND p.framework_contract_id IS NOT NULL) THEN
      RAISE EXCEPTION 'D1: website task requires a framework contract before PLANNED';
    END IF;
  END IF;

  IF NEW.state = 'EXECUTING' AND NEW.executor_agent_id IS NULL THEN
    RAISE EXCEPTION 'state machine: executor required to enter EXECUTING';
  END IF;

  IF NEW.state = 'EVIDENCE_SUBMITTED' THEN
    IF NOT EXISTS (SELECT 1 FROM evidence e
                    WHERE e.task_id = NEW.id AND e.oracle_tier >= NEW.required_oracle_tier) THEN
      RAISE EXCEPTION 'C11: evidence bundle does not meet required tier %', NEW.required_oracle_tier;
    END IF;
    IF NEW.task_class = 'website' AND NOT EXISTS (
         SELECT 1 FROM websites w WHERE w.id = NEW.website_id AND w.gate_status = 'PASSED') THEN
      RAISE EXCEPTION 'INV-13: website design gate has not PASSED';
    END IF;
  END IF;

  IF NEW.state = 'VERIFYING' THEN
    IF NEW.verifier_agent_id IS NULL OR NEW.verifier_agent_id = NEW.executor_agent_id THEN
      RAISE EXCEPTION 'INV-03: distinct verifier required to enter VERIFYING';
    END IF;
  END IF;

  IF NEW.state IN ('QC_PASSED', 'COMPLETED') THEN
    SELECT * INTO v FROM verifications WHERE id = NEW.verification_id;
    IF NOT FOUND
       OR v.task_id <> NEW.id
       OR v.verdict <> 'PASS'
       OR v.method_class = 'llm'
       OR v.tier < NEW.required_oracle_tier
       OR v.verifier_agent_id = NEW.executor_agent_id THEN
      RAISE EXCEPTION 'INV-01/INV-04: % requires a deterministic PASS verification at tier >= %',
        NEW.state, NEW.required_oracle_tier;
    END IF;
  END IF;

  IF NEW.state = 'FAILED_QC' THEN
    NEW.verification_id := NULL;
  END IF;
  IF NEW.state = 'COMPLETED' THEN
    NEW.completed_at := now();
  ELSIF NEW.completed_at IS NOT NULL THEN
    RAISE EXCEPTION 'state machine: completed_at only on COMPLETED';
  END IF;

  NEW.updated_at := now();
  RETURN NEW;
END $$;
CREATE TRIGGER trg_task_state_guard BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION task_state_guard();

-- ---------------------------------------------------------------------------
-- Tools, approvals, receipts (INV-02, INV-06)
-- ---------------------------------------------------------------------------
CREATE TABLE tool_registries (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source      text NOT NULL,
  snapshot_at timestamptz NOT NULL
);

CREATE TABLE tool_installations (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mcp_server_name    text NOT NULL,
  registry_source    text NOT NULL,
  version            text NOT NULL,
  checksum           text NOT NULL,
  license            text NOT NULL,
  resolution_mode    resolution_mode NOT NULL,
  policy_score       jsonb NOT NULL DEFAULT '{}'::jsonb,
  status             install_status NOT NULL DEFAULT 'experimental',
  installed_by_agent uuid REFERENCES agents(id),
  approved_by        text,
  health_status      text NOT NULL DEFAULT 'UNKNOWN',
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mcp_server_name, version),
  CHECK (status = 'experimental' OR approved_by IS NOT NULL)
);

CREATE TABLE approvals (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id             uuid NOT NULL REFERENCES tasks(id),
  tool_call_args_hash text NOT NULL CHECK (tool_call_args_hash ~ '^[0-9a-f]{64}$'),
  requested_by        text NOT NULL,
  approved_by         text,
  expires_at          timestamptz NOT NULL,
  used_at             timestamptz,
  status              approval_status NOT NULL DEFAULT 'pending',
  created_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (approved_by IS NULL OR approved_by <> requested_by),   -- separation of duties
  CHECK (status NOT IN ('approved','used') OR approved_by IS NOT NULL),
  CHECK ((status = 'used') = (used_at IS NOT NULL))
);

-- Atomically consume an approval: single use, unexpired, bound to exact args hash.
CREATE FUNCTION consume_approval(p_approval uuid, p_args_hash text) RETURNS boolean
LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
  UPDATE approvals SET status = 'used', used_at = now()
   WHERE id = p_approval AND status = 'approved' AND used_at IS NULL
     AND expires_at > now() AND tool_call_args_hash = p_args_hash;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n = 1;
END $$;

CREATE TABLE tool_calls (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id       uuid NOT NULL REFERENCES tasks(id),
  agent_id      uuid NOT NULL REFERENCES agents(id),
  mcp_server    text NOT NULL,
  tool          text NOT NULL,
  args_hash     text NOT NULL CHECK (args_hash ~ '^[0-9a-f]{64}$'),
  args_redacted jsonb NOT NULL,
  result_hash   text CHECK (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$'),
  latency_ms    integer NOT NULL CHECK (latency_ms >= 0),
  cost          numeric(14,6) NOT NULL CHECK (cost >= 0),
  risk_class    risk_class NOT NULL,
  approval_id   uuid REFERENCES approvals(id),
  verdict       text NOT NULL,
  trace_id      text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- INV-06 at the receipt layer: a high/critical receipt must cite a consumed
-- approval for exactly these arguments.
CREATE FUNCTION tool_call_approval_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.risk_class IN ('high','critical') THEN
    IF NEW.approval_id IS NULL OR NOT EXISTS (
         SELECT 1 FROM approvals a
          WHERE a.id = NEW.approval_id AND a.status = 'used'
            AND a.tool_call_args_hash = NEW.args_hash AND a.task_id = NEW.task_id) THEN
      RAISE EXCEPTION 'INV-06: % tool call without a consumed, hash-bound approval', NEW.risk_class;
    END IF;
    IF EXISTS (SELECT 1 FROM tool_calls t WHERE t.approval_id = NEW.approval_id) THEN
      RAISE EXCEPTION 'INV-06: approval % already used by another call', NEW.approval_id;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_tool_call_approval_guard BEFORE INSERT ON tool_calls
  FOR EACH ROW EXECUTE FUNCTION tool_call_approval_guard();

-- ---------------------------------------------------------------------------
-- Budgets, timelines, marketing, learning, registry
-- ---------------------------------------------------------------------------
CREATE TABLE budgets (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id uuid NOT NULL REFERENCES agents(id),
  period   text NOT NULL,                         -- e.g. 2026-11
  "limit"  numeric(14,4) NOT NULL CHECK ("limit" >= 0),
  used     numeric(14,4) NOT NULL DEFAULT 0 CHECK (used >= 0),
  reserved numeric(14,4) NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  UNIQUE (agent_id, period),
  CHECK (used + reserved <= "limit")               -- INV-08 storage half
);

CREATE TABLE timelines (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thing_type text NOT NULL,
  thing_id   text NOT NULL,
  UNIQUE (thing_type, thing_id)
);
CREATE TABLE timeline_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  timeline_id uuid NOT NULL REFERENCES timelines(id),
  event_type  text NOT NULL,
  payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE campaigns (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  platform_set        text[] NOT NULL,
  content_hash        text NOT NULL,
  approved_asset_hash text,
  scheduled_at        timestamptz,
  published           jsonb NOT NULL DEFAULT '{}'::jsonb,
  analytics           jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE contacts (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source          text NOT NULL,
  email           text NOT NULL,
  segments        text[] NOT NULL DEFAULT '{}',
  lifecycle_stage text NOT NULL DEFAULT 'lead',
  consent_status  text NOT NULL DEFAULT 'unknown',
  lawful_basis    text,
  suppressed      boolean NOT NULL DEFAULT false
);

CREATE TABLE leads (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company         text NOT NULL,
  contact_id      uuid REFERENCES contacts(id),
  research_run_id uuid REFERENCES research_runs(id),
  status          text NOT NULL DEFAULT 'new',
  owner_agent_id  uuid REFERENCES agents(id)
);

CREATE TABLE skills (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id     uuid NOT NULL REFERENCES agents(id),
  name         text NOT NULL,
  instructions text NOT NULL,
  version      integer NOT NULL,
  status       skill_status NOT NULL DEFAULT 'canary',
  lift         numeric,
  lift_ci_low  numeric,
  track        learning_track NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agent_id, name, version),
  -- INV-14 storage half: promotion needs measured positive lift
  CHECK (status <> 'promoted' OR (lift IS NOT NULL AND lift_ci_low IS NOT NULL AND lift_ci_low > 0))
);
CREATE TABLE skill_runs (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id uuid NOT NULL REFERENCES skills(id),
  task_id  uuid NOT NULL REFERENCES tasks(id),
  cohort   cohort NOT NULL,
  outcome  text NOT NULL
);
CREATE TABLE model_checkpoints (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role            text NOT NULL,
  base_model      text NOT NULL,
  trainer         trainer_kind NOT NULL,
  dataset_version text NOT NULL,
  eval_report     jsonb NOT NULL DEFAULT '{}'::jsonb,
  status          skill_status NOT NULL DEFAULT 'canary'
);

CREATE TABLE pins (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_name    text NOT NULL UNIQUE,
  repo_url        text,
  commit_sha      text CHECK (commit_sha IS NULL OR commit_sha ~ '^[0-9a-f]{40}$'),
  license         text,
  resolution_mode resolution_mode NOT NULL,
  evidence_uri    text NOT NULL,
  notes           text,
  -- No fabricated pins: upstream needs URL + SHA + license
  CHECK (resolution_mode <> 'upstream' OR (repo_url IS NOT NULL AND commit_sha IS NOT NULL AND license IS NOT NULL))
);
CREATE TABLE parity_entries (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category   text NOT NULL,
  tool       text NOT NULL,
  license    text NOT NULL,
  activity   text,
  mcp_status text,
  notes      text
);
CREATE TABLE credential_status (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  integration text NOT NULL,
  secret_ref  text NOT NULL CHECK (secret_ref ~ '^(vault|keychain)://'),
  status      credential_state NOT NULL,
  checked_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (integration, secret_ref)
);

-- ---------------------------------------------------------------------------
-- Audit ledger: append-only, hash-chained, serialized (C18)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seq        bigint NOT NULL UNIQUE,
  prev_hash  text NOT NULL,
  hash       text NOT NULL UNIQUE,
  actor      text NOT NULL,
  action     text NOT NULL,
  target     text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION audit_row_hash(p_prev text, p_seq bigint, p_actor text, p_action text,
                               p_target text, p_payload jsonb, p_at timestamptz)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT encode(sha256(convert_to(
    p_prev || '|' || jsonb_build_object(
      'seq', p_seq, 'actor', p_actor, 'action', p_action, 'target', p_target,
      'payload', p_payload,
      'at', to_char(p_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))::text,
    'UTF8')), 'hex')
$$;

-- Callers supply actor/action/target/payload only; seq and hashes are computed
-- here under an advisory lock so the chain cannot fork or be forged.
CREATE FUNCTION audit_chain() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE last audit_log%ROWTYPE;
BEGIN
  PERFORM pg_advisory_xact_lock(7426001);
  SELECT * INTO last FROM audit_log ORDER BY seq DESC LIMIT 1;
  NEW.created_at := clock_timestamp();
  IF NOT FOUND THEN
    NEW.seq := 1;
    NEW.prev_hash := repeat('0', 64);
  ELSE
    NEW.seq := last.seq + 1;
    NEW.prev_hash := last.hash;
  END IF;
  NEW.hash := audit_row_hash(NEW.prev_hash, NEW.seq, NEW.actor, NEW.action,
                             NEW.target, NEW.payload, NEW.created_at);
  RETURN NEW;
END $$;
CREATE TRIGGER trg_audit_chain BEFORE INSERT ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_chain();

-- Returns the first seq whose link or hash is broken, or NULL if intact.
CREATE FUNCTION audit_verify() RETURNS bigint LANGUAGE plpgsql STABLE AS $$
DECLARE r audit_log%ROWTYPE; prev text := repeat('0', 64); expect bigint := 1;
BEGIN
  FOR r IN SELECT * FROM audit_log ORDER BY seq LOOP
    IF r.seq <> expect OR r.prev_hash <> prev
       OR r.hash <> audit_row_hash(r.prev_hash, r.seq, r.actor, r.action, r.target, r.payload, r.created_at) THEN
      RETURN r.seq;
    END IF;
    prev := r.hash; expect := expect + 1;
  END LOOP;
  RETURN NULL;
END $$;

CREATE FUNCTION audit_append(p_actor text, p_action text, p_target text, p_payload jsonb)
RETURNS void LANGUAGE sql AS $$
  INSERT INTO audit_log(seq, prev_hash, hash, actor, action, target, payload)
  VALUES (0, '', '', p_actor, p_action, p_target, coalesce(p_payload, '{}'::jsonb))
$$;

-- Append-only enforcement that holds even for table owners (REVOKE alone does not).
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'append-only: % on % is forbidden', TG_OP, TG_TABLE_NAME;
END $$;
CREATE TRIGGER trg_audit_append_only     BEFORE UPDATE OR DELETE ON audit_log     FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER trg_tool_calls_append_only BEFORE UPDATE OR DELETE ON tool_calls    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER trg_verif_append_only     BEFORE UPDATE OR DELETE ON verifications FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER trg_evidence_append_only  BEFORE UPDATE OR DELETE ON evidence      FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER trg_events_append_only    BEFORE UPDATE OR DELETE ON task_events   FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER trg_audit_no_truncate     BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

-- ---------------------------------------------------------------------------
-- Side effects: every transition / receipt / verification / approval change
-- writes a task_event and an audit entry in the same transaction.
-- ---------------------------------------------------------------------------
CREATE FUNCTION task_transition_log() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE who text := coalesce(current_setting('revenueos.actor', true), session_user);
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO task_events(task_id, event_type, actor, payload)
      VALUES (NEW.id, 'created', who, jsonb_build_object('state', NEW.state));
    PERFORM audit_append(who, 'task.create', NEW.id::text, jsonb_build_object('objective', NEW.objective));
  ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
    INSERT INTO task_events(task_id, event_type, actor, payload)
      VALUES (NEW.id, 'transition', who, jsonb_build_object('from', OLD.state, 'to', NEW.state));
    PERFORM audit_append(who, 'task.transition', NEW.id::text,
      jsonb_build_object('from', OLD.state, 'to', NEW.state, 'verification_id', NEW.verification_id));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_task_transition_log AFTER INSERT OR UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION task_transition_log();

CREATE FUNCTION receipt_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM audit_append(NEW.agent_id::text, 'tool.call', NEW.mcp_server || '/' || NEW.tool,
    jsonb_build_object('tool_call_id', NEW.id, 'args_hash', NEW.args_hash, 'result_hash', NEW.result_hash,
                       'cost', NEW.cost, 'risk', NEW.risk_class, 'approval_id', NEW.approval_id,
                       'verdict', NEW.verdict));
  RETURN NEW;
END $$;
CREATE TRIGGER trg_receipt_log AFTER INSERT ON tool_calls FOR EACH ROW EXECUTE FUNCTION receipt_log();

CREATE FUNCTION verification_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO task_events(task_id, event_type, actor, payload)
    VALUES (NEW.task_id, 'verification', NEW.verifier_agent_id::text,
            jsonb_build_object('verdict', NEW.verdict, 'method', NEW.method, 'tier', NEW.tier));
  PERFORM audit_append(NEW.verifier_agent_id::text, 'verification', NEW.task_id::text,
    jsonb_build_object('verification_id', NEW.id, 'verdict', NEW.verdict, 'tier', NEW.tier));
  RETURN NEW;
END $$;
CREATE TRIGGER trg_verification_log AFTER INSERT ON verifications FOR EACH ROW EXECUTE FUNCTION verification_log();

CREATE FUNCTION approval_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM audit_append(coalesce(NEW.approved_by, NEW.requested_by), 'approval.' || NEW.status,
    NEW.id::text, jsonb_build_object('task_id', NEW.task_id, 'args_hash', NEW.tool_call_args_hash));
  RETURN NEW;
END $$;
CREATE TRIGGER trg_approval_log AFTER INSERT OR UPDATE OF status ON approvals
  FOR EACH ROW EXECUTE FUNCTION approval_log();

-- ---------------------------------------------------------------------------
-- INV-15: insight and learning roles read verified data only
-- ---------------------------------------------------------------------------
CREATE VIEW v_verified_tasks AS
  SELECT t.* FROM tasks t
  JOIN verifications v ON v.id = t.verification_id
  WHERE t.state = 'COMPLETED' AND v.verdict = 'PASS';
CREATE VIEW v_verified_evidence AS
  SELECT e.* FROM evidence e JOIN v_verified_tasks t ON t.id = e.task_id;
CREATE VIEW v_verified_tool_calls AS
  SELECT c.* FROM tool_calls c JOIN v_verified_tasks t ON t.id = c.task_id;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'revenueos_app')      THEN CREATE ROLE revenueos_app; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'revenueos_insight')  THEN CREATE ROLE revenueos_insight; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'revenueos_learning') THEN CREATE ROLE revenueos_learning; END IF;
END $$;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO revenueos_app;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log, tool_calls, verifications, evidence, task_events FROM revenueos_app;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM revenueos_insight, revenueos_learning;
GRANT SELECT ON v_verified_tasks, v_verified_evidence, v_verified_tool_calls TO revenueos_insight, revenueos_learning;

COMMIT;
