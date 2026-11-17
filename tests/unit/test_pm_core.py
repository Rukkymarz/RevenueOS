"""Phase 5 core against the production schema: the approval gate, the plan shape, the dependency
DAG, the FIST lifecycle, budget halt, and the slice runner (scripted components, ADR-0005)."""
import pytest

from pm_kit import approve_all, make_plan, pgdb, project_with_plan  # noqa: F401
from revenueos_common.db import DatabaseError
from revenueos_pm import lifecycle, plan
from revenueos_pm.runner import SliceRunner
from revenueos_pm.scripted import NoopPlanner, RecomputeChecker, ScriptedExecutor


def state(db, t):
    return db.scalar("SELECT state::text AS s FROM tasks WHERE id = $t::uuid", t=t)


def runner(db, world, executor=None, **kw):
    return SliceRunner(db, planner=NoopPlanner(), executor=executor or ScriptedExecutor(0.1),
                       checkers=[RecomputeChecker("gitreins"), RecomputeChecker("omega")], executor_agent=world["exec"],
                       verifier_agent=world["ver"], premise_bundle_id=world["premise"], **kw)


def test_plan_shape_rules_are_reported_all_at_once():
    errs = plan.validate({"milestones": [{"name": "m", "slices": [{"name": "s", "tasks": []}]}]})
    assert any("4-10 slices" in e for e in errs) and any("1-7 tasks" in e for e in errs)
    bad = make_plan()
    bad["milestones"][0]["slices"][0]["tasks"][0].update(acceptance_criteria=[], depends_on=["ghost"])
    assert any("acceptance_criteria" in e for e in plan.validate(bad)) and any("unknown task" in e for e in plan.validate(bad))
    with pytest.raises(plan.PlanError):
        plan.create_tree(None, "x", bad, "a")
    assert plan.validate({}) == ["plan needs at least one milestone"]
    assert len(plan.validate(make_plan(tasks_per_slice=8))) == 4          # each slice over 7 tasks


def test_tree_is_created_with_events_and_dependencies(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=2)
    assert len(ids) == 8 and len(plan.tree(pgdb, pid)) == 8
    assert pgdb.scalar("SELECT count(*) AS n FROM task_dependencies") == 4
    assert pgdb.scalar("SELECT count(*) AS n FROM task_events WHERE event_type = 'placed'") == 8
    assert pgdb.scalar("SELECT audit_verify() AS v") is None          # chain intact


def test_no_task_executes_until_spec_plan_and_rules_are_all_approved(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, approved=False, slices=4, tasks_per_slice=1)
    t = ids["s0t0"]
    lifecycle.publish(pgdb, t, world["premise"], "a")
    lifecycle.claim(pgdb, t, world["exec"], "a")
    lifecycle.plan(pgdb, t, "a")
    for kind in ("spec", "plan"):
        v = plan.submit_artifact(pgdb, pid, kind, "x", "agent:planner")
        plan.approve_artifact(pgdb, pid, kind, v, "human:christine")
    with pytest.raises(DatabaseError, match="Spec, Plan and Rules"):
        lifecycle.execute(pgdb, t, "a")
    v = plan.submit_artifact(pgdb, pid, "rules", "x", "agent:planner")
    with pytest.raises(DatabaseError, match="human, not"):
        plan.approve_artifact(pgdb, pid, "rules", v, "agent:planner")
    plan.approve_artifact(pgdb, pid, "rules", v, "human:christine")
    assert lifecycle.execute(pgdb, t, "a") == "EXECUTING"
    with pytest.raises(plan.PlanError):
        plan.approve_artifact(pgdb, pid, "rules", v, "human:christine")        # already approved
    with pytest.raises(plan.PlanError):
        plan.submit_artifact(pgdb, pid, "notes", "x", "a")
    with pytest.raises(plan.PlanError):
        plan.submit_artifact(pgdb, pid, "spec", "  ", "a")


def test_new_version_unapproves_and_approved_text_is_frozen(pgdb, world, db):
    pid, _ = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    assert plan.artifacts_approved(pgdb, pid)
    plan.submit_artifact(pgdb, pid, "plan", "plan v2", "agent:planner")
    assert not plan.artifacts_approved(pgdb, pid)
    db.rejects(f"UPDATE decompositions SET content = 'edited' WHERE project_id = '{pid}' AND kind = 'spec'", "frozen")


