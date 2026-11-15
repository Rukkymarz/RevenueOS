"""Sandbox supervisor service: every run is recorded (sandbox_sessions + audit), blocked runs
included; egress sessions are recorded and closed; bad input is refused."""
import importlib
import uuid

import pytest
from starlette.testclient import TestClient

from dbkit import HOST, PORT, USER
from revenueos_common.db import Database
from sandbox_kit import needs_sandbox


@pytest.fixture
def svc(db, world, tmp_path, monkeypatch):
    mod = importlib.import_module("revenueos_sandbox_supervisor.app")
    monkeypatch.setattr(mod, "db", Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="sandbox-supervisor"))
    monkeypatch.setattr(mod, "WORKSPACE_ROOT", tmp_path / "ws")
    monkeypatch.setattr(mod, "_ca", {})
    return mod, TestClient(mod.app), db, world


def test_blocked_run_is_recorded_and_audited(svc):
    _, c, db, w = svc
    r = c.post("/v1/run", json={"agent_id": w["exec"], "argv": ["rm", "-rf", "/"], "yolo": True}).json()
    assert r["status"] == "blocked" and r["exit_code"] is None
    assert db.one(f"SELECT status||'|'||yolo FROM sandbox_sessions WHERE agent_id='{w['exec']}'") == "blocked|true"
    assert db.one("SELECT count(*) FROM audit_log WHERE action='sandbox.blocked'") == "1"


@pytest.mark.parametrize("body,err", [
    ({"agent_id": "nope", "argv": ["true"]}, "UUID"),
    ({"agent_id": str(uuid.uuid4()), "argv": "true"}, "argv"),
    ({"agent_id": str(uuid.uuid4()), "argv": ["true"], "workspace": "../../etc"}, "plain name"),
    ({"agent_id": str(uuid.uuid4()), "argv": ["true"], "quotas": {"bogus": 1}}, "bogus"),
])
def test_bad_requests_are_refused(svc, body, err):
    _, c, _, _ = svc
    r = c.post("/v1/run", json=body)
    assert r.status_code == 400 and err in r.json()["error"]


def test_egress_without_identity_key_fails_closed(svc, tmp_path, monkeypatch):
    mod, c, _, w = svc
    from revenueos_common.secrets import KeychainStore, SecretResolver
    monkeypatch.setattr(mod, "secrets", SecretResolver(KeychainStore(tmp_path / "kc")))
    r = c.post("/v1/run", json={"agent_id": w["exec"], "argv": ["true"], "egress": True})
    assert r.status_code == 503 and "fail closed" in r.json()["error"]


@needs_sandbox
def test_run_with_egress_records_both_sessions(svc, tmp_path, monkeypatch):
    mod, c, db, w = svc
    from revenueos_common.secrets import KeychainStore, SecretResolver
    kc = KeychainStore(tmp_path / "kc")
    kc.put("egress-identity-hmac", "k" * 32)
    monkeypatch.setattr(mod, "secrets", SecretResolver(kc))
    (tmp_path / "ws" / w["exec"] / "proj").mkdir(parents=True)
    r = c.post("/v1/run", json={"agent_id": w["exec"], "task_id": w["task"], "argv": ["sh", "-c", "echo hi > out.txt"],
                                "workspace": "proj", "egress": True}).json()
    assert r["status"] == "ok" and r["changes"] == {"out.txt": "added"}
    assert db.one(f"SELECT status FROM sandbox_sessions WHERE agent_id='{w['exec']}'") == "finished"
    assert db.one(f"SELECT changeset_hash FROM sandbox_sessions WHERE agent_id='{w['exec']}'") == r["changeset_hash"]
    assert db.one(f"SELECT (closed_at IS NOT NULL)::text FROM egress_sessions WHERE agent_id='{w['exec']}'") == "true"
    assert not (tmp_path / "ws" / w["exec"] / "proj" / "out.txt").exists()
    assert TestClient(mod.app).get("/health").json()["checks"]["bubblewrap"]


def test_health_reports_the_egress_ca(svc, tmp_path, monkeypatch):
    mod, c, _, _ = svc
    from revenueos_common.secrets import KeychainStore, SecretResolver
    from revenueos_sandbox.tls import generate_ca
    kc = KeychainStore(tmp_path / "kc2")
    monkeypatch.setattr(mod, "secrets", SecretResolver(kc))
    assert c.get("/health").json()["checks"]["egress_ca"] != "ok"
    cert, key = generate_ca()
    kc.put("egress-ca-cert", cert)
    kc.put("egress-ca-key", key)
    monkeypatch.setattr(mod, "_ca", {})
    assert mod._egress_ca() is not None


def test_closing_an_egress_session_never_raises():
    from revenueos_sandbox.records import egress_hooks

    class Broken:
        def scalar(self, *a, **k):
            raise RuntimeError("db hiccup")

    class S:
        session_id = "00000000-0000-4000-8000-000000000000"
    _, closed = egress_hooks(Broken())
    closed(S())   # logged, not raised
