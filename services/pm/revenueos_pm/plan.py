"""Projects, the Spec/Plan/Rules artifacts and the milestone/slice/task tree (spec 5.2, 5.3, 5.4, 5.7).

Postgres is authoritative. The shape rules are GSD Pi's (a milestone holds 4-10 slices, a slice
1-7 tasks); the approval rule is the database's: no task of a project executes until the latest
Spec, Plan and Rules are all approved by a human."""
import json

KINDS = ("spec", "plan", "rules")
MILESTONE_SLICES = (4, 10)
SLICE_TASKS = (1, 7)


class PlanError(ValueError):
    pass


def event(db, task_id: str, kind: str, actor: str, payload: dict | None = None) -> None:
    db.rows("INSERT INTO task_events(task_id, event_type, actor, payload) VALUES ($t::uuid, $k, $a, $p::jsonb) RETURNING id",
            t=task_id, k=kind, a=actor, p=json.dumps(payload or {}, default=str))
    db.rows("SELECT audit_append($a, $k, $t, $p::jsonb) AS x", a=actor, k=f"task.{kind}", t=task_id,
            p=json.dumps(payload or {}, default=str))


def create_project(db, name: str, business_line: str, premise_bundle_id: str | None = None) -> str:
    return db.scalar("INSERT INTO projects(name, business_line, premise_bundle_id, status) VALUES ($n, $b, nullif($p, '')::uuid, "
                     "CASE WHEN $p = '' THEN 'draft' ELSE 'active' END) RETURNING id", n=name, b=business_line, p=premise_bundle_id or "")


def submit_artifact(db, project: str, kind: str, content: str, author: str) -> int:
    if kind not in KINDS:
        raise PlanError(f"artifact kind must be one of {KINDS}")
    if not content.strip():
        raise PlanError("an artifact cannot be empty")
    version = db.scalar("SELECT coalesce(max(version), 0) + 1 AS v FROM decompositions WHERE project_id = $p::uuid AND kind = $k::decomposition_kind",
                        p=project, k=kind)
    db.rows("INSERT INTO decompositions(project_id, kind, content, version) VALUES ($p::uuid, $k::decomposition_kind, $c, $v::integer) RETURNING id",
            p=project, k=kind, c=content, v=version)
    db.rows("SELECT audit_append($a, 'decomposition.submitted', $p, $d::jsonb) AS x", a=author, p=project,
            d=json.dumps({"kind": kind, "version": version}))
    return int(version)


def approve_artifact(db, project: str, kind: str, version: int, approver: str) -> dict:
    row = db.one("UPDATE decompositions SET approved_by = $a WHERE project_id = $p::uuid AND kind = $k::decomposition_kind "
                 "AND version = $v::integer AND approved_at IS NULL RETURNING kind, version, approved_at", p=project, k=kind, v=version, a=approver)
    if row is None:
        raise PlanError(f"no unapproved {kind} v{version} on this project")
    db.rows("SELECT audit_append($a, 'decomposition.approved', $p, $d::jsonb) AS x", a=approver, p=project,
            d=json.dumps({"kind": kind, "version": version}))
    return row


def artifacts_approved(db, project: str) -> bool:
    return bool(db.scalar("SELECT project_artifacts_approved($p::uuid) AS ok", p=project))


def validate(plan: dict) -> list[str]:
    """Every problem in a plan, none raised: a Planner gets the whole list back at once."""
    errs, keys, deps = [], set(), []
    ms = plan.get("milestones")
    if not isinstance(ms, list) or not ms:
        return ["plan needs at least one milestone"]
    for mi, m in enumerate(ms):
        where = f"milestone {mi + 1}"
        sl = m.get("slices") or []
        if not m.get("name"):
            errs.append(f"{where}: name required")
        if not MILESTONE_SLICES[0] <= len(sl) <= MILESTONE_SLICES[1]:
            errs.append(f"{where}: needs {MILESTONE_SLICES[0]}-{MILESTONE_SLICES[1]} slices, has {len(sl)}")
        for si, s in enumerate(sl):
            sw = f"{where} slice {si + 1}"
            ts = s.get("tasks") or []
            if not SLICE_TASKS[0] <= len(ts) <= SLICE_TASKS[1]:
                errs.append(f"{sw}: needs {SLICE_TASKS[0]}-{SLICE_TASKS[1]} tasks, has {len(ts)}")
            for t in ts:
                k = t.get("key")
                if not k or k in keys:
                    errs.append(f"{sw}: task key missing or duplicated ({k!r})")
                keys.add(k)
                if not t.get("objective") or not t.get("task_class"):
                    errs.append(f"{sw} task {k}: objective and task_class required")
                ac = t.get("acceptance_criteria")
                if not isinstance(ac, list) or not ac:
                    errs.append(f"{sw} task {k}: machine-checkable acceptance_criteria required")
                deps += [(k, d) for d in t.get("depends_on") or []]
    errs += [f"task {a} depends on unknown task {b}" for a, b in deps if b not in keys]
    return errs


def create_tree(db, project: str, plan: dict, actor: str) -> dict:
    """Milestones, slices, tasks and dependency edges, in one pass. Returns key -> task id."""
    errs = validate(plan)
    if errs:
        raise PlanError("; ".join(errs))
    ids: dict[str, str] = {}
    for mi, m in enumerate(plan["milestones"]):
        mid = db.scalar("INSERT INTO milestones(project_id, name, order_index) VALUES ($p::uuid, $n, $i::integer) RETURNING id",
                        p=project, n=m["name"], i=mi + 1)
        for si, s in enumerate(m["slices"]):
            sid = db.scalar("INSERT INTO slices(milestone_id, name, order_index) VALUES ($m::uuid, $n, $i::integer) RETURNING id",
                            m=mid, n=s["name"], i=si + 1)
            for t in s["tasks"]:
                ids[t["key"]] = db.scalar(
                    "INSERT INTO tasks(project_id, slice_id, objective, task_class, acceptance_criteria, cost_estimate, "
                    "required_oracle_tier) VALUES ($p::uuid, $s::uuid, $o, $c, $a::jsonb, nullif($e, '')::numeric, $tier::oracle_tier) RETURNING id",
                    p=project, s=sid, o=t["objective"], c=t["task_class"], a=json.dumps(t["acceptance_criteria"]),
                    e=str(t.get("cost_estimate", "")), tier=t.get("tier", "L2"))
                event(db, ids[t["key"]], "placed", actor, {"key": t["key"], "slice": sid})
    for m in plan["milestones"]:
        for s in m["slices"]:
            for t in s["tasks"]:
                for d in t.get("depends_on") or []:
                    db.rows("INSERT INTO task_dependencies(task_id, depends_on) VALUES ($a::uuid, $b::uuid) RETURNING task_id",
                            a=ids[t["key"]], b=ids[d])
    return ids


def tree(db, project: str) -> list[dict]:
    return db.rows("SELECT m.order_index AS milestone, m.name AS milestone_name, s.id AS slice_id, s.order_index AS slice, "
                   "s.name AS slice_name, s.status AS slice_status, t.id AS task_id, t.objective, t.state "
                   "FROM milestones m JOIN slices s ON s.milestone_id = m.id LEFT JOIN tasks t ON t.slice_id = s.id "
                   "WHERE m.project_id = $p::uuid ORDER BY m.order_index, s.order_index, t.created_at", p=project)
