"""INV-07: the model is never the security boundary; unauthorized tools are hidden at the
execution layer and restricted-tool decisions are audited.

The tool gateway lands in Phase 4 (agent-discover) and Phase 13 (Hubzoid/Harnis). The
attack is a strict expected failure until then."""
import pytest

PHASE = "control lands in Phase 4 (gateway tool filtering)"


@pytest.mark.xfail(strict=True, raises=ImportError, reason=PHASE)
def test_prompted_call_to_hidden_tool_is_refused_and_audited():
    from revenueos_discovery.gateway import ToolGateway, ToolNotAuthorized
    gw = ToolGateway(agent_allowlist={"agent-a": ["scraper.fetch"]})
    assert "outreach.send" not in gw.list_tools("agent-a")
    with pytest.raises(ToolNotAuthorized):
        gw.call("agent-a", "outreach.send", {"to": "victim@example.com"})
    assert gw.audit_events[-1]["action"] == "tool.denied"


def test_mcp_common_refuses_tool_names_outside_the_protocol_charset():
    """Execution-layer naming rule exists today: a tool name cannot smuggle path or
    namespace characters to impersonate another server's tool."""
    server = pytest.importorskip("revenueos_mcp_common.server")
    for hostile in ("outreach.send/../admin", "probe echo", "a" * 65, "tool;rm -rf /", ""):
        assert server.TOOL_NAME.match(hostile) is None, hostile
    assert server.TOOL_NAME.match("probe_echo")
