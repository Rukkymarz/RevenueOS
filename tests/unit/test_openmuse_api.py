"""runtime-omni HTTP surface for OpenMuse: takeover console, browser actions, pipeline route.
The desktop, Chromium and IMAP are faked; e2e drives the real ones."""
import importlib
import subprocess

import pytest

pytest.importorskip("httpx")
from starlette.testclient import TestClient  # noqa: E402

from revenueos_common.secrets import KeychainStore  # noqa: E402
from revenueos_runtime_omni.openmuse import Takeover  # noqa: E402
from revenueos_runtime_omni.runtime import Runtime, build_registry  # noqa: E402

TASK, AGENT = "7a1c2e30-0002-4000-8000-000000000001", "7a1c2e30-0001-4000-8000-000000000001"
H = {"authorization": "Bearer rt-token-123"}


class FakeReceipts:
    def __init__(self):
        self.written, self.denied = [], []

    def write(self, **kw):
        self.written.append(kw)
        return f"receipt-{len(self.written)}"

    def deny(self, **kw):
        self.denied.append(kw)

    def consume_approval(self, approval_id, args, risk_class, task_id=None, tool=None):
        if approval_id != "ok-approval":
            raise PermissionError("approval required")
        return approval_id


class FakeBrowser:
    def __init__(self):
        self.calls, self.sessions = [], {}

    def open(self, agent, task_id=None):
        self.calls.append(("open", agent))
        return {"status": "ok", "reused": False}

    def goto(self, agent, url):
        if url == "boom":
            raise RuntimeError("navigation failed")
        self.calls.append(("goto", url))
        return {"url": url, "title": "t"}

    def fill(self, agent, selector, value):
        self.calls.append(("fill", selector))
        return {"filled": selector}

    def text(self, agent):
        raise KeyError("no open browser session for this agent; call open first")

    def close(self, agent):
        return {"closed": True}


class FakeDB:
    def __init__(self):
        self.audits, self.identity = [], None

    def scalar(self, sql, **kw):
        self.audits.append(kw)
        return True

    def one(self, sql, **kw):
        return self.identity


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("REVENUEOS_KEYCHAIN_DIR", str(tmp_path / "kc"))
    kc = KeychainStore(tmp_path / "kc")
    kc.put("runtime-omni-token", "rt-token-123")
    kc.put("agent-mail-password", "pw")
    mod = importlib.import_module("revenueos_runtime_omni.app")
    rt = Runtime(FakeReceipts(), workdir=str(tmp_path), registry=build_registry())
    rt.takeover = Takeover()
    db = FakeDB()
    monkeypatch.setattr(mod, "runtime", lambda: rt)
    monkeypatch.setattr(mod, "db", db)
    monkeypatch.setitem(mod._state, "takeover", rt.takeover)
    monkeypatch.setitem(mod._state, "browser", FakeBrowser())
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))
    return mod, TestClient(mod.app), rt, db


def test_takeover_console_over_http(api):
    mod, c, rt, db = api
    assert c.post("/v1/takeover/attach", json={"holder": "christine"}).status_code == 401
    assert c.get("/v1/takeover/status", headers=H).json()["active"] is False
    assert c.post("/v1/takeover/attach", json={"holder": "christine"}, headers=H).json()["active"] is True
    # the agent is paused on both surfaces
    r = c.post("/v1/tools/system.get_system_info/invoke", json={"task_id": TASK, "agent_id": AGENT, "args": {}}, headers=H)
    assert r.status_code == 423 and r.json()["status"] == "paused"
    r = c.post("/v1/openmuse/browser/goto", json={"task_id": TASK, "agent_id": AGENT, "url": "http://x"}, headers=H)
    assert r.status_code == 423
    assert c.post("/v1/takeover/type", json={"holder": "christine", "text": "hi"}, headers=H).json()["typed_chars"] == 2
    assert c.post("/v1/takeover/key", json={"holder": "christine", "key": "Return"}, headers=H).status_code == 200
    assert c.post("/v1/takeover/key", json={"holder": "christine", "key": "a b;c"}, headers=H).status_code == 400
    assert c.post("/v1/takeover/type", json={"holder": "mallory", "text": "x"}, headers=H).status_code == 403
    assert c.post("/v1/takeover/dance", json={"holder": "christine"}, headers=H).status_code == 404
    assert c.post("/v1/takeover/release", json={"holder": "christine"}, headers=H).json()["active"] is False
    r = c.post("/v1/tools/system.get_system_info/invoke", json={"task_id": TASK, "agent_id": AGENT, "args": {}}, headers=H)
    assert r.status_code == 200                      # the agent resumed
    assert len(db.audits) >= 4                       # attach, type, key, release all audited


