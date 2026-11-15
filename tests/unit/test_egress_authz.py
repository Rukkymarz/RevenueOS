"""egress-authz HTTP surface (INV-11): identity pinning, per-agent and per-task rules from
Postgres, secret injection by reference, fail-closed, and an egress_log row (+ audit) for every
decision."""
import importlib
import sys
import uuid

import pytest
from starlette.testclient import TestClient

from dbkit import HOST, PORT, USER
from revenueos_common import egress_identity
from revenueos_common.secrets import KeychainStore, SecretResolver

KEY = "identity-key-" + "x" * 20
SECRET = "-".join(["fixture", "value", "123"])   # built, not a literal, so the hygiene scan stays strict


@pytest.fixture
def env(db, world, tmp_path, monkeypatch):
    for k, v in {"PGHOST": HOST, "PGPORT": PORT, "PGUSER": USER, "PGDATABASE": db.name}.items():
        monkeypatch.setenv(k, v)   # the module-level Database and its /health check bind at import
    sys.modules.pop("revenueos_egress_authz.app", None)
    mod = importlib.import_module("revenueos_egress_authz.app")
    kc = KeychainStore(tmp_path / "kc")
    kc.put("egress-identity-hmac", KEY)
    kc.put("upstream-echo-token", SECRET)
    monkeypatch.setattr(mod, "secrets", SecretResolver(kc))
    monkeypatch.setattr(mod, "_cache", {"at": 0.0, "policy": None})
    a, t = world["exec"], world["task"]
    db.q(f"INSERT INTO egress_rules(agent_id, host, created_by) VALUES ('{a}','upstream-echo:8080','t')")
    db.q(f"INSERT INTO egress_rules(agent_id, task_id, host, created_by) VALUES ('{a}','{t}','task-only:80','t')")
    db.q(f"INSERT INTO secret_bindings(secret_ref, host, header, format, agent_ids) "
         f"VALUES ('keychain://upstream-echo-token','upstream-echo:8080','authorization','Bearer {{}}',ARRAY['{a}']::uuid[])")
    session = db.one(f"INSERT INTO egress_sessions(agent_id, task_id, socket_path) VALUES ('{a}','{t}','/s/{uuid.uuid4()}') RETURNING id")
    return mod, TestClient(mod.app), db, {"agent": a, "task": t, "session": session}


def hdrs(ids, host="upstream-echo:8080", key=KEY, **override):
    stamp = egress_identity.sign(key, ids["session"], ids["agent"], ids["task"])
    h = {k.replace("x-revenueos-", "x-egress-"): v for k, v in stamp.items()}
    h.update({"x-egress-host": host, "x-egress-method": "GET", "x-egress-path": "/ok"})
    h.update(override)
    return h


def last_log(db):
    return db.one("SELECT decision||'|'||reason||'|'||injected_secrets FROM egress_log ORDER BY created_at DESC LIMIT 1")


def test_pinned_allowed_request_injects_the_secret_and_logs_without_it(env):
    _, c, db, ids = env
    r = c.post("/v1/check", headers=hdrs(ids))
    assert r.status_code == 200 and r.text == f"authorization=Bearer {SECRET}\n"
    assert last_log(db) == "allow|allowlisted|1"
    assert SECRET not in "".join(db.q("SELECT payload::text FROM audit_log"))


def test_task_scoped_rule_applies_only_to_that_task(env):
    _, c, db, ids = env
    assert c.post("/v1/check", headers=hdrs(ids, host="task-only:80")).status_code == 200
    other = db.one(f"INSERT INTO egress_sessions(agent_id, socket_path) VALUES ('{ids['agent']}','/s/other') RETURNING id")
    r = c.post("/v1/check", headers=hdrs({**ids, "session": other, "task": ""}, host="task-only:80"))
    assert r.status_code == 403 and "not allowlisted" in r.json()["reason"]


@pytest.mark.parametrize("attack,reason", [
    ("unsigned", "not identity-pinned"),
    ("other_agent", "signature invalid"),
    ("wrong_key", "signature invalid"),
    ("stale", "expired"),
    ("closed", "session closed"),
    ("foreign_session", "does not belong"),
    ("unknown_session", "unknown egress session"),
])
def test_identity_attacks_are_denied_and_logged(env, attack, reason):
    _, c, db, ids = env
    h = hdrs(ids)
    if attack == "unsigned":
        h = {"x-egress-agent": ids["agent"], "x-egress-host": "upstream-echo:8080", "x-egress-method": "GET"}
    elif attack == "other_agent":
        h["x-egress-agent"] = str(uuid.uuid4())
    elif attack == "wrong_key":
        h = hdrs(ids, key="guess")
    elif attack == "stale":
        stamp = egress_identity.sign(KEY, ids["session"], ids["agent"], ids["task"], ts=1)
        h.update({k.replace("x-revenueos-", "x-egress-"): v for k, v in stamp.items()})
    elif attack == "closed":
        db.q(f"UPDATE egress_sessions SET closed_at=now() WHERE id='{ids['session']}'")
    elif attack == "foreign_session":
        other = db.one(f"INSERT INTO egress_sessions(agent_id, socket_path) VALUES ('{ids['agent']}','/s/f') RETURNING id")
        h = hdrs({**ids, "session": other})   # validly signed, but that session has no task
    elif attack == "unknown_session":
        h = hdrs({**ids, "session": str(uuid.uuid4())})
    r = c.post("/v1/check", headers=h)
    assert r.status_code == 403 and reason in r.json()["reason"]
    assert last_log(db).startswith("deny|") and reason in last_log(db)


def test_unlisted_host_is_denied_logged_and_audited(env):
    _, c, db, ids = env
    r = c.post("/v1/check", headers=hdrs(ids, host="exfil.example:443"))
    assert r.status_code == 403 and "not allowlisted" in r.json()["reason"]
    assert db.one("SELECT count(*) FROM audit_log WHERE action='egress.deny' AND target='exfil.example:443'") == "1"


def test_policy_or_database_failure_fails_closed(env, monkeypatch):
    mod, c, _, ids = env

    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(mod, "cached_policy", boom)
    r = c.post("/v1/check", headers=hdrs(ids))
    assert r.status_code == 403 and "policy error" in r.json()["reason"]


def test_missing_identity_key_fails_closed(env, monkeypatch, tmp_path):
    mod, c, _, ids = env
    monkeypatch.setattr(mod, "secrets", SecretResolver(KeychainStore(tmp_path / "empty")))
    r = c.post("/v1/check", headers=hdrs(ids))
    assert r.status_code == 403 and "fail closed" in r.json()["reason"]


def test_health_reports_database_and_identity_key(env):
    _, c, _, _ = env
    assert c.get("/health").json()["checks"] == {"postgres": "ok", "identity_key": "ok"}


def test_policy_is_built_from_postgres(env):
    mod, _, _, ids = env
    p = mod.load_policy()
    assert p["agents"][ids["agent"]] == {"allow": ["upstream-echo:8080"], "tasks": {ids["task"]: ["task-only:80"]}}
    assert p["secret_bindings"][0]["agents"] == [ids["agent"]]
