"""The 21 NAVA kernel invariants (docs/NAVA.md). Each test drives the real gateway against the
real migrated database, or attacks the database directly to prove the trigger — not the Python —
is the boundary (INV-07)."""
import time

from conftest import make_approval

from revenueos_runtime_os.nava import args_hash

H = "a" * 64


def open_syscall(db, agent, task, tool="test.echo", h=H, mutating=False):
    return db.one("INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating) "
                  f"VALUES ('{agent}', '{task}', '{tool}', '{h}', {mutating}) RETURNING id")


def put_step(db, sid, n, name, outcome="pass", detail="{}"):
    db.q(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome, detail) "
          f"VALUES ('{sid}', {n}, '{name}', '{outcome}', '{detail}')")


NAMES = ["validate", "authenticate", "authorize", "classify", "policy", "approval", "quota", "lock",
         "snapshot", "execute", "verify", "record"]


def walk(db, sid, upto=12, outcome="pass", classify=True):
    for i in range(1, upto + 1):
        put_step(db, sid, i, NAMES[i - 1], outcome if i == upto else "pass")
        if i == 4 and classify:          # classification is what step 4 records (N05)
            db.q(f"UPDATE syscalls SET risk_class='low' WHERE id='{sid}'")


# ---- N01..N03 -------------------------------------------------------------------------------
def test_n01_step_order(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 2, 'authenticate', 'pass')",
                    "N01")                                      # can't start at 2
    put_step(nava.db, sid, 1, "validate")
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 3, 'authorize', 'pass')",
                    "N01")                                      # can't skip 2
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 2, 'quota', 'pass')",
                    "N01")                                      # wrong name for step 2
    put_step(nava.db, sid, 2, "authenticate", "fail")
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 3, 'authorize', 'pass')",
                    "N01")                                      # after a failure, only step 12
    put_step(nava.db, sid, 12, "record", "fail")
    # steps are append-only
    nava.db.rejects(f"UPDATE syscall_steps SET outcome='pass' WHERE syscall_id='{sid}' AND step=2", "append-only")


def test_n02_single_terminal_state(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    nava.db.rejects(f"UPDATE syscalls SET status='failed' WHERE id='{sid}'", "N01")  # no record step yet
    walk(nava.db, sid, 11)
    put_step(nava.db, sid, 12, "record", "fail")
    nava.db.q(f"UPDATE syscalls SET status='failed', reason='x' WHERE id='{sid}'")
    nava.db.rejects(f"UPDATE syscalls SET status='committed' WHERE id='{sid}'", "N02")   # ended once
    sid2 = open_syscall(nava.db, nava.agent, nava.task)
    walk(nava.db, sid2, 12)
    nava.db.q(f"UPDATE syscalls SET status='failed', reason='x' WHERE id='{sid2}'")
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid2}', 12, 'record', 'pass')",
                    "N02")                                      # nothing recorded after the end


def test_n03_only_active_agents(nava):
    for status in ("paused", "budget_halted", "killed"):
        nava.db.q(f"UPDATE agents SET status='{status}' WHERE id='{nava.other}'")
        nava.db.rejects(f"INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating) "
                        f"VALUES ('{nava.other}', '{nava.task}', 't', '{H}', false)", "N03")
    r = nava.gw.syscall(caller_agent=nava.agent, agent_id=nava.agent, task_id=nava.task,
                        tool="test.echo", args={"text": "hi"})
    assert r.status == "committed"


def test_n04_capability_denies(nava):
    nava.db.q(f"INSERT INTO nava_denies(agent_id, tool_pattern) VALUES ('{nava.agent}', 'fs.*')")
    r = nava.call(tool="fs.list", args={"workspace": "w1"})
    assert r.status == "denied" and r.step == "authorize" and "capability" in r.reason
    assert nava.call(tool="test.echo", args={}).status == "committed"    # others unaffected
    # the deny is inherited by a subagent (also under N21)
    child = nava.k.spawn(nava.agent, "list files", ttl_s=60)
    r2 = nava.gw.syscall(caller_agent=child["agent_id"], agent_id=child["agent_id"], task_id=nava.task,
                         tool="fs.list", args={"workspace": "w1"})
    assert r2.status == "denied" and r2.step == "authorize"


