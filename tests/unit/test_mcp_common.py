"""packages/mcp-common: rate limiting, backoff, and the full tool-call path (contract validation,
auth, OTel span, approval consumption, receipt) against a real Postgres. Needs fastmcp,
OpenTelemetry and the generated contract models (installed in CI)."""
import asyncio

import pytest

pytest.importorskip("fastmcp")
pytest.importorskip("revenueos_contracts.models")

from fastmcp import Client  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402
from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from dbkit import HOST, PORT, USER  # noqa: E402
from revenueos_common.canonical import args_hash  # noqa: E402
from revenueos_common.db import Database  # noqa: E402
from revenueos_common.secrets import KeychainStore, SecretResolver  # noqa: E402
from revenueos_mcp_common import RateLimited, TokenBucket, create_server, retry_with_backoff  # noqa: E402
from revenueos_mcp_common.telemetry import setup_tracing  # noqa: E402

EXPORTER = InMemorySpanExporter()
setup_tracing("unit-tests")
trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(EXPORTER))


# ---------------------------------------------------------------- rate limiting and backoff
def test_token_bucket_limits_per_key_and_refills():
    now = [0.0]
    b = TokenBucket(rate_per_s=1, burst=2, clock=lambda: now[0])
    b.take("a"); b.take("a")
    with pytest.raises(RateLimited) as e:
        b.take("a")
    assert e.value.retry_after == pytest.approx(1.0)
    b.take("b")  # other callers are unaffected
    now[0] = 1.0
    b.take("a")


def test_backoff_retries_transient_errors_then_gives_up():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("blip")
        return "ok"
    assert retry_with_backoff(flaky, sleep=sleeps.append, rng=lambda: 1.0) == "ok"
    assert sleeps == [0.2, 0.4]
    with pytest.raises(ConnectionError):
        retry_with_backoff(lambda: (_ for _ in ()).throw(ConnectionError()), retries=2, sleep=lambda _: None)


def test_non_retryable_errors_are_not_retried():
    calls = []

    def bad():
        calls.append(1)
        raise ValueError("bug")
    with pytest.raises(ValueError):
        retry_with_backoff(bad, sleep=lambda _: None)
    assert len(calls) == 1


# ---------------------------------------------------------------- the tool-call path
class Msg(BaseModel):
    message: str = Field(max_length=20)


@pytest.fixture
def server(db, world, tmp_path):
    kc = KeychainStore(tmp_path / "kc")
    kc.put("mcp-unit-token", "tok-123")
    pg = Database(dbname=db.name, host=HOST, port=PORT, user=USER, actor="mcp:unit")
    s = create_server("unit", db=pg, secrets=SecretResolver(kc), token_ref="keychain://mcp-unit-token")

    @s.tool("echo", risk_class="low", args_model=Msg)
    def echo(args):
        return {"echo": args["message"]}

    @s.tool("send_mail", risk_class="high", args_model=Msg)
    def send(args):
        return {"sent": args["message"]}

    return s


def call(server, tool, **envelope):
    async def go():
        async with Client(server.mcp) as c:
            return await c.call_tool(tool, envelope)
    return asyncio.run(go())


def test_low_risk_call_returns_result_writes_receipt_and_span(server, db, world):
    EXPORTER.clear()
    res = call(server, "echo", task_id=world["task"], agent_id=world["exec"], args={"message": "hi"})
    assert res.structured_content["result"] == {"echo": "hi"}
    row = db.one(f"SELECT tool || '|' || verdict || '|' || args_hash FROM tool_calls WHERE task_id='{world['task']}'")
    assert row == f"echo|ok|{args_hash({'message': 'hi'})}"
    span = [s for s in EXPORTER.get_finished_spans() if s.name == "mcp.tool/echo"][-1]
    assert {k: span.attributes[k] for k in ("task_id", "agent_id", "tool", "risk_class")} == \
        {"task_id": world["task"], "agent_id": world["exec"], "tool": "echo", "risk_class": "low"}


def test_invalid_arguments_rejected_at_the_boundary_with_a_receipt(server, db, world):
    with pytest.raises(ToolError):
        call(server, "echo", task_id=world["task"], agent_id=world["exec"], args={"message": "x" * 50})
    assert db.one("SELECT verdict FROM tool_calls ORDER BY created_at DESC LIMIT 1") == "rejected:validation"


def test_envelope_violating_the_contract_is_rejected(server, world):
    with pytest.raises(ToolError):
        call(server, "echo", task_id="not-a-uuid", agent_id=world["exec"], args={"message": "hi"})


