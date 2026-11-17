"""Deterministic planner, executor and checkers for the slice runner. They make the runner
testable and let acceptance run it end to end with no model. They are labelled as such everywhere
(ADR-0005): they prove the machinery, not the model-backed Planner and Auto Mode of Phase 13.

The oracle is a recomputation: the executor records the sha-256 of its output text as evidence, and
each checker recomputes it from the stored evidence (a different path from the one that made it)."""
import hashlib


class NoopPlanner:
    def refine(self, db, slice_id, tasks):  # a model planner reorders and splits here (Phase 13)
        return None


class ScriptedExecutor:
    def __init__(self, cost_per_task: float = 0.01, fail_first: set[str] | None = None):
        self.cost, self.fail_first, self.seen = cost_per_task, set(fail_first or ()), set()

    def execute(self, db, task):
        out = f"result for {task['objective']}"
        if task["id"] in self.fail_first and task["id"] not in self.seen:
            self.seen.add(task["id"])
            out = "wrong"                      # fails the recomputation once, then a retry succeeds
        digest = hashlib.sha256(f"result for {task['objective']}".encode()).hexdigest()
        if out == "wrong":
            digest = hashlib.sha256(b"wrong").hexdigest()
        return {"evidence": [{"kind": "test-report", "uri": f"scripted://{task['id']}", "hash": digest, "tier": "L2"}],
                "cost": self.cost}


class RecomputeChecker:
    def __init__(self, method: str):
        self.method = method

    def check(self, db, task, evidence):
        want = hashlib.sha256(f"result for {task['objective']}".encode()).hexdigest()
        got = [e["hash"] for e in evidence]
        return want in got, {"expected": want, "got": got, "scripted": True}