# ---- N05..N07: execution preconditions, proven at the database -------------------------------
def test_n05_no_execute_without_classification(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    walk(nava.db, sid, 9, classify=False)      # 12 steps walked, but no risk class ever recorded
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 10, 'execute', 'pass')",
                    "N05")


def test_n06_critical_never_executes(nava):
    # policy layer: rm -rf is critical in every mode, straight through the gateway
    for mode in ("ask", "auto", "yolo"):
        r = nava.call(tool="sandbox.run", args={"workspace": "w", "argv": ["rm", "-rf", "/"]}, mode=mode)
        assert r.status == "denied" and r.risk_class == "critical", mode
    # database layer: even a forged step sequence cannot execute a critical call
    sid = open_syscall(nava.db, nava.agent, nava.task)
    walk(nava.db, sid, 3)
    put_step(nava.db, sid, 4, "classify")
    nava.db.q(f"UPDATE syscalls SET risk_class='critical' WHERE id='{sid}'")
    for n in (5, 6, 7, 8, 9):
        put_step(nava.db, sid, n, NAMES[n - 1])
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 10, 'execute', 'pass')",
                    "N06")
    # and the terminal CHECK refuses a committed critical call outright
    nava.db.rejects(f"INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating, risk_class, status, ended_at) "
                    f"VALUES ('{nava.agent}', '{nava.task}', 't', '{H}', false, 'critical', 'committed', now())", "")


def test_n07_approval_bound_execution(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task, tool="x.dangerous")
    walk(nava.db, sid, 3)
    put_step(nava.db, sid, 4, "classify")
    nava.db.q(f"UPDATE syscalls SET risk_class='high' WHERE id='{sid}'")
    put_step(nava.db, sid, 5, "policy")
    put_step(nava.db, sid, 6, "approval")        # passed, but cites no approval id
    for n in (7, 8, 9):
        put_step(nava.db, sid, n, NAMES[n - 1])
    nava.db.rejects(f"INSERT INTO syscall_steps(syscall_id, step, name, outcome) VALUES ('{sid}', 10, 'execute', 'pass')",
                    "N07")
    # with a consumed approval bound to args+task+tool, execution is allowed
    sid2 = open_syscall(nava.db, nava.agent, nava.task, tool="x.dangerous", h="c" * 64)
    a = make_approval(nava.db, nava.task, "c" * 64, tool="x.dangerous")
    assert nava.db.one(f"SELECT consume_approval('{a}', '{'c' * 64}', '{nava.task}', 'x.dangerous')") == "t"
    walk(nava.db, sid2, 3)
    put_step(nava.db, sid2, 4, "classify")
    nava.db.q(f"UPDATE syscalls SET risk_class='high' WHERE id='{sid2}'")
    put_step(nava.db, sid2, 5, "policy")
    put_step(nava.db, sid2, 6, "approval", detail=f'{{"approval_id": "{a}"}}')
    for n in (7, 8, 9):
        put_step(nava.db, sid2, n, NAMES[n - 1])
    put_step(nava.db, sid2, 10, "execute")       # accepted


def test_n08_quotas(nava):
    nava.db.q(f"INSERT INTO nava_quotas(agent_id, max_concurrent, max_per_minute) VALUES ('{nava.agent}', 1, 1000)")
    sid = open_syscall(nava.db, nava.agent, nava.task)   # one already running
    r = nava.call(tool="test.echo", args={})
    assert r.status == "denied" and r.step == "quota" and "concurrency" in r.reason
    walk(nava.db, sid, 12, outcome="fail")
    nava.db.q(f"UPDATE syscalls SET status='failed', reason='closed by test' WHERE id='{sid}'")
    assert nava.call(tool="test.echo", args={}).status == "committed"
    # rate quota
    nava.db.q(f"UPDATE nava_quotas SET max_per_minute = 1 WHERE agent_id = '{nava.agent}'")
    r = nava.call(tool="test.echo", args={})
    assert r.status == "denied" and "rate" in r.reason


