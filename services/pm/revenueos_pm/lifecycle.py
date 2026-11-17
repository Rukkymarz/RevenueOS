"""FIST-Mbt's task lifecycle (spec 5.5) on the database state machine: publish, claim, plan,
execute, submit, verify, reject, retry, pause, resume, archive, delete. The verbs only ask; the
guards in 0001/0005 decide, so a verb cannot do what the state machine forbids."""
import json

from .plan import event

VERBS = ("publish", "claim", "plan", "execute", "submit", "verify", "reject", "retry", "pause", "resume", "archive", "delete")


class LifecycleError(RuntimeError):
    pass


def _state(db, task: str) -> str:
    s = db.scalar("SELECT state::text AS s FROM tasks WHERE id = $t::uuid", t=task)
    if s is None:
        raise LifecycleError(f"unknown task {task}")
    return s


def _move(db, task: str, to: str, actor: str, verb: str, extra: str = "", **p) -> str:
    row = db.one(f"UPDATE tasks SET state = $to::task_state{extra} WHERE id = $t::uuid RETURNING state::text AS s", to=to, t=task, **p)
    event(db, task, verb, actor, {"to": row["s"]})
    return row["s"]


def publish(db, task: str, premise_bundle_id: str, actor: str) -> str:
    db.rows("UPDATE tasks SET premise_bundle_id = $b::uuid WHERE id = $t::uuid RETURNING id", b=premise_bundle_id, t=task)
    return _move(db, task, "RESEARCHED", actor, "publish")


def claim(db, task: str, agent: str, actor: str) -> bool:
    """Atomic: exactly one claimant wins."""
    row = db.one("UPDATE tasks SET assigned_agent_id = $a::uuid, executor_agent_id = $a::uuid WHERE id = $t::uuid "
                 "AND assigned_agent_id IS NULL AND state IN ('RESEARCHED','PLANNED','AWAITING_APPROVAL') RETURNING id", a=agent, t=task)
    if row:
        event(db, task, "claim", actor, {"agent": agent})
    return bool(row)


def plan(db, task: str, actor: str) -> str:
    _move(db, task, "PLANNED", actor, "plan")
    return _move(db, task, "AWAITING_APPROVAL", actor, "plan")


def execute(db, task: str, actor: str) -> str:
    return _move(db, task, "EXECUTING", actor, "execute")


def submit(db, task: str, evidence: list[dict], actor: str) -> str:
    for e in evidence:
        db.rows("INSERT INTO evidence(task_id, kind, uri, hash, oracle_tier, produced_by) VALUES ($t::uuid, $k, $u, $h, $o::oracle_tier, $p) RETURNING id",
                t=task, k=e["kind"], u=e["uri"], h=e["hash"], o=e.get("tier", "L2"), p=e.get("produced_by", actor))
    return _move(db, task, "EVIDENCE_SUBMITTED", actor, "submit")


def verify(db, task: str, verifier: str, results: list[dict], actor: str) -> str:
    """results: [{method, method_class, verdict, tier, details}]. Every verdict is stored. Any
    non-PASS sends the task to FAILED_QC; all PASS (gitreins and omega among them) reach COMPLETED."""
    _move(db, task, "VERIFYING", actor, "verify", ", verifier_agent_id = $v::uuid", v=verifier)
    last = None
    for r in results:
        last = db.scalar("INSERT INTO verifications(task_id, verifier_agent_id, method, method_class, verdict, tier, details) "
                         "VALUES ($t::uuid, $v::uuid, $m::verify_method, $c::verify_method_class, $d::verdict, $o::oracle_tier, $x::jsonb) RETURNING id",
                         t=task, v=verifier, m=r["method"], c=r.get("method_class", "deterministic"), d=r["verdict"],
                         o=r.get("tier", "L2"), x=json.dumps(r.get("details", {})))
    if not results or any(r["verdict"] != "PASS" for r in results):
        return _move(db, task, "FAILED_QC", actor, "reject")
    db.rows("UPDATE tasks SET verification_id = $i::uuid WHERE id = $t::uuid RETURNING id", i=last, t=task)
    _move(db, task, "QC_PASSED", actor, "verify")
    db.rows("UPDATE tasks SET verification_id = $i::uuid WHERE id = $t::uuid RETURNING id", i=last, t=task)
    return _move(db, task, "COMPLETED", actor, "verify")


def retry(db, task: str, actor: str) -> str:
    return _move(db, task, "EXECUTING", actor, "retry")


def pause(db, task: str, actor: str, reason: str = "") -> str:
    s = _move(db, task, "BLOCKED", actor, "pause")
    return s


def resume(db, task: str, actor: str) -> str:
    rs = db.scalar("SELECT resume_state::text AS r FROM tasks WHERE id = $t::uuid", t=task)
    if rs is None:
        raise LifecycleError("task is not paused")
    return _move(db, task, rs, actor, "resume")


def archive(db, task: str, actor: str) -> None:
    db.rows("UPDATE tasks SET archived_at = now() WHERE id = $t::uuid RETURNING id", t=task)
    event(db, task, "archive", actor)


def delete(db, task: str, actor: str) -> None:
    if _state(db, task) == "DRAFT":
        _move(db, task, "CANCELLED", actor, "delete")
    db.rows("UPDATE tasks SET deleted_at = now() WHERE id = $t::uuid RETURNING id", t=task)
    event(db, task, "delete", actor)