def test_high_risk_call_without_approval_is_denied_and_audited(server, db, world):
    with pytest.raises(ToolError):
        call(server, "send_mail", task_id=world["task"], agent_id=world["exec"], args={"message": "hi"})
    assert db.one("SELECT count(*) FROM tool_calls WHERE tool='send_mail'") == "0"
    assert db.one("SELECT count(*) FROM audit_log WHERE action='tool.denied'") == "1"


def test_high_risk_call_with_hash_bound_approval_runs_once(server, db, world):
    args = {"message": "hi"}
    a = db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
               f"VALUES ('{world['task']}','{args_hash(args)}','agent','owner',now()+interval '5 minutes','approved') RETURNING id")
    res = call(server, "send_mail", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)
    assert res.structured_content["result"] == {"sent": "hi"}
    assert db.one(f"SELECT approval_id FROM tool_calls WHERE tool='send_mail'") == a
    with pytest.raises(ToolError):  # single use
        call(server, "send_mail", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)


def test_approval_for_different_arguments_is_refused(server, db, world):
    a = db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
               f"VALUES ('{world['task']}','{args_hash({'message': 'hi'})}','agent','owner',now()+interval '5 minutes','approved') RETURNING id")
    with pytest.raises(ToolError):
        call(server, "send_mail", task_id=world["task"], agent_id=world["exec"], args={"message": "HI"}, approval_id=a)


def test_http_transport_requires_the_bearer_token(server):
    with TestClient(server.http_app()) as c:
        assert c.get("/health").status_code == 200
        assert c.post("/mcp", json={}).status_code == 401
        assert c.post("/mcp", json={}, headers={"authorization": "Bearer wrong"}).status_code == 401


def test_tool_names_outside_the_protocol_charset_are_refused(server):
    with pytest.raises(ValueError):
        server.tool("bad.name", risk_class="low")(lambda a: a)
    with pytest.raises(ValueError):
        server.tool("ok", risk_class="extreme")(lambda a: a)


# ---------------------------------------------------------------- echo-probe server and orchestrator probe
@pytest.fixture
def echo_probe(db, world, tmp_path, monkeypatch):
    for k, v in {"PGHOST": HOST, "PGPORT": PORT, "PGUSER": USER, "PGDATABASE": db.name,
                 "REVENUEOS_KEYCHAIN_DIR": str(tmp_path / "kc")}.items():
        monkeypatch.setenv(k, v)
    KeychainStore(tmp_path / "kc").put("mcp-echo-probe-token", "probe-token")
    import importlib
    import sys
    sys.modules.pop("revenueos_mcp_echo_probe.server", None)
    return importlib.import_module("revenueos_mcp_echo_probe.server")


def test_echo_probe_tools_run_through_mcp_common(echo_probe, db, world):
    res = call(echo_probe.server, "probe_echo", task_id=world["task"], agent_id=world["exec"], args={"message": "ping"})
    assert res.structured_content["result"] == {"echo": "ping"}
    with pytest.raises(ToolError):
        call(echo_probe.server, "probe_guarded", task_id=world["task"], agent_id=world["exec"], args={"message": "x"})
    args = {"message": "go"}
    a = db.one("INSERT INTO approvals(task_id, tool_call_args_hash, requested_by, approved_by, expires_at, status) "
               f"VALUES ('{world['task']}','{args_hash(args)}','agent','owner',now()+interval '5 minutes','approved') RETURNING id")
    res = call(echo_probe.server, "probe_guarded", task_id=world["task"], agent_id=world["exec"], args=args, approval_id=a)
    assert res.structured_content["result"] == {"echo": "go", "guarded": True}


def test_orchestrator_probe_rejects_contract_violations_and_missing_token(tmp_path, monkeypatch):
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "empty"))
    from revenueos_orchestrator.app import app
    c = TestClient(app)
    assert c.post("/v1/probe", json={"task_id": "nope", "agent_id": "x", "message": "hi"}).status_code == 400
    ok = {"task_id": "7a1c2e30-0002-4000-8000-000000000001", "agent_id": "7a1c2e30-0001-4000-8000-000000000001", "message": "hi"}
    r = c.post("/v1/probe", json=ok)
    assert r.status_code == 503 and "token" in r.json()["error"]


def test_mcp_common_package_health():
    from revenueos_mcp_common.health import health
    assert health()["status"] == "ok"