def test_n09_single_use_approvals(nava):
    h = args_hash({"workspace": "w", "path": "f.txt"})
    a = make_approval(nava.db, nava.task, h, tool="fs.delete")
    nava.ws.path(nava.agent, "w").mkdir(parents=True)
    (nava.ws.path(nava.agent, "w") / "f.txt").write_text("x")
    r = nava.call(tool="fs.delete", args={"workspace": "w", "path": "f.txt"}, mode="ask", approval_id=a)
    assert r.status == "committed"
    (nava.ws.path(nava.agent, "w") / "f.txt").write_text("x")   # recreate; try to reuse the approval
    r2 = nava.call(tool="fs.delete", args={"workspace": "w", "path": "f.txt"}, mode="ask", approval_id=a)
    assert r2.status == "denied" and r2.step == "approval"
    assert nava.db.one("SELECT count(*) FROM audit_log WHERE action='approval.consume_rejected'") >= "1"


# ---- N10..N12: locks --------------------------------------------------------------------------
def test_n10_exclusive_locks(nava):
    s1 = open_syscall(nava.db, nava.agent, nava.task)
    s2 = open_syscall(nava.db, nava.agent, nava.task)
    nava.db.q(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('ws:a/w', '{s1}', 0)")
    nava.db.rejects(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('ws:a/w', '{s2}', 0)", "")
    # and end-to-end: a held lock makes the second call time out at step 8
    s3 = open_syscall(nava.db, nava.agent, nava.task)      # its own syscall: N12 ordering is per call
    nava.db.q(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('{nava.ws.resource(nava.agent, 'held')}', '{s3}', 0)")
    r = nava.call(tool="fs.write", args={"workspace": "held", "path": "a", "content": "b"})
    assert r.status in ("failed", "rolled_back") and r.step == "lock" and "lock timeout" in r.reason


def test_n11_locks_released(nava):
    r = nava.call(tool="fs.write", args={"workspace": "w2", "path": "a.txt", "content": "hi"})
    assert r.status == "committed"
    assert nava.db.q("SELECT resource FROM nava_locks") == []        # released at step 12
    # also on failure
    r2 = nava.call(tool="sandbox.run", args={"workspace": "w2", "argv": ["false"]})
    assert r2.status in ("rolled_back", "failed")
    assert nava.db.q("SELECT resource FROM nava_locks") == []


def test_n12_lock_ordering(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    nava.db.q(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('b', '{sid}', 0)")
    nava.db.rejects(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('a', '{sid}', 1)", "N12")
    nava.db.q(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('c', '{sid}', 1)")


# ---- N13..N17: snapshots, rollback, receipts, reaping -----------------------------------------
def test_n13_snapshot_before_mutation(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task, mutating=True)
    walk(nava.db, sid, 8)
    put_step(nava.db, sid, 9, "snapshot", "skip")     # mutating call that skipped its snapshot
    for n in (10, 11, 12):
        put_step(nava.db, sid, n, NAMES[n - 1])
    nava.db.rejects(f"UPDATE syscalls SET status='committed', receipt_id=NULL WHERE id='{sid}'", "N13")


def test_n14_rollback_restores_snapshot(nava):
    ws = nava.ws.path(nava.agent, "w3")
    ws.mkdir(parents=True)
    (ws / "keep.txt").write_text("original")
    # the command mutates the workspace, then fails -> rollback must restore the exact state
    r = nava.call(tool="sandbox.run",
                  args={"workspace": "w3", "argv": ["sh", "-c", "echo garbage > keep.txt; touch junk; exit 1"]})
    assert r.status == "rolled_back"
    assert (ws / "keep.txt").read_text() == "original" and not (ws / "junk").exists()
    assert r.restored_hash == r.snapshot_hash
    row = nava.db.one(f"SELECT restored_hash = snapshot_hash FROM syscalls WHERE id='{r.id}'")
    assert row == "t"
    # the database refuses a rolled_back row whose hashes differ
    nava.db.rejects(f"INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating, status, snapshot_hash, "
                    f"restored_hash, ended_at) VALUES ('{nava.agent}', '{nava.task}', 't', '{H}', true, "
                    f"'rolled_back', 'aaa', 'bbb', now())", "")


def test_n15_commit_needs_all_steps(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    walk(nava.db, sid, 9)                     # verify (11) never ran
    put_step(nava.db, sid, 10, "execute", "fail")
    put_step(nava.db, sid, 12, "record", "fail")
    nava.db.rejects(f"UPDATE syscalls SET status='committed' WHERE id='{sid}'", "N15")


def test_n16_commit_needs_receipt(nava):
    sid = open_syscall(nava.db, nava.agent, nava.task)
    walk(nava.db, sid, 12)
    nava.db.rejects(f"UPDATE syscalls SET status='committed', receipt_id=NULL WHERE id='{sid}'", "N16")
    # a receipt for a different args hash is not this call's receipt
    other = nava.db.one(f"INSERT INTO tool_calls(task_id, agent_id, mcp_server, tool, args_hash, args_redacted, "
                        f"latency_ms, cost, risk_class, verdict) VALUES ('{nava.task}', '{nava.agent}', 'runtime-os', "
                        f"'test.echo', '{'d' * 64}', '{{}}', 1, 0, 'low', 'ok') RETURNING id")
    nava.db.rejects(f"UPDATE syscalls SET status='committed', receipt_id='{other}' WHERE id='{sid}'", "N16")
    # the gateway's own commit satisfies it
    r = nava.call(tool="test.echo", args={"text": "receipted"})
    assert r.status == "committed" and r.receipt_id
    assert nava.db.one(f"SELECT count(*) FROM tool_calls WHERE id='{r.receipt_id}'") == "1"


def test_n17_crash_reap(nava):
    ws = nava.ws.path(nava.agent, "w4")
    ws.mkdir(parents=True)
    (ws / "state.txt").write_text("before")
    # simulate a gateway that died between snapshot and execute
    r_args = {"workspace": "w4"}
    sid = open_syscall(nava.db, nava.agent, nava.task, tool="fs.write", h=args_hash(r_args), mutating=True)
    walk(nava.db, sid, 8)
    snap = nava.ws.snapshot(sid, [nava.ws.resource(nava.agent, "w4")])
    nava.db.q(f"UPDATE syscalls SET snapshot_hash='{snap}' WHERE id='{sid}'")
    put_step(nava.db, sid, 9, "snapshot")
    nava.db.q(f"INSERT INTO nava_locks(resource, syscall_id, ord) VALUES ('ws:x', '{sid}', 0)")
    (ws / "state.txt").write_text("half-written")                 # the crash left damage
    nava.db.q(f"UPDATE syscalls SET started_at = now() - interval '1 hour' WHERE id='{sid}'")
    reaped = nava.gw.reap(older_than_s=60)
    assert sid in reaped
    assert (ws / "state.txt").read_text() == "before"             # restored
    assert nava.db.one(f"SELECT status FROM syscalls WHERE id='{sid}'") == "rolled_back"
    assert nava.db.q("SELECT resource FROM nava_locks") == []     # freed
    assert nava.db.q("SELECT id FROM syscalls WHERE status='running'") == []


# ---- N18..N21: bus, memory, subagents ----------------------------------------------------------
def test_n18_bus_sender_and_immutability(nava):
    seq = nava.k.send(nava.agent, nava.other, "jobs", {"kind": "ping"})
    assert seq >= 1
    nava.db.q(f"UPDATE agents SET status='killed' WHERE id='{nava.agent}'")
    nava.db.rejects(f"SELECT a2a_send('{nava.agent}', '{nava.other}', 'jobs', '{{}}')", "N18")
    nava.db.rejects(f"UPDATE a2a_messages SET body='{{}}' WHERE seq={seq}", "append-only")
    nava.db.rejects(f"DELETE FROM a2a_messages WHERE seq={seq}", "append-only")


def test_n19_inbox_isolation(nava):
    nava.k.send(nava.agent, nava.other, "jobs", {"n": 1})
    nava.k.send(nava.other, nava.agent, "jobs", {"n": 2})
    mine = nava.k.inbox(nava.agent)
    theirs = nava.k.inbox(nava.other)
    assert [m["body"]["n"] for m in mine] == [2]
    assert [m["body"]["n"] for m in theirs] == [1]
    # ordering: seq is monotonic per recipient
    nava.k.send(nava.other, nava.agent, "jobs", {"n": 3})
    seqs = [m["seq"] for m in nava.k.inbox(nava.agent)]
    assert seqs == sorted(seqs)
    # after= pagination never re-reads
    assert [m["body"]["n"] for m in nava.k.inbox(nava.agent, after=seqs[0])] == [3]


def test_n20_memory_tiers(nava):
    # four tiers, no fifth
    nava.db.rejects(f"INSERT INTO nava_memory(agent_id, tier, key, value) VALUES ('{nava.agent}', 'eternal', 'k', '1')", "")
    # working memory requires a task and dies with it
    nava.db.rejects(f"INSERT INTO nava_memory(agent_id, tier, key, value) VALUES ('{nava.agent}', 'working', 'k', '1')", "")
    nava.k.remember(nava.agent, "working", "scratch", {"v": 1}, task_id=nava.task)
    nava.k.remember(nava.agent, "episodic", "happened", {"v": 2})
    # semantic/procedural need provenance
    nava.db.rejects(f"INSERT INTO nava_memory(agent_id, tier, key, value) VALUES ('{nava.agent}', 'semantic', 'k', '1')", "")
    r = nava.call(tool="test.echo", args={"text": "s"})
    nava.k.remember(nava.agent, "semantic", "fact", {"v": 3}, source_syscall=r.id)
    nava.k.remember(nava.agent, "procedural", "howto", {"v": 4}, source_syscall=r.id)
    assert {m["tier"] for m in nava.k.recall(nava.agent)} == {"working", "episodic", "semantic", "procedural"}
    nava.db.q(f"UPDATE tasks SET state='CANCELLED' WHERE id='{nava.task}'")
    tiers = {m["tier"] for m in nava.k.recall(nava.agent)}
    assert "working" not in tiers and {"episodic", "semantic", "procedural"} <= tiers


def test_n21_jit_subagents(nava):
    child = nava.k.spawn(nava.agent, "summarize inbox", ttl_s=60, denies=["sandbox.*"])
    cid = child["agent_id"]
    # scoped: its own deny plus every parent deny (N04 test covers inheritance)
    r = nava.gw.syscall(caller_agent=cid, agent_id=cid, task_id=nava.task, tool="sandbox.run",
                        args={"workspace": "w", "argv": ["true"]})
    assert r.status == "denied" and r.step == "authorize"
    assert nava.gw.syscall(caller_agent=cid, agent_id=cid, task_id=nava.task, tool="test.echo",
                           args={}).status == "committed"
    # no sub-subagents
    try:
        nava.k.spawn(cid, "grandchild")
        raise AssertionError("subagent spawned a subagent")
    except PermissionError:
        pass
    # mortal: expiry kills it and its token stops authenticating
    assert nava.k.authenticate(child["token"]) == cid
    nava.db.q(f"UPDATE nava_subagents SET expires_at = now() - interval '1 second' WHERE agent_id='{cid}'")
    assert nava.db.one("SELECT nava_expire_subagents()") == "1"
    assert nava.db.one(f"SELECT status FROM agents WHERE id='{cid}'") == "killed"
    assert nava.k.authenticate(child["token"]) is None
    nava.db.rejects(f"INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating) "
                    f"VALUES ('{cid}', '{nava.task}', 't', '{H}', false)", "N03")