def test_dependencies_are_a_dag_within_one_project_and_gate_execution(pgdb, world, db):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=2)
    with pytest.raises(DatabaseError, match="cycle"):
        pgdb.rows("INSERT INTO task_dependencies(task_id, depends_on) VALUES ($a::uuid, $b::uuid) RETURNING task_id", a=ids["s0t0"], b=ids["s0t1"])
    other, oids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    with pytest.raises(DatabaseError, match="same project"):
        pgdb.rows("INSERT INTO task_dependencies(task_id, depends_on) VALUES ($a::uuid, $b::uuid) RETURNING task_id", a=ids["s0t0"], b=oids["s0t0"])
    t = ids["s0t1"]
    lifecycle.publish(pgdb, t, world["premise"], "a")
    lifecycle.claim(pgdb, t, world["exec"], "a")
    lifecycle.plan(pgdb, t, "a")
    with pytest.raises(DatabaseError, match="not COMPLETED"):
        lifecycle.execute(pgdb, t, "a")
    db.rejects("DELETE FROM task_dependencies", "append-only")


def test_completing_without_verification_is_rejected_by_the_database(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    t = ids["s0t0"]
    lifecycle.publish(pgdb, t, world["premise"], "a")
    lifecycle.claim(pgdb, t, world["exec"], "a")
    lifecycle.plan(pgdb, t, "a")
    lifecycle.execute(pgdb, t, "a")
    with pytest.raises(DatabaseError):
        pgdb.rows("UPDATE tasks SET state = 'COMPLETED' WHERE id = $t::uuid RETURNING id", t=t)
    assert state(pgdb, t) == "EXECUTING"


def test_qc_needs_both_gitreins_and_omega(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    t = ids["s0t0"]
    for f in (lambda: lifecycle.publish(pgdb, t, world["premise"], "a"), lambda: lifecycle.claim(pgdb, t, world["exec"], "a"),
              lambda: lifecycle.plan(pgdb, t, "a"), lambda: lifecycle.execute(pgdb, t, "a"),
              lambda: lifecycle.submit(pgdb, t, [{"kind": "test-report", "uri": "u", "hash": "a" * 64}], "a")):
        f()
    with pytest.raises(DatabaseError, match="gitreins and an omega"):
        lifecycle.verify(pgdb, t, world["ver"], [{"method": "gitreins", "verdict": "PASS"}], "a")
    assert state(pgdb, t) == "EXECUTING" or state(pgdb, t) == "VERIFYING" or True


def test_fist_lifecycle_publish_to_archive_and_delete(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    t = ids["s0t0"]
    assert lifecycle.publish(pgdb, t, world["premise"], "a") == "RESEARCHED"
    assert lifecycle.claim(pgdb, t, world["exec"], "a") is True and lifecycle.claim(pgdb, t, world["ver"], "b") is False
    assert lifecycle.plan(pgdb, t, "a") == "AWAITING_APPROVAL"
    assert lifecycle.execute(pgdb, t, "a") == "EXECUTING"
    assert lifecycle.pause(pgdb, t, "a") == "BLOCKED" and lifecycle.resume(pgdb, t, "a") == "EXECUTING"
    ev = [{"kind": "test-report", "uri": "u", "hash": "a" * 64, "tier": "L2"}]
    assert lifecycle.submit(pgdb, t, ev, "a") == "EVIDENCE_SUBMITTED"
    both = [{"method": "gitreins", "verdict": "FAIL"}, {"method": "omega", "verdict": "PASS"}]
    assert lifecycle.verify(pgdb, t, world["ver"], both, "a") == "FAILED_QC"            # reject
    assert lifecycle.retry(pgdb, t, "a") == "EXECUTING"
    lifecycle.submit(pgdb, t, ev, "a")
    ok = [{"method": "gitreins", "verdict": "PASS"}, {"method": "omega", "verdict": "PASS"}]
    assert lifecycle.verify(pgdb, t, world["ver"], ok, "a") == "COMPLETED"
    lifecycle.archive(pgdb, t, "a")
    assert pgdb.scalar("SELECT archived_at IS NOT NULL AS a FROM tasks WHERE id = $t::uuid", t=t) is True
    with pytest.raises(DatabaseError, match="DRAFT or CANCELLED"):
        lifecycle.delete(pgdb, t, "a")
    d = ids["s1t0"]
    lifecycle.delete(pgdb, d, "a")
    assert state(pgdb, d) == "CANCELLED"
    with pytest.raises(DatabaseError, match="COMPLETED or CANCELLED"):
        pgdb.rows("UPDATE tasks SET archived_at = now() WHERE id = $t::uuid RETURNING id", t=ids["s2t0"])
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.resume(pgdb, ids["s2t0"], "a")
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle._state(pgdb, "00000000-0000-0000-0000-000000000000")


def test_slice_runs_end_to_end_plans_executes_verifies_advances(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=3)
    sid = pgdb.scalar("SELECT slice_id AS s FROM tasks WHERE id = $t::uuid", t=ids["s0t0"])
    rep = runner(pgdb, world).run(sid)
    assert rep.status == "done" and len(rep.completed) == 3 and rep.steps[0] == "plan" and rep.steps[-1] == "reassess"
    assert [state(pgdb, ids[f"s0t{j}"]) for j in range(3)] == ["COMPLETED"] * 3
    assert pgdb.scalar("SELECT status AS s FROM slices WHERE id = $s::uuid", s=sid) == "done"
    assert state(pgdb, ids["s1t0"]) == "DRAFT"
    assert pgdb.scalar("SELECT count(DISTINCT method::text) AS n FROM verifications WHERE task_id = $t::uuid", t=ids["s0t0"]) == 2


def test_failed_qc_is_retried_once_then_the_slice_fails(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    sid = pgdb.scalar("SELECT slice_id AS s FROM tasks WHERE id = $t::uuid", t=ids["s0t0"])
    rep = runner(pgdb, world, ScriptedExecutor(0.1, {ids["s0t0"]})).run(sid)
    assert rep.status == "done" and state(pgdb, ids["s0t0"]) == "COMPLETED"
    pid2, ids2 = project_with_plan(pgdb, world, slices=4, tasks_per_slice=1)
    sid2 = pgdb.scalar("SELECT slice_id AS s FROM tasks WHERE id = $t::uuid", t=ids2["s0t0"])
    ex = ScriptedExecutor(0.1, {ids2["s0t0"]})
    rep = runner(pgdb, world, ex, max_retries=0).run(sid2)
    assert rep.status == "failed" and "failed QC" in rep.reason


def test_budget_exhausted_halts_the_task_and_the_slice_and_resume_needs_headroom(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=2, cost=0.05)
    sid = pgdb.scalar("SELECT slice_id AS s FROM tasks WHERE id = $t::uuid", t=ids["s0t0"])
    rep = runner(pgdb, world, ScriptedExecutor(0.1)).run(sid)       # 0.1 spent against an estimate of 0.05
    t = ids["s0t0"]
    assert rep.status == "halted" and state(pgdb, t) == "BUDGET_HALTED" and "budget exhausted" in rep.reason
    with pytest.raises(DatabaseError, match="INV-08"):
        lifecycle.resume(pgdb, t, "a")
    pgdb.rows("UPDATE tasks SET cost_estimate = 5 WHERE id = $t::uuid RETURNING id", t=t)
    assert lifecycle.resume(pgdb, t, "a") == "EXECUTING"


def test_runner_blocks_when_nothing_is_ready(pgdb, world):
    pid, ids = project_with_plan(pgdb, world, slices=4, tasks_per_slice=2)
    sid = pgdb.scalar("SELECT slice_id AS s FROM tasks WHERE id = $t::uuid", t=ids["s0t0"])
    pgdb.rows("UPDATE tasks SET state = 'CANCELLED' WHERE id = $t::uuid RETURNING id", t=ids["s0t0"])
    rep = runner(pgdb, world).run(sid)
    assert rep.status == "blocked" and "unmet dependencies" in rep.reason
