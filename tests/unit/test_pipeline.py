"""OpenMuse pipeline units: OTP extraction, nib fill/review plumbing (binary mocked here; the
real pinned nib runs in e2e), and the fail-honestly path."""
import json
from pathlib import Path

import pytest

import revenueos_runtime_omni.pipeline as pl


def test_otp_regex_matches_the_signup_service_wording():
    body = "Your verification code is 482917.\n\nOr open this link: http://signup-test:8090/magic?token=x\n"
    assert pl.OTP.search(body).group(1) == "482917"
    assert pl.OTP.search("no code here") is None


def test_fill_form_invokes_nib_with_json_data(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pl, "nib", lambda args, timeout=60: calls.append(args) or "")
    pdf, out = tmp_path / "in.pdf", tmp_path / "out.pdf"
    pl.fill_form(pdf, {"name": "A", "email": "a@b"}, out)
    assert calls[0][:2] == ["fill", str(pdf)]
    assert calls[0][2:4] == ["--data", str(out.with_suffix(".data.json"))]
    assert json.loads(out.with_suffix(".data.json").read_text()) == {"name": "A", "email": "a@b"}


def test_review_passes_only_when_every_field_round_trips(monkeypatch, tmp_path):
    filled = tmp_path / "filled.pdf"

    def fake_nib(args, timeout=60):
        assert args[0] == "export-xfdf"
        Path(args[-1]).write_text('<field name="name"><value>Agent X</value></field>'
                                  '<field name="email"><value>x@y.test</value></field>')
        return ""

    monkeypatch.setattr(pl, "nib", fake_nib)
    ok = pl.review_filled(filled, {"name": "Agent X", "email": "x@y.test"})
    assert ok["verdict"] == "PASS" and ok["problems"] == []
    bad = pl.review_filled(filled, {"name": "Agent X", "company": "RevenueOS"})
    assert bad["verdict"] == "FAIL" and any("company" in p for p in bad["problems"])


def test_nib_failures_raise_with_stderr(monkeypatch):
    import subprocess

    def fake_run(argv, **kw):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="field 'zz' not in form")

    monkeypatch.setattr(pl.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not in form"):
        pl.nib(["fill", "x.pdf"])


def test_pipeline_reports_failure_and_always_closes_the_browser(monkeypatch, tmp_path):
    closed = []

    class B:
        sessions = {}

        def open(self, a, t):
            raise RuntimeError("chromium exploded")

        def close(self, a):
            closed.append(a)

    res = pl.run_signup_pipeline(B(), "agent-1", "task-1", email_addr="a@b", login="a", password="p",
                                 signup_url="http://s", workdir=str(tmp_path))
    assert res.status == "failed" and "chromium exploded" in res.reason
    assert closed == ["agent-1"]           # the browser session never leaks
