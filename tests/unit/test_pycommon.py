"""Unit tests for packages/pycommon: hashing, database access, secrets, service skeleton, CLI."""
import json
import math
import os

import pytest
from starlette.testclient import TestClient

from dbkit import HOST, PORT, USER
from revenueos_common import canonical, cli
from revenueos_common.db import Database, DatabaseError
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretError, SecretResolver, parse_ref
from revenueos_common.service import create_app


# ---------------------------------------------------------------- canonical hashing
def test_hash_is_independent_of_key_order_and_whitespace():
    assert canonical.args_hash({"b": 1, "a": [1, 2]}) == canonical.args_hash({"a": [1, 2], "b": 1})


def test_one_changed_byte_changes_the_hash():
    assert canonical.args_hash({"to": "a@b.co"}) != canonical.args_hash({"to": "a@b.cO"})


@pytest.mark.parametrize("bad", [math.nan, math.inf, {1: "x"}, object()])
def test_non_canonical_values_are_rejected(bad):
    with pytest.raises(ValueError):
        canonical.canonical_json({"v": bad} if not isinstance(bad, dict) else bad)


def test_redact_masks_secret_looking_keys_recursively():
    out = canonical.redact({"api_key": "x", "nested": [{"Authorization": "Bearer y", "ok": 1}]})
    assert out == {"api_key": "[redacted]", "nested": [{"Authorization": "[redacted]", "ok": 1}]}


# ---------------------------------------------------------------- database access
@pytest.fixture
def pg(db):
    return Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="unit")


def test_rows_returns_dicts_and_binds_parameters(pg):
    rows = pg.rows("SELECT $a AS a, #b AS b", a="x", b={"k": [1]})
    assert rows == [{"a": "x", "b": {"k": [1]}}]


def test_parameters_cannot_inject_sql(pg):
    hostile = "x'); DROP TABLE agents; --"
    assert pg.scalar("SELECT $v AS v", v=hostile) == hostile
    assert pg.scalar("SELECT count(*) AS n FROM agents") == 0


def test_none_binds_as_sql_null(pg):
    assert pg.scalar("SELECT $v IS NULL AS isnull", v=None) is True


def test_database_errors_surface_the_server_message(pg):
    with pytest.raises(DatabaseError) as e:
        pg.scalar("INSERT INTO tasks(objective, task_class, state) VALUES ('x','code','COMPLETED') RETURNING id")
    assert "created in DRAFT" in e.value.message


def test_actor_is_recorded_on_audit_entries(pg):
    pg.with_actor("agent:unit-test").scalar("INSERT INTO tasks(objective, task_class) VALUES ('t','code') RETURNING id")
    assert pg.scalar("SELECT actor FROM audit_log ORDER BY seq DESC LIMIT 1") == "agent:unit-test"


# ---------------------------------------------------------------- secrets
def test_keychain_round_trip_and_permissions(tmp_path):
    store = KeychainStore(tmp_path / "kc")
    store.put("token", "abc")
    assert oct((tmp_path / "kc" / "token").stat().st_mode & 0o777) == "0o600"
    assert SecretResolver(store).get("keychain://token") == "abc"
    assert SecretResolver(store).get("keychain://absent") is None


def test_world_readable_secret_is_refused(tmp_path):
    store = KeychainStore(tmp_path / "kc")
    store.put("token", "abc")
    os.chmod(tmp_path / "kc" / "token", 0o644)
    with pytest.raises(SecretError):
        store.get("token")


@pytest.mark.parametrize("ref", ["hunter2", "keychain://../etc/passwd", "s3://bucket/key", "keychain://"])
def test_invalid_secret_references_are_rejected(ref):
    with pytest.raises(SecretError):
        parse_ref(ref)


# ---------------------------------------------------------------- service skeleton and registry
def test_health_is_ok_only_when_every_check_passes():
    ok = TestClient(create_app("svc", checks={"a": lambda: True}))
    r = ok.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["checks"] == {"a": "ok"}


def test_failing_or_crashing_check_reports_503_with_the_check_named():
    def boom():
        raise RuntimeError("db down")
    c = TestClient(create_app("svc", checks={"a": lambda: True, "b": lambda: False, "c": boom}))
    body = c.get("/health").json()
    assert c.get("/health").status_code == 503
    assert body["status"] == "degraded" and body["checks"]["b"] == "failed" and "db down" in body["checks"]["c"]


def test_registry_reads_the_component_map():
    assert config_loaded()
    assert "langgraph" in components_for("C01")


# ---------------------------------------------------------------- `revenueos audit verify`
@pytest.fixture
def cli_env(db, monkeypatch):
    monkeypatch.setenv("PGHOST", HOST)
    monkeypatch.setenv("PGPORT", PORT)
    monkeypatch.setenv("PGUSER", USER)
    return db


def test_audit_verify_exits_zero_on_an_intact_chain(cli_env, world, capsys):
    assert cli.main(["audit", "verify", "--db", cli_env.name]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "intact" and out["rows"] >= 1 and len(out["head"]) == 64


def test_audit_verify_exits_nonzero_and_names_the_tampered_row(cli_env, world, capsys):
    db = cli_env
    seq = db.one("SELECT min(seq) FROM audit_log")
    row_id = db.one(f"SELECT id FROM audit_log WHERE seq={seq}")
    db.q("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_append_only; "
         f"UPDATE audit_log SET payload = '{{\"forged\": true}}' WHERE seq={seq}; "
         "ALTER TABLE audit_log ENABLE TRIGGER trg_audit_append_only")
    assert cli.main(["audit", "verify", "--db", db.name]) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "tampered"
    assert report["first_broken"]["seq"] == int(seq) and report["first_broken"]["id"] == row_id
    assert f"seq {seq}" in captured.err and row_id in captured.err


def test_audit_export_writes_every_row(cli_env, world, tmp_path, capsys):
    out = tmp_path / "ledger.jsonl"
    assert cli.main(["audit", "export", str(out), "--db", cli_env.name]) == 0
    lines = out.read_text().splitlines()
    assert len(lines) == int(cli_env.one("SELECT count(*) FROM audit_log"))
    assert all(len(json.loads(line)["hash"]) == 64 for line in lines)
