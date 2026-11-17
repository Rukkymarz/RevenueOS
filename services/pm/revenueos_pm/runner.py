"""The slice runner behind GSD Pi Auto Mode (spec 5.4): plan, execute, verify, advance, reassess,
per slice, halting on budget exhaustion (INV-08). Who plans and who executes is pluggable.

Phase 5 drives it with deterministic scripted components; the model-backed planner and executor
arrive in Phase 13 (ADR-0005) behind the same two protocols. A scripted run proves the machinery,
not the model."""
from dataclasses import dataclass, field
from typing import Protocol

from . import lifecycle
from .plan import event


class Planner(Protocol):
    def refine(self, db, slice_id: str, tasks: list[dict]) -> None: ...


class Executor(Protocol):
    def execute(self, db, task: dict) -> dict:
        """-> {"evidence": [{kind, uri, hash, tier}], "cost": float}"""


class Checker(Protocol):
    method: str
    def check(self, db, task: dict, evidence: list[dict]) -> tuple[bool, dict]: ...


@dataclass
class Report:
    slice_id: str
    status: str = "open"                     # done | halted | blocked | failed
    completed: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    reason: str = ""


class SliceRunner:
    def __init__(self, db, *, planner: Planner, executor: Executor, checkers: list[Checker], executor_agent: str,
                 verifier_agent: str, premise_bundle_id: str, actor: str = "gsd-runner", max_retries: int = 1):
        self.db, self.planner, self.executor, self.checkers = db, planner, executor, checkers
        self.ea, self.va, self.premise, self.actor, self.max_retries = executor_agent, verifier_agent, premise_bundle_id, actor, max_retries

    def _tasks(self, slice_id: str) -> list[dict]:
        return self.db.rows("SELECT id, objective, task_class, state::text AS state, cost_estimate, cost_actual FROM tasks "
                            "WHERE slice_id = $s::uuid AND deleted_at IS NULL ORDER BY created_at", s=slice_id)

    def _ready(self, task_id: str) -> bool:
        return not self.db.scalar("SELECT 1 AS x FROM task_dependencies d JOIN tasks t ON t.id = d.depends_on "
                                  "WHERE d.task_id = $t::uuid AND t.state <> 'COMPLETED' LIMIT 1", t=task_id)

    def run(self, slice_id: str) -> Report:
        db, rep = self.db, Report(slice_id)
        tasks = self._tasks(slice_id)
        rep.steps.append("plan")
        self.planner.refine(db, slice_id, tasks)
        guard = 0
        while guard < 1000:
            guard += 1
            todo = [t for t in self._tasks(slice_id) if t["state"] not in ("COMPLETED", "CANCELLED")]
            if not todo:
                break
            ready = [t for t in todo if self._ready(t["id"])]
            if not ready:
                rep.status, rep.reason = "blocked", "no ready task: unmet dependencies"
                return rep
            t = ready[0]
            out = self._run_task(t, rep)
            if out != "ok":
                rep.status, rep.reason = out, rep.reason or out
                return rep
            rep.steps.append(f"advance:{t['id']}")
        db.rows("UPDATE slices SET status = 'done' WHERE id = $s::uuid RETURNING id", s=slice_id)
        rep.status = "done"
        rep.steps.append("reassess")
        return rep

    def _run_task(self, t: dict, rep: Report) -> str:
        db, tid = self.db, t["id"]
        if t["state"] == "DRAFT":
            lifecycle.publish(db, tid, self.premise, self.actor)
        if t["state"] in ("DRAFT", "RESEARCHED"):
            lifecycle.claim(db, tid, self.ea, self.actor)
            lifecycle.plan(db, tid, self.actor)
        attempts = 0
        lifecycle.execute(db, tid, self.actor)
        while True:
            rep.steps.append(f"execute:{tid}")
            res = self.executor.execute(db, t)
            db.rows("UPDATE tasks SET cost_actual = cost_actual + $c::numeric WHERE id = $t::uuid RETURNING id", c=str(res.get("cost", 0)), t=tid)
            state = db.scalar("SELECT state::text AS s FROM tasks WHERE id = $t::uuid", t=tid)
            if state == "BUDGET_HALTED":                       # reassess: the estimate is spent
                event(db, tid, "budget_halted", self.actor, {"cost_actual": res.get("cost")})
                rep.reason = f"budget exhausted on {tid}"
                return "halted"
            lifecycle.submit(db, tid, res["evidence"], self.actor)
            results = []
            for c in self.checkers:
                ok, details = c.check(db, t, res["evidence"])
                results.append({"method": c.method, "method_class": "deterministic", "tier": "L2",
                                "verdict": "PASS" if ok else "FAIL", "details": details})
            rep.steps.append(f"verify:{tid}")
            if lifecycle.verify(db, tid, self.va, results, self.actor) == "COMPLETED":
                rep.completed.append(tid)
                return "ok"
            attempts += 1
            if attempts > self.max_retries:
                rep.reason = f"{tid} failed QC {attempts} times"
                return "failed"
            lifecycle.retry(db, tid, self.actor)
