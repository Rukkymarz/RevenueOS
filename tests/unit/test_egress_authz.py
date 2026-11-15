"""egress-authz HTTP surface: every decision is answered, contract-checked and audited."""
import importlib
import sys

import pytest
from starlette.testclient import TestClient

from dbkit import HOST, PORT, USER

AGENT = "7a1c2e30-0001-4000-8000-000000000001"


@pytest.fixture
def client(db, tmp_path, monkeypatch):
    pytest.importorskip("revenueos_contracts.models")
    kc = tmp_path / "kc"
    policy = tmp_path / "policy.yaml"
    policy.write_text(f"""agents:
  "{AGENT}": {{allow: ["upstream-echo:8080"]}}
secret_bindings:
  - {{host: "upstream-echo:8080", header: authorization, format: "Bearer {{}}", secret_ref: "keychain://tok", agents: ["{AGENT}"]}}
""")
    for k, v in {"PGHOST": HOST, "PGPORT": PORT, "PGUSER": USER, "PGDATABASE": db.name,
                 "REVENUEOS_KEYCHAIN_DIR": str(kc), "EGRESS_POLICY": str(policy)}.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("revenueos_egress_authz.app", None)
    mod = importlib.import_module("revenueos_egress_authz.app")
    from revenueos_common.secrets import KeychainStore
    KeychainStore(kc).put("tok", "s3cret-xyz")
    db.q(f"INSERT INTO agents(id, name, role, framework, budget_monthly) VALUES ('{AGENT}','probe','probe','x',1)")
    return TestClient(mod.app), db


def hdrs(agent=AGENT, host="upstream-echo:8080"):
    return {"x-egress-agent": agent, "x-egress-host": host, "x-egress-method": "GET", "x-egress-path": "/ok"}


def test_allowed_request_returns_injection_lines_and_audits_without_the_secret(client):
    c, db = client
    r = c.post("/v1/check", headers=hdrs())
    assert r.status_code == 200 and r.text == "authorization=Bearer s3cret-xyz\n"
    logged = db.one("SELECT payload::text FROM audit_log WHERE action='egress.allow'")
    assert '"injected_secrets": 1' in logged and "s3cret" not in logged


def test_denied_request_returns_403_and_audits_the_reason(client):
    c, db = client
    r = c.post("/v1/check", headers=hdrs(host="evil.example:443"))
    assert r.status_code == 403 and "not allowlisted" in r.json()["reason"]
    assert db.one("SELECT target FROM audit_log WHERE action='egress.deny'") == "evil.example:443"


def test_policy_failure_fails_closed(client, monkeypatch, tmp_path):
    c, db = client
    monkeypatch.setenv("EGRESS_POLICY", str(tmp_path / "missing.yaml"))
    import revenueos_egress_authz.app as mod
    monkeypatch.setattr(mod, "POLICY_PATH", tmp_path / "missing.yaml")
    r = c.post("/v1/check", headers=hdrs())
    assert r.status_code == 403 and "policy error" in r.json()["reason"]


def test_health_reports_database_and_policy(client):
    c, _ = client
    assert c.get("/health").json()["checks"] == {"postgres": "ok", "policy": "ok"}
