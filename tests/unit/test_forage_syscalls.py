"""The Forage syscalls on the NAVA tool side (spec 4.1): they call the discovery service, and
`forage.learn` writes a marked, replaceable block into the agent rule file."""
import io
import json
import urllib.error

import pytest

from revenueos_runtime_os import tools
from revenueos_runtime_os.nava import CallContext, Workspaces


@pytest.fixture
def ctx(tmp_path):
    return CallContext("sc", "agent1", "task1", "auto", None, Workspaces(tmp_path / "ws", tmp_path / "snaps"))


def fake_discovery(monkeypatch, answers):
    seen = []

    def _d(path, body, timeout=180):
        seen.append((path, body))
        a = answers[path]
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(tools, "_discovery", _d)
    return seen


def test_specs_are_registered_with_the_expected_risk():
    t = tools.builtin_tools()
    assert {"forage.search", "forage.install", "forage.learn", "mcp.call"} <= set(t)
    assert t["forage.install"].risk == "medium" and t["mcp.call"].risk == "medium" and t["forage.learn"].mutating


def test_search_and_mcp_call_forward_with_the_callers_identity(ctx, monkeypatch):
    seen = fake_discovery(monkeypatch, {"/v1/forage/search": {"candidates": []}, "/v1/call": {"result": {"echo": "hi"}}})
    assert tools.forage_search(ctx, {"query": "github", "limit": 3}) == {"candidates": []}
    assert tools.mcp_call(ctx, {"server": "echo", "tool": "echo", "arguments": {"message": "hi"}}) == {"echo": "hi"}
    assert seen[1][1]["task_id"] == "task1" and seen[1][1]["agent_id"] == "agent1" and seen[0][1]["limit"] == 3


def test_a_denied_install_is_a_tool_error_with_the_reasons(ctx, monkeypatch):
    fake_discovery(monkeypatch, {"/v1/forage/install": {"status": "denied", "reasons": ["no license", "stale"]}})
    with pytest.raises(tools.ToolError, match="no license; stale"):
        tools.forage_install(ctx, {"spec": {"name": "x"}})
    fake_discovery(monkeypatch, {"/v1/forage/install": {"status": "installed", "server": "x"}})
    assert tools.forage_install(ctx, {"spec": {"name": "x"}})["server"] == "x"


def test_learn_writes_one_block_per_server_and_replaces_it_in_place(ctx, monkeypatch, tmp_path):
    def answer(server, text):
        return {"marker": f"<!-- forage:{server} -->", "instructions": text}
    fake_discovery(monkeypatch, {"/v1/forage/learn": answer("echo", "v1\n")})
    out = tools.forage_learn(ctx, {"server": "echo"})
    f = ctx.workspaces.path("agent1", "rules") / "AGENTS.md"
    assert out["rule_file"] == "rules/AGENTS.md" and "v1" in f.read_text()
    fake_discovery(monkeypatch, {"/v1/forage/learn": answer("other", "o1\n")})
    tools.forage_learn(ctx, {"server": "other"})
    fake_discovery(monkeypatch, {"/v1/forage/learn": answer("echo", "v2\n")})
    tools.forage_learn(ctx, {"server": "echo"})
    text = f.read_text()
    assert "v2" in text and "v1" not in text and "o1" in text and text.count("<!-- forage:echo -->") == 1


def test_discovery_http_errors_become_tool_errors(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO(json.dumps({"reason": "INV-10: experimental"}).encode()))
    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(tools.ToolError, match="INV-10"):
        tools._discovery("/v1/call", {})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: (_ for _ in ()).throw(OSError("refused")))
    with pytest.raises(tools.ToolError, match="unreachable"):
        tools._discovery("/v1/call", {})
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: io.BytesIO(b'{"ok": true}'))
    assert tools._discovery("/v1/x", {}) == {"ok": True}
