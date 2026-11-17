"""OpenMuse Browser against a fake Playwright: session lifecycle, egress wiring, download
jail, and the full pipeline success path with fake IMAP and mocked nib. The real Chromium and
the real nib binary run in e2e."""
import sys
import types
from pathlib import Path

import pytest

from revenueos_runtime_omni.openmuse import Browser

TASK, AGENT = "7a1c2e30-0002-4000-8000-000000000001", "7a1c2e30-0001-4000-8000-000000000001"


class FakeDownload:
    suggested_filename = "intake-form.pdf"

    def save_as(self, dest):
        Path(dest).write_bytes(b"%PDF-fake")


class FakePage:
    def __init__(self):
        self.url, self.actions = "about:blank", []

    def goto(self, url, timeout=None, wait_until=None):
        self.url = url
        self.actions.append(("goto", url))

    def title(self):
        return "Fake"

    def fill(self, sel, val, timeout=None):
        self.actions.append(("fill", sel, val))

    def click(self, sel, timeout=None):
        self.actions.append(("click", sel))

    def inner_text(self, sel, timeout=None):
        return f"text of {sel}"

    def content(self):
        return '<html>fake <p id="sent">ok</p></html>'

    def expect_download(self, timeout=None):
        page = self

        class CM:
            def __enter__(self):
                class V:
                    value = FakeDownload()
                return V()

            def __exit__(self, *a):
                return False
        return CM()


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.closed = False

    def new_page(self):
        return FakePage()

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, log):
        self.log = log

    def launch_persistent_context(self, profile, **kw):
        self.log.append((profile, kw))
        return FakeContext()


@pytest.fixture
def fake_playwright(monkeypatch):
    launches = []

    class PW:
        def __init__(self):
            self.chromium = FakeChromium(launches)

    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = lambda: types.SimpleNamespace(start=lambda: PW())
    pkg = types.ModuleType("playwright")
    pkg.sync_api = mod
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    return launches


class DB:
    def __init__(self, profile):
        self.profile = profile

    def one(self, sql, **kw):
        return {"profile_path": self.profile}


class FakeEgressCM:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append("open")
        return ("http://127.0.0.1:31280", "/run/ca.pem")

    def __exit__(self, *a):
        self.log.append("close")
        return False


def test_browser_session_lifecycle_with_pinned_egress(fake_playwright, tmp_path):
    egress_log = []
    b = Browser(DB(str(tmp_path / "prof")), lambda a, t: FakeEgressCM(egress_log), str(tmp_path / "work"))
    out = b.open(AGENT, TASK)
    assert out == {"status": "ok", "reused": False, "profile": str(tmp_path / "prof" / "user-data")}
    profile, kw = fake_playwright[0]
    assert profile.endswith("user-data")
    assert kw["proxy"] == {"server": "http://127.0.0.1:31280"}      # identity-pinned egress
    assert kw["headless"] is False and "--no-sandbox" in kw["args"]
    assert b.open(AGENT, TASK)["reused"] is True                     # persistent: one context
    assert b.goto(AGENT, "http://signup-test:8090/")["title"] == "Fake"
    assert b.fill(AGENT, "#email", "a@b") == {"filled": "#email"}
    assert b.click(AGENT, "#submit")["clicked"] == "#submit"
    assert "fake" in b.text(AGENT)["text"]
    saved = b.download(AGENT, "#download", "pipeline/t/form.pdf")
    assert Path(saved["saved"]).read_bytes() == b"%PDF-fake"
    assert b.close(AGENT) == {"closed": True}
    assert egress_log == ["open", "close"]                           # session closed with browser


def test_pipeline_success_path_end_to_end_with_fakes(fake_playwright, tmp_path, monkeypatch):
    import revenueos_runtime_omni.pipeline as pl
    b = Browser(DB(str(tmp_path / "prof")), None, str(tmp_path / "work"))
    monkeypatch.setattr(pl, "wait_for_otp", lambda *a, **k: "123456")
    filled_values = {}

    def fake_nib(args, timeout=60):
        if args[0] == "fill":
            import xml.etree.ElementTree as ET
            ns = {"x": "http://ns.adobe.com/xfdf/"}
            filled_values.update({f.get("name"): f.find("x:value", ns).text
                                  for f in ET.fromstring(Path(args[3]).read_text()).iterfind(".//x:field", ns)})
            Path(args[-1]).write_bytes(b"%PDF-filled")
        else:
            Path(args[-1]).write_text("".join(f"<value>{v}</value>" for v in filled_values.values()))
        return ""

    monkeypatch.setattr(pl, "nib", fake_nib)
    drafted = {}

    def fake_draft(host, port, login, from_addr, password, to, subject, body, attachment):
        drafted.update(login=login, attachment=attachment.read_bytes())
        return "7"

    monkeypatch.setattr(pl, "draft_reply", fake_draft)
    res = pl.run_signup_pipeline(b, AGENT, TASK, email_addr="muse@agents.test", login="muse",
                                 password="pw", signup_url="http://signup-test:8090",
                                 workdir=str(tmp_path / "work"))
    assert res.status == "completed", res.reason
    assert [s["stage"] for s in res.stages] == ["browser.open", "signup.submitted", "otp.extracted",
                                                "signup.verified", "form.downloaded", "form.filled",
                                                "review", "reply.drafted"]
    assert res.review["verdict"] == "PASS" and res.draft_uid == "7"
    assert filled_values["email"] == "muse@agents.test" and filled_values["company"] == "RevenueOS"
    assert drafted["login"] == "muse" and drafted["attachment"] == b"%PDF-filled"
    assert AGENT not in b.sessions                                   # browser closed either way
