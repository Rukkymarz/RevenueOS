"""OmniClient and the delegated omni.* tool specs, with the HTTP layer stubbed."""
import io
import json

import pytest

from revenueos_runtime_os.nava import CallContext, ToolError, Workspaces
from revenueos_runtime_os.tools import OmniClient, omni_tools


class FakeHTTP:
    def __init__(self, responses):
        self.responses, self.requests = responses, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        body = json.dumps(self.responses[len(self.requests) - 1]).encode()
        return io.BytesIO(body)


@pytest.fixture
def ctx(tmp_path):
    return CallContext("5e000000-0000-4000-8000-000000000001", "agent-1", "task-1", "auto", "appr-1",
                       Workspaces(tmp_path / "w", tmp_path / "s"))


def test_client_and_delegated_specs(monkeypatch, ctx):
    fake = FakeHTTP([
        {"tools": [{"name": "screen.capture", "base_risk": "medium", "parameters":
                    {"type": "object", "properties": {"region": {"type": "string"}}, "required": []}}]},
        {"status": "ok", "output": "captured", "receipt_id": "r-1"},
        {"status": "blocked", "error": "critical"},
    ])
    monkeypatch.setattr("urllib.request.urlopen", fake)
    client = OmniClient("http://runtime-omni:8102/", "tok")
    tools = omni_tools(client)
    assert set(tools) == {"omni.screen.capture"} and tools["omni.screen.capture"].delegated
    assert tools["omni.screen.capture"].risk == "medium"
    assert tools["omni.screen.capture"].resources({}, ctx) == ["desktop"]

    out = tools["omni.screen.capture"].handler(ctx, {"region": "full"})
    assert out["receipt_id"] == "r-1"
    req = fake.requests[-1]
    assert req.get_header("Authorization") == "Bearer tok"
    assert req.get_header("X-nava-syscall") == ctx.syscall_id        # ties the call to this syscall
    sent = json.loads(req.data)
    assert sent["agent_id"] == "agent-1" and sent["task_id"] == "task-1" and sent["approval_id"] == "appr-1"

    with pytest.raises(ToolError):
        tools["omni.screen.capture"].handler(ctx, {})                # blocked upstream -> ToolError
