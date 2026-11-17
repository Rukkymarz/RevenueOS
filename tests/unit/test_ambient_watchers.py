"""ambient-watchers (C02): real-Postgres tests for the scanner that watches NAVA's own durable
state for subagents about to be killed by TTL, approvals about to expire unused, and syscalls
stuck in `running` past a staleness threshold. No mocks: these are the production triggers and
constraints, same pattern as tests/nava."""
import pytest

import dbkit
from revenueos_common.db import Database
from revenueos_ambient_watchers.watchers import AmbientWatchers, Finding, ensure_registered, main


@pytest.fixture
def pgdb(db):
    return Database(dbname=db.name, host=dbkit.HOST, port=dbkit.PORT, user=dbkit.USER, actor="ambient-test")


@pytest.fixture
def self_agent(db):
    return db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                  "VALUES ('ambient-watchers','watcher','nava-static',0) RETURNING id")


def test_ensure_registered_is_idempotent(db, pgdb):
    first = ensure_registered(pgdb)
    second = ensure_registered(pgdb)
    assert first == second
    rows = db.q(f"SELECT count(*) FROM agents WHERE name = 'ambient-watchers'")
    assert rows[0] == "1"


def test_scan_finds_expiring_subagent(db, pgdb, world, self_agent):
    sub = db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                 "VALUES ('sub-1','jit','nava-static',0) RETURNING id")
    db.q(f"INSERT INTO nava_subagents(agent_id, parent_agent_id, objective, expires_at) "
         f"VALUES ('{sub}','{world['exec']}','scrape a page', now() + interval '10 seconds')")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, subagent_warn_s=60)
    findings = w.scan()

    matches = [f for f in findings if f.kind == "subagent_expiring" and f.detail["subagent_id"] == sub]
    assert len(matches) == 1
    assert matches[0].agent_id == world["exec"]   # notified: the parent, not the subagent itself
    assert matches[0].detail["objective"] == "scrape a page"
    assert 0 <= matches[0].detail["seconds_left"] <= 10


def test_scan_ignores_subagent_outside_warn_window(db, pgdb, world, self_agent):
    sub = db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                 "VALUES ('sub-2','jit','nava-static',0) RETURNING id")
    db.q(f"INSERT INTO nava_subagents(agent_id, parent_agent_id, objective, expires_at) "
         f"VALUES ('{sub}','{world['exec']}','later', now() + interval '1 hour')")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, subagent_warn_s=60)
    assert [f for f in w.scan() if f.detail.get("subagent_id") == sub] == []


def test_scan_finds_expiring_approval_for_an_agent_requester(db, pgdb, world, self_agent):
    args_hash = "a" * 64
    approval = db.one(
        "INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at) "
        f"VALUES ('{world['task']}','{args_hash}','agent:{world['exec']}', now() + interval '10 seconds') "
        "RETURNING id")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, approval_warn_s=60)
    findings = [f for f in w.scan() if f.kind == "approval_expiring"]

    assert len(findings) == 1
    assert findings[0].agent_id == world["exec"]
    assert findings[0].detail["approval_id"] == approval
    assert findings[0].task_id == world["task"]


def test_scan_skips_approval_requested_by_a_human(db, pgdb, world, self_agent):
    args_hash = "b" * 64
    db.q(
        "INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at) "
        f"VALUES ('{world['task']}','{args_hash}','human:christine', now() + interval '10 seconds')")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, approval_warn_s=60)
    assert [f for f in w.scan() if f.kind == "approval_expiring"] == []


def test_scan_finds_stuck_syscall(db, pgdb, world, self_agent):
    args_hash = "c" * 64
    sid = db.one(
        "INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating, started_at) "
        f"VALUES ('{world['exec']}','{world['task']}','fs.read','{args_hash}', false, "
        "now() - interval '10 minutes') RETURNING id")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, syscall_stale_s=300)
    findings = [f for f in w.scan() if f.kind == "syscall_stuck"]

    assert len(findings) == 1
    assert findings[0].detail["syscall_id"] == sid
    assert findings[0].detail["tool"] == "fs.read"
    assert findings[0].detail["running_for"] >= 599


def test_scan_ignores_syscall_running_briefly(db, pgdb, world, self_agent):
    args_hash = "d" * 64
    db.q(
        "INSERT INTO syscalls(agent_id, task_id, tool, args_hash, mutating, started_at) "
        f"VALUES ('{world['exec']}','{world['task']}','fs.read','{args_hash}', false, now()) RETURNING id")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, syscall_stale_s=300)
    assert [f for f in w.scan() if f.kind == "syscall_stuck"] == []


def test_emit_writes_episodic_memory_and_a2a_message(db, pgdb, world, self_agent):
    finding = Finding("subagent_expiring", world["exec"], None,
                       {"subagent_id": world["ver"], "objective": "x", "seconds_left": 5})
    w = AmbientWatchers(pgdb, self_agent_id=self_agent)

    msg_id = w.emit(finding)
    assert msg_id

    mem = db.q(
        f"SELECT tier, key FROM nava_memory WHERE agent_id = '{self_agent}' "
        "AND key = 'ambient.subagent_expiring'")
    assert mem and mem[0] == "episodic|ambient.subagent_expiring"

    inbox = db.q(f"SELECT channel FROM a2a_messages WHERE to_agent = '{world['exec']}'")
    assert "ambient.alert" in inbox


def test_scan_and_emit_covers_every_finding(db, pgdb, world, self_agent):
    sub = db.one("INSERT INTO agents(name, role, framework, budget_monthly) "
                 "VALUES ('sub-3','jit','nava-static',0) RETURNING id")
    db.q(f"INSERT INTO nava_subagents(agent_id, parent_agent_id, objective, expires_at) "
         f"VALUES ('{sub}','{world['exec']}','x', now() + interval '5 seconds')")

    w = AmbientWatchers(pgdb, self_agent_id=self_agent, subagent_warn_s=60)
    findings = w.scan_and_emit()

    assert len(findings) == 1
    sent = db.q(f"SELECT count(*) FROM a2a_messages WHERE channel = 'ambient.alert'")
    assert sent[0] == "1"


def test_main_once_prints_json_findings(db, monkeypatch):
    """`--once` is the CLI entrypoint compose/cron would invoke; it must connect using the
    standard PG* env vars (via Database()) and print one JSON array, not loop."""
    monkeypatch.setenv("PGDATABASE", db.name)
    monkeypatch.setenv("PGHOST", dbkit.HOST)
    monkeypatch.setenv("PGPORT", dbkit.PORT)
    monkeypatch.setenv("PGUSER", dbkit.USER)

    rc = main(["--once"])
    assert rc == 0


def test_main_once_prints_findings_for_an_agent_with_a_live_finding(db, world, monkeypatch, capsys):
    monkeypatch.setenv("PGDATABASE", db.name)
    monkeypatch.setenv("PGHOST", dbkit.HOST)
    monkeypatch.setenv("PGPORT", dbkit.PORT)
    monkeypatch.setenv("PGUSER", dbkit.USER)
    args_hash = "e" * 64
    db.q(
        "INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, expires_at) "
        f"VALUES ('{world['task']}','{args_hash}','agent:{world['exec']}', now() + interval '5 seconds')")

    rc = main(["--once"])

    assert rc == 0
    import json as _json
    findings = _json.loads(capsys.readouterr().out)
    assert any(f["kind"] == "approval_expiring" for f in findings)
