"""`browser.call` (C02 playwright-mcp, docs/PINS.md): a thin, generic passthrough to the real
playwright-mcp server's own MCP tools. `_call_playwright_mcp` itself needs `fastmcp` and a real
(or in-process) MCP server to prove end-to-end -- `fastmcp` isn't installable in this sandboxed
dev environment (no pip network access), the same pre-existing gap documented across
tests/unit/test_runtime_omni.py and friends; CI installs it. What's tested here, without
fastmcp, is the actual integration point: the ToolSpec's schema shape, and `browser_call`'s own
plumbing (env var default, args unwrapping, exception -> ToolError translation) via a
monkeypatched `_call_playwright_mcp`."""
import pytest

from revenueos_runtime_os.nava import CallContext, ToolError, Workspaces
from revenueos_runtime_os.tools import browser_call, builtin_tools


def _ctx(ws):
    return CallContext("sc", "agent1", "task1", "auto", None, ws)


def test_browser_call_toolspec_schema():
    spec = builtin_tools()["browser.call"]
    assert spec.schema["required"] == ["tool", "args"]
    assert spec.schema["additionalProperties"] is False
    assert set(spec.schema["properties"]) == {"tool", "args", "timeout_s"}
    assert spec.risk == "medium" and spec.mutating is False


def test_browser_call_resource_is_a_shared_browser_lock(tmp_path):
    spec = builtin_tools()["browser.call"]
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    ctx = _ctx(ws)
    assert spec.resources({"tool": "browser_navigate", "args": {}}, ctx) == ["browser"]


def test_browser_call_reads_tool_and_args_and_uses_default_url(tmp_path, monkeypatch):
    seen = {}

    def fake_run(coro):
        seen["awaited"] = True
        return {"ok": True}

    captured = {}

    async def fake_call(tool, args, url, timeout_s=30.0):
        captured.update(tool=tool, args=args, url=url, timeout_s=timeout_s)
        return {"ok": True}

    monkeypatch.delenv("PLAYWRIGHT_MCP_URL", raising=False)
    monkeypatch.setattr("revenueos_runtime_os.tools._call_playwright_mcp", fake_call)
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    out = browser_call(_ctx(ws), {"tool": "browser_navigate", "args": {"url": "https://example.com"}})
    assert out == {"ok": True}
    assert captured["tool"] == "browser_navigate"
    assert captured["args"] == {"url": "https://example.com"}
    assert captured["url"] == "http://playwright-mcp:8931"   # default, no env var set
    assert captured["timeout_s"] == 60


def test_browser_call_honors_playwright_mcp_url_env_and_timeout(tmp_path, monkeypatch):
    captured = {}

    async def fake_call(tool, args, url, timeout_s=30.0):
        captured.update(url=url, timeout_s=timeout_s)
        return {}

    monkeypatch.setenv("PLAYWRIGHT_MCP_URL", "http://custom-host:9999")
    monkeypatch.setattr("revenueos_runtime_os.tools._call_playwright_mcp", fake_call)
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    browser_call(_ctx(ws), {"tool": "browser_snapshot", "args": {}, "timeout_s": 5})
    assert captured["url"] == "http://custom-host:9999"
    assert captured["timeout_s"] == 5


def test_browser_call_defaults_args_to_empty_object(tmp_path, monkeypatch):
    captured = {}

    async def fake_call(tool, args, url, timeout_s=30.0):
        captured["args"] = args
        return {}

    monkeypatch.setattr("revenueos_runtime_os.tools._call_playwright_mcp", fake_call)
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    browser_call(_ctx(ws), {"tool": "browser_snapshot", "args": {}})
    assert captured["args"] == {}


def test_browser_call_wraps_failures_as_tool_error(tmp_path, monkeypatch):
    async def fake_call(tool, args, url, timeout_s=30.0):
        raise ConnectionError("playwright-mcp unreachable")

    monkeypatch.setattr("revenueos_runtime_os.tools._call_playwright_mcp", fake_call)
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    with pytest.raises(ToolError, match="playwright-mcp call failed"):
        browser_call(_ctx(ws), {"tool": "browser_navigate", "args": {"url": "https://example.com"}})
