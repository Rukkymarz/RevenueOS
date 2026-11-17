"""OpenMuse (spec 3.5): the human takeover console pauses the agent, carries keystrokes, and
hands the desk back; the persistent browser is fenced to agents with a provisioned profile.
xdotool and Playwright are mocked here; the live desktop runs in e2e."""
import subprocess

import pytest

from revenueos_runtime_omni.openmuse import Browser, TakenOver, Takeover
from revenueos_runtime_omni.runtime import Runtime, build_registry

TASK, AGENT = "7a1c2e30-0002-4000-8000-000000000001", "7a1c2e30-0001-4000-8000-000000000001"


@pytest.fixture
def xdotool_calls(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_attach_type_release_cycle(xdotool_calls):
    t = Takeover()
    assert t.status()["active"] is False
    t.attach("christine")
    assert t.status() == {**t.status(), "active": True, "holder": "christine"}
    t.type_text("christine", "hello from the console")
    t.key("christine", "Return")
    assert xdotool_calls[0][:2] == ["xdotool", "type"] and xdotool_calls[0][-1] == "hello from the console"
    assert xdotool_calls[1][:2] == ["xdotool", "key"]
    t.release("christine")
    assert t.status()["active"] is False and t.status()["typed_chars"] == len("hello from the console")


def test_desk_is_exclusive_and_typing_needs_attachment(xdotool_calls):
    t = Takeover()
    t.attach("christine")
    with pytest.raises(PermissionError):
        t.attach("mallory")
    with pytest.raises(PermissionError):
        t.type_text("mallory", "sneaky")
    with pytest.raises(PermissionError):
        t.release("mallory")
    t.release("christine")
    with pytest.raises(PermissionError):
        t.type_text("christine", "after release")
    assert xdotool_calls == []


def test_key_names_are_validated(xdotool_calls):
    t = Takeover()
    t.attach("h")
    with pytest.raises(ValueError):
        t.key("h", "Return; rm -rf /")
    with pytest.raises(ValueError):
        t.type_text("h", "x" * 5000)


def test_takeover_pauses_the_runtime_and_release_resumes(tmp_path, xdotool_calls):
    class FakeReceipts:
        def write(self, **kw):
            return "r-1"

        def deny(self, **kw):
            pass

    rt = Runtime(FakeReceipts(), workdir=str(tmp_path), registry=build_registry())
    rt.takeover = t = Takeover()
    (tmp_path / "f.txt").write_text("x")
    assert rt.invoke("fs.read_file", {"path": str(tmp_path / "f.txt")}, task_id=TASK, agent_id=AGENT).status == "ok"
    t.attach("christine")
    with pytest.raises(TakenOver):                 # the agent is paused while a human holds the desk
        rt.invoke("fs.read_file", {"path": str(tmp_path / "f.txt")}, task_id=TASK, agent_id=AGENT)
    t.release("christine")
    assert rt.invoke("fs.read_file", {"path": str(tmp_path / "f.txt")}, task_id=TASK, agent_id=AGENT).status == "ok"


# ------------------------------------------------------------------ browser fences (no playwright)
class FakeDB:
    def __init__(self, profile=None):
        self.profile = profile

    def one(self, sql, **kw):
        return {"profile_path": self.profile} if self.profile else None


def test_browser_requires_a_provisioned_profile(tmp_path):
    b = Browser(FakeDB(profile=None), None, str(tmp_path))
    with pytest.raises(PermissionError):           # INV-09: no identity, no browser
        b.open(AGENT, TASK)


def test_browser_actions_require_an_open_session(tmp_path):
    b = Browser(FakeDB(profile=str(tmp_path / "prof")), None, str(tmp_path))
    with pytest.raises(KeyError):
        b.goto(AGENT, "https://example.com")
    assert b.close(AGENT) == {"closed": False}


def test_download_target_cannot_escape_the_workspace(tmp_path):
    b = Browser(FakeDB(profile=str(tmp_path / "prof")), None, str(tmp_path / "work"))

    class S:
        page = None
    b.sessions[AGENT] = S()
    with pytest.raises(PermissionError):
        b.download(AGENT, "#dl", "../../etc/cron.d/evil")