def test_browser_actions_are_classified_and_receipted(api):
    mod, c, rt, db = api
    base = {"task_id": TASK, "agent_id": AGENT}
    assert c.post("/v1/openmuse/browser/goto", json={**base, "url": "http://x"}).status_code == 401
    assert c.post("/v1/openmuse/browser/teleport", json=base, headers=H).status_code == 404
    assert c.post("/v1/openmuse/browser/goto", json={"task_id": "x", "agent_id": AGENT}, headers=H).status_code == 400
    assert c.post("/v1/openmuse/browser/goto", json=base, headers=H).status_code == 400      # url missing
    r = c.post("/v1/openmuse/browser/open", json=base, headers=H)
    assert r.status_code == 200 and r.json()["receipt_id"] == "receipt-1"
    r = c.post("/v1/openmuse/browser/goto", json={**base, "url": "http://signup-test:8090/"}, headers=H)
    assert r.status_code == 200 and rt.receipts.written[-1]["tool"] == "openmuse.browser.goto"
    # a failing action is a receipted error, not a silent drop
    r = c.post("/v1/openmuse/browser/goto", json={**base, "url": "boom"}, headers=H)
    assert r.status_code == 422 and rt.receipts.written[-1]["verdict"] == "error"
    # no session -> denied
    assert c.post("/v1/openmuse/browser/text", json=base, headers=H).status_code == 403
    # medium action in ask mode needs a hash-bound approval
    r = c.post("/v1/openmuse/browser/fill", json={**base, "selector": "#e", "value": "v", "mode": "ask"}, headers=H)
    assert r.status_code == 403 and r.json()["status"] == "approval_required" and rt.receipts.denied
    r = c.post("/v1/openmuse/browser/fill", json={**base, "selector": "#e", "value": "v", "mode": "ask",
                                                  "approval_id": "ok-approval"}, headers=H)
    assert r.status_code == 200 and rt.receipts.written[-1]["approval_id"] == "ok-approval"


def test_pipeline_route_fails_closed_without_identity_and_receipts_the_run(api, monkeypatch):
    mod, c, rt, db = api
    base = {"task_id": TASK, "agent_id": AGENT}
    assert c.post("/v1/openmuse/pipeline/signup", json=base).status_code == 401
    assert c.post("/v1/openmuse/pipeline/signup", json={"task_id": "x", "agent_id": AGENT}, headers=H).status_code == 400
    r = c.post("/v1/openmuse/pipeline/signup", json=base, headers=H)
    assert r.status_code == 403 and "INV-09" in r.json()["error"]
    db.identity = {"address": "muse@agents.test", "meta": {}}
    assert c.post("/v1/openmuse/pipeline/signup", json=base, headers=H).status_code == 403   # no password ref
    db.identity = {"address": "muse@agents.test", "meta": {"password_ref": "keychain://agent-mail-password",
                                                             "login": "muse"}}
    import revenueos_runtime_omni.pipeline as pl
    seen = {}

    def fake_run(browser, agent, task, **kw):
        seen.update(kw)
        res = pl.PipelineResult(status="completed", review={"verdict": "PASS", "problems": []}, draft_uid="3")
        res.stage("browser.open")
        return res

    monkeypatch.setattr(pl, "run_signup_pipeline", fake_run)
    r = c.post("/v1/openmuse/pipeline/signup", json=base, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["draft_uid"] == "3"
    assert seen["login"] == "muse" and seen["email_addr"] == "muse@agents.test"
    assert rt.receipts.written[-1]["tool"] == "openmuse.pipeline.signup"
    assert "pw" not in str(r.json())                 # the mailbox password never leaves the service
    rt.takeover.attach("christine")
    assert c.post("/v1/openmuse/pipeline/signup", json=base, headers=H).status_code == 423
