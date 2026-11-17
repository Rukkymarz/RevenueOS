"""The NAVA MCP facades end to end through FastMCP with the gateway HTTP faked: every tool
forwards to runtime-os as the calling agent, with that agent's own token, and writes its receipt."""
import asyncio
import io
import json

import pytest

pytest.importorskip("fastmcp")
pytest.importorskip("revenueos_contracts.models")
from fastmcp import Client  # noqa: E402

import revenueos_mcp_nava.suite as suite  # noqa: E402
from revenueos_common.secrets import KeychainStore, SecretResolver  # noqa: E402


@pytest.fixture
def wired(nava, pgdb, tmp_path, monkeypatch):
    kc = KeychainStore(tmp_path / "kc")
    kc.put(f"nava-agent-{nava.agent}", "nava_agent_token")
    secrets = SecretResolver(kc)
    sent = []

    def fake_urlopen(req, timeout=None):
        body = json.loads(req.data) if req.data else None
        sent.append({"url": req.full_url, "method": req.get_method(), "auth": req.get_header("Authorization"),
                     "body": body})
        if req.full_url.endswith("/v1/syscalls"):
            out = ({"status": "denied", "reason": "blocked: rm -rf", "step": "policy", "risk_class": "critical"}
                   if body["args"].get("argv") == ["rm", "-rf", "/"] else
                   {"status": "committed", "id": "sc-1", "receipt_id": "r-1", "output": {"ok": True}})
        else:
            out = {"ok": True, "seq": 7, "id": "x", "items": [], "messages": [], "status": "running"}
        return io.BytesIO(json.dumps(out).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    def call(domain, tool, args, agent=None):
        srv = suite.build(domain, db=pgdb, secrets=secrets, token_ref=f"keychain://mcp-nava-{domain}-token")

        async def go():
            async with Client(srv.mcp) as c:
                return await c.call_tool(tool, {"task_id": nava.task, "agent_id": agent or nava.agent, "args": args})
        return asyncio.run(go()).structured_content["result"]

    return nava, sent, call


def test_file_tool_forwards_as_the_agent_and_is_receipted(wired):
    nava, sent, call = wired
    out = call("files", "write", {"args": {"workspace": "w", "path": "a", "content": "b"}})
    assert out == {"status": "committed", "output": {"ok": True}, "receipt_id": "r-1", "syscall_id": "sc-1"}
    assert sent[-1]["url"].endswith("/v1/syscalls") and sent[-1]["auth"] == "Bearer nava_agent_token"
    assert sent[-1]["body"]["tool"] == "fs.write" and sent[-1]["body"]["task_id"] == nava.task
    assert nava.db.one("SELECT count(*) FROM tool_calls WHERE mcp_server='nava-files' AND tool='write'") == "1"


def test_gateway_verdicts_surface_verbatim(wired):
    nava, sent, call = wired
    out = call("terminal", "run", {"args": {"workspace": "w", "argv": ["rm", "-rf", "/"]}})
    assert out["status"] == "denied" and out["risk_class"] == "critical" and out["step"] == "policy"


def test_agent_without_a_token_fails_closed(wired):
    nava, sent, call = wired
    before = len(sent)
    with pytest.raises(Exception, match="no NAVA token"):
        call("files", "list", {"args": {"workspace": "w"}}, agent=nava.other)
    assert len(sent) == before                       # nothing reached the gateway


def test_memory_bus_and_plans_facades(wired):
    nava, sent, call = wired
    call("memory", "remember", {"tier": "episodic", "key": "k", "value": {"v": 1}})
    assert sent[-1]["url"].endswith("/v1/memory") and sent[-1]["method"] == "POST"
    call("memory", "recall", {"tier": "episodic", "key": "k"})
    assert "/v1/memory?tier=episodic&key=k" in sent[-1]["url"] and sent[-1]["method"] == "GET"
    call("bus", "send", {"to": nava.other, "channel": "jobs", "body": {"n": 1}})
    assert sent[-1]["url"].endswith("/v1/bus/send")
    call("bus", "inbox", {"after": 3})
    assert sent[-1]["url"].endswith("/v1/bus/inbox?after=3")
    call("plans", "create", {"task_id": nava.task, "objective": "o", "steps": [{"tool": "fs.list", "args": {}}]})
    assert sent[-1]["url"].endswith("/v1/plans")
    for action in ("run", "pause", "resume", "retry"):
        call("plans", action, {"plan_id": "p-1", "mode": "auto"})
        assert sent[-1]["url"].endswith(f"/v1/plans/p-1/{action}")
    call("plans", "status", {"plan_id": "p-1"})
    assert sent[-1]["url"].endswith("/v1/plans/p-1") and sent[-1]["method"] == "GET"


def test_http_errors_become_verdicts(wired, monkeypatch):
    import urllib.error
    nava, sent, call = wired

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 502, "bad gateway", {}, io.BytesIO(b"not json"))

    monkeypatch.setattr("urllib.request.urlopen", boom)
    out = call("files", "list", {"args": {"workspace": "w"}})
    assert out["status"] == "failed" and "502" in out["reason"]


def test_all_fifteen_mount_in_one_app(tmp_path):
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient
    app = suite.build_all(secrets=SecretResolver(KeychainStore(tmp_path / "kc")))
    with TestClient(app) as c:
        body = c.get("/health").json()
    assert body["count"] == 15 and set(body["servers"]) == set(suite.DOMAINS)
