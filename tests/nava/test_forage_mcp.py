"""Forage as an MCP server (spec 4.1): its four tools forward to the governed Forage syscalls
as the calling agent, so the gateway (INV-10, policy, receipts) stays the only place decisions are made."""
import asyncio
import io
import json

import pytest

pytest.importorskip("fastmcp")
pytest.importorskip("revenueos_contracts.models")
from fastmcp import Client  # noqa: E402

import revenueos_mcp_forage.server as forage_server  # noqa: E402
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

    def call(tool, args, agent=None):
        srv = forage_server.build(db=pgdb, secrets=secrets, token_ref="keychain://mcp-forage-token")

        async def go():
            async with Client(srv.mcp) as c:
                return await c.call_tool(tool, {"task_id": nava.task, "agent_id": agent or nava.agent, "args": args})
        return asyncio.run(go()).structured_content["result"]

    return nava, sent, call


import pytest as _pytest


@_pytest.mark.parametrize("tool,syscall", [("forage_search", "forage.search"), ("forage_install", "forage.install"),
                                           ("forage_learn", "forage.learn"), ("call", "mcp.call")])
def test_each_tool_forwards_to_its_syscall_as_the_agent(wired, tool, syscall):
    nava, sent, call = wired
    out = call(tool, {"args": {"query": "github"}})
    assert out["status"] == "committed" and out["receipt_id"] == "r-1"
    assert sent[-1]["body"]["tool"] == syscall and sent[-1]["body"]["task_id"] == nava.task
    assert sent[-1]["auth"] == "Bearer nava_agent_token"
