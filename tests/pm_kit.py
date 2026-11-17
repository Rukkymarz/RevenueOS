import json

from discovery_kit import pgdb  # noqa: F401  (fixture)


def make_plan(slices=4, tasks_per_slice=2, cost=1.0):
    ms = [{"name": "MVP", "slices": [
        {"name": f"slice {i}", "tasks": [
            {"key": f"s{i}t{j}", "objective": f"build part {i}.{j}", "task_class": "code",
             "acceptance_criteria": [{"check": "tests_pass"}], "cost_estimate": cost,
             **({"depends_on": [f"s{i}t{j - 1}"]} if j else {})} for j in range(tasks_per_slice)]} for i in range(slices)]}]
    return {"milestones": ms}


def approve_all(pm_plan, db, project, approver="human:christine"):
    for kind in pm_plan.KINDS:
        v = pm_plan.submit_artifact(db, project, kind, f"{kind} text", "agent:planner")
        pm_plan.approve_artifact(db, project, kind, v, approver)


def project_with_plan(db, world, approved=True, **kw):
    from revenueos_pm import plan
    pid = plan.create_project(db, "p", "cleaning", world["premise"])
    if approved:
        approve_all(plan, db, pid)
    return pid, plan.create_tree(db, pid, make_plan(**kw), "agent:planner")
