"""Phase 1 acceptance against the live compose stack (run with REVENUEOS_E2E=1 after
`docker compose -f infra/compose.yaml --profile test up --wait`)."""
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.skipif(os.environ.get("REVENUEOS_E2E") != "1", reason="needs the running compose stack")

ROOT = Path(__file__).resolve().parents[2]
API, CC, ENVOY = "http://127.0.0.1:3000", "http://127.0.0.1:3001", "http://127.0.0.1:10000"
AGENT = "7a1c2e30-0001-4000-8000-000000000001"
TASK = "7a1c2e30-0002-4000-8000-000000000001"
SECRETS = ROOT / "infra" / "secrets"


def psql(sql: str) -> str:
    env = {**os.environ, "PGPASSFILE": str(SECRETS / "pgpass_host")}
    r = subprocess.run(["psql", "-h", "127.0.0.1", "-U", "revenueos_owner", "-d", "revenueos", "-X", "-A", "-t", "-c", sql],
                       capture_output=True, text=True, env=env, check=True)
    return r.stdout.strip()


def test_api_health_200():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200 and r.json()["checks"]["postgres"] == "ok"


def test_command_center_renders_shell():
    r = requests.get(CC, timeout=10)
    assert r.status_code == 200 and "Command center" in r.text


def test_all_compose_services_healthy():
    out = subprocess.run(["docker", "compose", "-f", str(ROOT / "infra/compose.yaml"), "--profile", "test", "ps", "--format", "json"],
                         capture_output=True, text=True, check=True).stdout
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    running = {r["Service"]: r.get("Health") or r["State"] for r in rows}
    unhealthy = {s: h for s, h in running.items() if h not in ("healthy", "running") and s != "migrate"}
    assert not unhealthy, unhealthy


def _spans_for(trace_id: str) -> list[dict]:
    found = []
    path = ROOT / "infra" / "otel" / "out" / "traces.jsonl"
    for line in path.read_text().splitlines() if path.exists() else []:
        for rs in json.loads(line).get("resourceSpans", []):
            svc = next((a["value"].get("stringValue") for a in rs["resource"]["attributes"] if a["key"] == "service.name"), None)
            for ss in rs.get("scopeSpans", []):
                for sp in ss.get("spans", []):
                    if sp["traceId"].lower() == trace_id:
                        attrs = {a["key"]: next(iter(a["value"].values())) for a in sp.get("attributes", [])}
                        found.append({"service": svc, "name": sp["name"], "attrs": attrs})
    return found


def test_otel_span_chain_api_to_orchestrator_to_mcp_with_all_four_attributes():
    r = requests.post(f"{API}/v1/probe", json={"task_id": TASK, "agent_id": AGENT, "message": "phase-1"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["echo"] == "phase-1"
    trace_id = body["trace_id"]
    deadline, spans = time.time() + 30, []
    while time.time() < deadline:
        spans = _spans_for(trace_id)
        if {"api", "orchestrator", "echo-probe"} <= {s["service"] for s in spans}:
            break
        time.sleep(1)
    services = {s["service"] for s in spans}
    assert {"api", "orchestrator", "echo-probe"} <= services, f"spans seen: {spans}"
    for svc in ("api", "orchestrator", "echo-probe"):
        tagged = [s for s in spans if s["service"] == svc and {"task_id", "agent_id", "tool", "risk_class"} <= set(s["attrs"])]
        assert tagged, f"{svc} span lacks the four standard attributes: {spans}"
        assert tagged[0]["attrs"]["task_id"] == TASK and tagged[0]["attrs"]["agent_id"] == AGENT
    assert psql(f"SELECT count(*) FROM tool_calls WHERE task_id='{TASK}' AND trace_id='{trace_id}'") == "1"


def pinned_headers() -> dict:
    """What the sandbox supervisor's forwarder adds (Phase 2 identity pinning): an open session
    for the probe agent and an HMAC stamp. Unsigned requests are denied."""
    import sys
    sys.path.insert(0, str(ROOT / "packages" / "pycommon"))
    from revenueos_common import egress_identity
    session = psql(f"INSERT INTO egress_sessions(agent_id, task_id, socket_path) "
                   f"VALUES ('{AGENT}', '{TASK}', 'e2e-{uuid.uuid4().hex}') RETURNING id").splitlines()[0]
    key = (SECRETS / "keychain" / "egress-identity-hmac").read_text().strip()
    return egress_identity.sign(key, session, AGENT, TASK)


def test_envoy_denies_unlisted_host_and_logs_it():
    marker = uuid.uuid4().hex[:8]
    r = requests.get(f"http://denied-{marker}.example/steal", proxies={"http": ENVOY},
                     headers=pinned_headers(), timeout=15)
    assert r.status_code == 403
    assert "not allowlisted" in r.json()["reason"]
    assert psql(f"SELECT count(*) FROM audit_log WHERE action='egress.deny' AND target LIKE 'denied-{marker}%'") == "1"


def test_envoy_injects_secret_the_agent_never_sees():
    secret = (SECRETS / "keychain" / "upstream-echo-token").read_text().strip()
    r = requests.get("http://upstream-echo:8080/ok", proxies={"http": ENVOY},
                     headers=pinned_headers(), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorization_present"] is True
    assert body["authorization_sha256"] == hashlib.sha256(f"Bearer {secret}".encode()).hexdigest()
    assert body["agent_header_leaked"] is False
    assert secret not in r.text and secret not in json.dumps(dict(r.headers))
    logged = psql("SELECT payload::text FROM audit_log WHERE action='egress.allow' ORDER BY seq DESC LIMIT 1")
    assert '"injected_secrets": 1' in logged and secret not in logged


def test_unidentified_agent_is_denied_by_envoy():
    r = requests.get("http://upstream-echo:8080/ok", proxies={"http": ENVOY}, timeout=15)
    assert r.status_code == 403


def test_self_declared_agent_without_a_signed_stamp_is_denied():
    r = requests.get("http://upstream-echo:8080/ok", proxies={"http": ENVOY},
                     headers={"x-revenueos-agent": AGENT, "x-revenueos-task": TASK}, timeout=15)
    assert r.status_code == 403 and "not identity-pinned" in r.json()["reason"]


def test_audit_chain_intact_after_the_run():
    assert psql("SELECT audit_verify() IS NULL") == "t"
