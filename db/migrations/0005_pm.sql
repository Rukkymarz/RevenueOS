BEGIN;
ALTER TYPE verify_method ADD VALUE IF NOT EXISTS 'omega';
-- Phase 5 (C06): decomposition approval gate, dependency DAG, lifecycle fields, budget halt, mirrors.

ALTER TABLE tasks
  ADD COLUMN namespace   text NOT NULL DEFAULT 'default',
  ADD COLUMN archived_at timestamptz,
  ADD COLUMN deleted_at  timestamptz,
  ADD CONSTRAINT tasks_slice_needs_project CHECK (slice_id IS NULL OR project_id IS NOT NULL);

-- Approved artifacts are frozen; a human approves, never an agent.
CREATE FUNCTION decomposition_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.approved_at IS NOT NULL
     AND (NEW.content IS DISTINCT FROM OLD.content OR NEW.approved_by IS DISTINCT FROM OLD.approved_by) THEN
    RAISE EXCEPTION 'decomposition: an approved % v% is frozen; write a new version', OLD.kind, OLD.version;
  END IF;
  IF NEW.approved_by IS NOT NULL THEN
    IF NEW.approved_by LIKE 'agent:%' OR NEW.approved_by = '' THEN
      RAISE EXCEPTION 'decomposition: artifacts are approved by a human, not %', NEW.approved_by;
    END IF;
    IF NEW.approved_at IS NULL THEN NEW.approved_at := now(); END IF;
  ELSIF NEW.approved_at IS NOT NULL THEN
    RAISE EXCEPTION 'decomposition: approved_at without approved_by';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_decomposition_guard BEFORE INSERT OR UPDATE ON decompositions
  FOR EACH ROW EXECUTE FUNCTION decomposition_guard();

-- The latest version of each kind is the one that counts.
CREATE FUNCTION project_artifacts_approved(p_project uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT count(*) = 3 FROM (
    SELECT DISTINCT ON (kind) kind, approved_at FROM decompositions
     WHERE project_id = p_project ORDER BY kind, version DESC) d
   WHERE d.approved_at IS NOT NULL
$$;

CREATE TABLE task_dependencies (
  task_id    uuid NOT NULL REFERENCES tasks(id),
  depends_on uuid NOT NULL REFERENCES tasks(id),
  PRIMARY KEY (task_id, depends_on),
  CHECK (task_id <> depends_on)
);
CREATE FUNCTION task_dependency_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT project_id FROM tasks WHERE id = NEW.task_id) IS DISTINCT FROM (SELECT project_id FROM tasks WHERE id = NEW.depends_on) THEN
    RAISE EXCEPTION 'dependency: tasks must belong to the same project';
  END IF;
  IF EXISTS (WITH RECURSIVE up(id) AS (SELECT NEW.depends_on UNION SELECT d.depends_on FROM task_dependencies d JOIN up ON d.task_id = up.id)
             SELECT 1 FROM up WHERE id = NEW.task_id) THEN
    RAISE EXCEPTION 'dependency: % -> % would create a cycle', NEW.task_id, NEW.depends_on;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_task_dependency_guard BEFORE INSERT ON task_dependencies
  FOR EACH ROW EXECUTE FUNCTION task_dependency_guard();
CREATE TRIGGER trg_task_dependencies_append_only BEFORE UPDATE OR DELETE ON task_dependencies
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Mirrors in Mission Control, Piyaz and the filesystem tracker. Postgres stays authoritative.
CREATE TABLE task_mirrors (
  task_id     uuid NOT NULL REFERENCES tasks(id),
  system      text NOT NULL CHECK (system IN ('mission-control', 'piyaz', 'llm-tracker')),
  external_id text NOT NULL,
  synced_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (task_id, system)
);

-- Fires before trg_task_state_guard (alphabetical), so the halt below is validated by the state machine.
CREATE FUNCTION task_pm_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.state = 'EXECUTING' AND OLD.state IS DISTINCT FROM 'EXECUTING' THEN
    IF NEW.project_id IS NOT NULL AND NOT project_artifacts_approved(NEW.project_id) THEN
      RAISE EXCEPTION 'C06: Spec, Plan and Rules must all be approved before a task executes';
    END IF;
    IF EXISTS (SELECT 1 FROM task_dependencies d JOIN tasks t ON t.id = d.depends_on
                WHERE d.task_id = NEW.id AND t.state <> 'COMPLETED') THEN
      RAISE EXCEPTION 'C06: dependencies of % are not COMPLETED', NEW.id;
    END IF;
  END IF;
  -- FIST-Mbt: Omega and GitReins must both pass before a managed task reaches QC_PASSED.
  IF NEW.state = 'QC_PASSED' AND OLD.state IS DISTINCT FROM 'QC_PASSED' AND NEW.slice_id IS NOT NULL THEN
    IF (SELECT count(DISTINCT v.method::text) FROM verifications v
         WHERE v.task_id = NEW.id AND v.verdict = 'PASS' AND v.method::text IN ('gitreins', 'omega')
           AND v.tier >= NEW.required_oracle_tier) < 2 THEN
      RAISE EXCEPTION 'C06: QC_PASSED needs both a gitreins and an omega PASS';
    END IF;
  END IF;
  IF NEW.archived_at IS DISTINCT FROM OLD.archived_at AND NEW.archived_at IS NOT NULL
     AND NEW.state NOT IN ('COMPLETED', 'CANCELLED') THEN
    RAISE EXCEPTION 'C06: only a COMPLETED or CANCELLED task is archived';
  END IF;
  IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at AND NEW.deleted_at IS NOT NULL
     AND NEW.state NOT IN ('DRAFT', 'CANCELLED') THEN
    RAISE EXCEPTION 'C06: only a DRAFT or CANCELLED task is deleted';
  END IF;
  -- INV-08 for tasks: spending the estimate halts the task, resuming needs headroom.
  IF NEW.state = OLD.state AND NEW.cost_estimate IS NOT NULL AND NEW.cost_estimate > 0
     AND NEW.cost_actual >= NEW.cost_estimate
     AND OLD.state IN ('EXECUTING', 'EVIDENCE_SUBMITTED', 'VERIFYING', 'FAILED_QC') THEN
    NEW.state := 'BUDGET_HALTED';
  END IF;
  IF OLD.state = 'BUDGET_HALTED' AND NEW.state <> 'BUDGET_HALTED' AND NEW.state <> 'CANCELLED'
     AND NEW.cost_estimate IS NOT NULL AND NEW.cost_actual >= NEW.cost_estimate THEN
    RAISE EXCEPTION 'INV-08: task % is over its budget; raise the estimate before resuming', NEW.id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_task_pm_guard BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION task_pm_guard();

GRANT SELECT, INSERT, UPDATE ON task_dependencies, task_mirrors TO revenueos_app;
REVOKE UPDATE ON task_dependencies FROM revenueos_app;
COMMIT;
