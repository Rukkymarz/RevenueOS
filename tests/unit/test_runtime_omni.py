"""runtime-omni (spec 3.1, 3.6): OmniPilot's 41 tools by remote control, each call classified
by the shared risk library, receipted, and run with pinned egress."""
import os
from contextlib import contextmanager

import pytest

from revenueos_runtime_omni.runtime import Runtime, build_registry

TASK, AGENT = "7a1c2e30-0002-4000-8000-000000000001", "7a1c2e30-0001-4000-8000-000000000001"


class FakeReceipts:
    def __init__(self, approve=False):
        self.written, self.denied, self.approve = [], [], approve

    def write(self, **kw):
        self.written.append(kw)
        return f"receipt-{len(self.written)}"

    def deny(self, **kw):
        self.denied.append(kw)

    def consume_approval(self, approval_id, args, risk_class, task_id=None, tool=None):
        if not (self.approve and approval_id):
            raise PermissionError("high tool call requires a hash-bound approval")
        return approval_id


@pytest.fixture(scope="module")
def registry():
    return build_registry()


@pytest.fixture
def rt(registry, tmp_path):
    return Runtime(FakeReceipts(), workdir=str(tmp_path), registry=registry)


def test_exposes_exactly_omnipilots_41_tools(rt):
    names = [t["name"] for t in rt.tools()]
    assert len(names) == 41 and "plugin.broken" not in names
    for prefix in ("shell.", "python.", "fs.", "apps.", "screen.", "gui.", "clipboard.", "processes.", "notify.", "web."):
        assert any(n.startswith(prefix) for n in names), prefix


def test_low_risk_call_runs_and_is_receipted(rt, tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    res = rt.invoke("fs.read_file", {"path": str(tmp_path / "a.txt")}, task_id=TASK, agent_id=AGENT)
    assert res.status == "ok" and "hello" in res.output and res.receipt_id == "receipt-1"
    w = rt.receipts.written[0]
    assert (w["tool"], w["server"], w["verdict"], w["risk_class"]) == ("fs.read_file", "runtime-omni", "ok", "low")


def test_persistent_python_keeps_state_between_calls(rt):
    rt.invoke("python.run_python", {"code": "counter = 41"}, task_id=TASK, agent_id=AGENT)
    res = rt.invoke("python.run_python", {"code": "print(counter + 1)"}, task_id=TASK, agent_id=AGENT)
    assert res.status == "ok" and "42" in res.output


@pytest.mark.parametrize("mode", ["ask", "auto", "yolo"])
def test_rm_rf_root_is_blocked_in_every_mode_and_never_runs(rt, mode, tmp_path):
    canary = tmp_path / "canary"
    canary.write_text("x")
    res = rt.invoke("shell.run_command", {"command": f"rm -rf / ; rm {canary}"}, task_id=TASK, agent_id=AGENT, mode=mode)
    assert res.status == "blocked" and res.risk_class == "critical"
    assert canary.exists() and rt.receipts.written == []
    assert "critical" in rt.receipts.denied[0]["reason"]


def test_high_risk_needs_an_approval_then_runs(registry, tmp_path):
    rt = Runtime(FakeReceipts(approve=True), workdir=str(tmp_path), registry=registry)
    args = {"path": "/etc/hostname-copy"}
    refused = rt.invoke("fs.delete_file", args, task_id=TASK, agent_id=AGENT, mode="yolo")
    assert refused.status == "approval_required" and refused.risk_class == "high"
    ran = rt.invoke("fs.delete_file", args, task_id=TASK, agent_id=AGENT, approval_id="ap-1", mode="yolo")
    assert ran.status in ("ok", "error") and rt.receipts.written[-1]["approval_id"] == "ap-1"


def test_shell_runs_in_the_workdir(rt, tmp_path):
    res = rt.invoke("shell.run_command", {"command": "pwd"}, task_id=TASK, agent_id=AGENT)
    assert res.status == "ok" and str(tmp_path) in res.output


def test_web_traffic_uses_the_pinned_proxy_only_during_the_call(registry, tmp_path):
    seen = {}

    @contextmanager
    def egress(agent, task):
        seen["session"] = (agent, task)
        yield ("http://127.0.0.1:9", str(tmp_path / "ca.pem"))
    rt = Runtime(FakeReceipts(), workdir=str(tmp_path), registry=registry, egress=egress)
    before = os.environ.get("HTTPS_PROXY")
    res = rt.invoke("python.run_python", {"code": "import os; print(os.environ['HTTPS_PROXY'], os.environ['SSL_CERT_FILE'])"},
                    task_id=TASK, agent_id=AGENT)
    assert "http://127.0.0.1:9" in res.output and "ca.pem" in res.output
    assert seen["session"] == (AGENT, TASK) and os.environ.get("HTTPS_PROXY") == before


def test_unknown_tool_and_crashing_tool(rt, monkeypatch):
    with pytest.raises(KeyError):
        rt.invoke("nope.tool", {}, task_id=TASK, agent_id=AGENT)
    tool = rt.registry.get("system.get_system_info")
    monkeypatch.setattr(tool, "execute", lambda ctx, args: (_ for _ in ()).throw(RuntimeError("boom")))
    res = rt.invoke("system.get_system_info", {}, task_id=TASK, agent_id=AGENT)
    assert res.status == "error" and "boom" in res.output and rt.receipts.written[-1]["verdict"] == "error"


# --------------------------------------------------------------------------- HTTP surface
@pytest.fixture
def api(registry, tmp_path, monkeypatch):
    import importlib

    from starlette.testclient import TestClient

    from revenueos_common.secrets import KeychainStore
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "kc"))
    KeychainStore(tmp_path / "kc").put("runtime-omni-token", "rt-token-123")
    mod = importlib.import_module("revenueos_runtime_omni.app")
    rt = Runtime(FakeReceipts(), workdir=str(tmp_path), registry=registry)
    monkeypatch.setattr(mod, "runtime", lambda: rt)
    return mod, TestClient(mod.app), rt


