"""OpenMuse durable plans on the NAVA gateway: run to completion, pause on approval, resume,
retry, and survive a restart (the next pending step is always in the database)."""
from conftest import approve

from revenueos_runtime_os.nava import args_hash


def test_plan_runs_to_completion_with_receipts(nava):
    pid = nava.k.plan_create(nava.agent, nava.task, "write two files", [
        {"tool": "fs.write", "args": {"workspace": "p1", "path": "a.txt", "content": "A"}},
        {"tool": "fs.write", "args": {"workspace": "p1", "path": "b.txt", "content": "B"}},
        {"tool": "fs.read", "args": {"workspace": "p1", "path": "a.txt"}},
    ])
    p = nava.k.plan_run(pid, nava.agent)
    assert p["status"] == "completed"
    assert [s["status"] for s in p["steps"]] == ["done", "done", "done"]
    # every step is a receipted syscall
    for s in p["steps"]:
        assert nava.db.one(f"SELECT status FROM syscalls WHERE id='{s['syscall_id']}'") == "committed"
    assert (nava.ws.path(nava.agent, "p1") / "b.txt").read_text() == "B"


def test_plan_failed_step_and_retry(nava):
    pid = nava.k.plan_create(nava.agent, nava.task, "flaky build", [
        {"tool": "fs.write", "args": {"workspace": "p2", "path": "ok.txt", "content": "fine"}},
        {"tool": "fs.read", "args": {"workspace": "p2", "path": "missing.txt"}, "max_attempts": 2},
    ])
    p = nava.k.plan_run(pid, nava.agent)
    assert p["status"] == "failed"
    assert [s["status"] for s in p["steps"]] == ["done", "failed"]
    assert p["steps"][1]["attempts"] == 2
    # fix the precondition, retry: only the failed step reruns
    (nava.ws.path(nava.agent, "p2") / "missing.txt").write_text("found")
    p = nava.k.plan_retry(pid, nava.agent)
    assert p["status"] == "completed"
    done_first = nava.db.one(f"SELECT count(*) FROM syscalls WHERE tool='fs.write' AND status='committed'")
    assert done_first == "1"                       # the done step did not rerun


def test_plan_pauses_on_approval_then_resumes(nava):
    ws = nava.ws.path(nava.agent, "p3")
    ws.mkdir(parents=True)
    (ws / "old.txt").write_text("x")
    delete_args = {"workspace": "p3", "path": "old.txt"}
    pid = nava.k.plan_create(nava.agent, nava.task, "clean up", [
        {"tool": "fs.delete", "args": delete_args},
        {"tool": "fs.write", "args": {"workspace": "p3", "path": "new.txt", "content": "y"}},
    ])
    p = nava.k.plan_run(pid, nava.agent, mode="ask")       # fs.delete is medium -> prompt in ask mode
    assert p["status"] == "paused"
    pending = p["steps"][0]["output"]["approval_id"]
    assert pending and p["steps"][0]["status"] == "pending" and p["steps"][0]["attempts"] == 0
    row = nava.db.one(f"SELECT status || '|' || tool || '|' || tool_call_args_hash FROM approvals WHERE id='{pending}'")
    assert row == f"pending|fs.delete|{args_hash(delete_args)}"
    approve(nava.db, pending)
    nava.k.plan_set(pid, "running")
    p = nava.k.plan_run(pid, nava.agent, mode="ask", approvals={"0": pending})
    # step 1 committed with the approval; step 2 (fs.write is low) ran without one
    assert [s["status"] for s in p["steps"]] == ["done", "done"] and p["status"] == "completed"
    assert not (ws / "old.txt").exists() and (ws / "new.txt").exists()


def test_plan_survives_restart(nava, pgdb):
    from revenueos_runtime_os.kernel import Kernel
    pid = nava.k.plan_create(nava.agent, nava.task, "two writes", [
        {"tool": "fs.write", "args": {"workspace": "p4", "path": "1.txt", "content": "1"}},
        {"tool": "fs.write", "args": {"workspace": "p4", "path": "2.txt", "content": "2"}},
    ])
    # run only the first step, then "crash": mark the plan paused mid-way
    nava.k.plan_set(pid, "paused")
    p = nava.k.plan_run(pid, nava.agent)
    assert p["status"] == "paused" and all(s["status"] == "pending" for s in p["steps"])
    # a brand-new kernel (fresh process) resumes from the database state alone
    k2 = Kernel(pgdb, nava.gw)
    k2.plan_set(pid, "running")
    p = k2.plan_run(pid, nava.agent)
    assert p["status"] == "completed" and [s["status"] for s in p["steps"]] == ["done", "done"]


def test_plan_pause_stops_between_steps(nava):
    pid = nava.k.plan_create(nava.agent, nava.task, "noop", [
        {"tool": "test.echo", "args": {"text": "a"}},
    ])
    nava.k.plan_set(pid, "paused")
    assert nava.k.plan_run(pid, nava.agent)["status"] == "paused"   # paused plans never execute
    assert nava.db.one("SELECT count(*) FROM syscalls WHERE tool='test.echo'") == "0"
