"""The 15 NAVA MCP servers (spec 3.3): exactly fifteen, each a narrow facade whose every tool
forwards to the gateway. Needs fastmcp (installed in CI; skipped on a bare workstation)."""
import pytest

fastmcp = pytest.importorskip("fastmcp")

from revenueos_mcp_nava import DOMAINS, build  # noqa: E402

EXPECTED = {"files", "terminal", "python", "processes", "system", "screen", "gui", "clipboard",
            "apps", "notify", "web", "browser", "memory", "bus", "plans"}


def test_exactly_fifteen_domains():
    assert set(DOMAINS) == EXPECTED and len(DOMAINS) == 15


@pytest.mark.parametrize("domain", sorted(EXPECTED))
def test_each_server_builds_with_its_tools(domain, monkeypatch, tmp_path):
    from revenueos_common.secrets import KeychainStore, SecretResolver
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    srv = build(domain, secrets=SecretResolver(KeychainStore(tmp_path / "kc")))
    assert srv.name == f"nava-{domain}" and srv.tools, domain
    # the facade never raises its own risk: NAVA is the single enforcement point (spec 3.2)
    assert set(srv.tools.values()) == {"low"}
    if domain == "memory":
        assert {"remember", "recall"} <= set(srv.tools)
    if domain == "bus":
        assert {"send", "inbox"} <= set(srv.tools)
    if domain == "plans":
        assert {"create", "run", "pause", "resume", "retry", "status"} <= set(srv.tools)
    if domain == "terminal":
        assert set(srv.tools) == {"run"}


def test_unknown_domain_refused():
    with pytest.raises(KeyError):
        build("root")


def test_terminal_cap_is_30s_and_calls_are_receipted(nava, pgdb, tmp_path, monkeypatch):
    """The OpenMuse isolated terminal clamps every command to 30 s before it reaches the gateway,
    through the full mcp-common path (envelope, span, receipt) against the real database."""
    pytest.importorskip("revenueos_contracts.models")
    import asyncio

    import revenueos_mcp_nava.suite as suite
    from revenueos_common.secrets import KeychainStore, SecretResolver
    sent = {}

    def fake_syscall(secrets, ctx, tool, payload, approval_id=None):
        sent["tool"], sent["payload"], sent["agent"] = tool, payload, ctx["agent_id"]
        return {"status": "committed", "output": {"exit_code": 0}}

    monkeypatch.setattr(suite, "_syscall", fake_syscall)
    kc = KeychainStore(tmp_path / "kc")
    kc.put("mcp-nava-terminal-token", "tok-1")
    srv = suite.build("terminal", db=pgdb, secrets=SecretResolver(kc),
                      token_ref="keychain://mcp-nava-terminal-token")
    from fastmcp import Client

    async def go():
        async with Client(srv.mcp) as c:
            return await c.call_tool("run", {"task_id": nava.task, "agent_id": nava.agent,
                                             "args": {"args": {"workspace": "w", "argv": ["sleep", "500"],
                                                               "timeout_s": 500}}})
    out = asyncio.run(go())
    assert out.structured_content["result"]["status"] == "committed"
    assert sent["tool"] == "sandbox.run" and sent["agent"] == nava.agent
    assert sent["payload"]["args"]["timeout_s"] == 30
    # the facade call wrote its own receipt on top of the gateway's
    assert nava.db.one("SELECT count(*) FROM tool_calls WHERE mcp_server='nava-terminal' AND tool='run'") == "1"