def post(c, tool, body, token="rt-token-123"):
    return c.post(f"/v1/tools/{tool}/invoke", json=body, headers={"authorization": f"Bearer {token}"} if token else {})


def test_api_requires_the_runtime_token(api):
    _, c, _ = api
    body = {"task_id": TASK, "agent_id": AGENT, "args": {}}
    assert post(c, "system.get_system_info", body, token=None).status_code == 401
    assert post(c, "system.get_system_info", body, token="wrong").status_code == 401


def test_api_validates_and_maps_statuses(api, tmp_path):
    pytest.importorskip("fastmcp")   # the invoke path uses mcp-common telemetry; installed in CI
    _, c, _ = api
    assert post(c, "system.get_system_info", {"task_id": "x", "agent_id": AGENT}).status_code == 400
    assert post(c, "system.get_system_info", {"task_id": TASK, "agent_id": AGENT, "mode": "turbo"}).status_code == 400
    assert post(c, "nope.tool", {"task_id": TASK, "agent_id": AGENT}).status_code == 404
    blocked = post(c, "shell.run_command", {"task_id": TASK, "agent_id": AGENT, "args": {"command": "rm -rf /"}, "mode": "yolo"})
    assert blocked.status_code == 403 and blocked.json()["status"] == "blocked"
    ok = post(c, "fs.list_directory", {"task_id": TASK, "agent_id": AGENT, "args": {"path": str(tmp_path)}})
    assert ok.status_code == 200 and ok.json()["status"] == "ok" and ok.json()["receipt_id"]


def test_api_lists_tools_and_info(api):
    _, c, _ = api
    assert c.get("/v1/tools").json()["count"] == 41
    assert c.get("/v1/info").json()["runtime"] == "omnipilot"
