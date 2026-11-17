"""Pure-function tests for the aegis-os engine glue (argv construction, diff-json parsing).
No binary required: these prove our own code is correct against the CLI shape read directly
from heurion-org/aegis-os's source (crates/aos-cli/src/main.rs) at the pinned commit."""
import json
from pathlib import Path

import pytest

from revenueos_sandbox import aegis


def test_binary_missing_raises_on_run_and_diff(monkeypatch):
    monkeypatch.setattr(aegis.shutil, "which", lambda name: None)
    with pytest.raises(aegis.AegisUnavailable):
        aegis.run_argv(["echo", "hi"])
    with pytest.raises(aegis.AegisUnavailable):
        aegis.diff_argv()


def test_run_argv_shape(monkeypatch):
    monkeypatch.setattr(aegis.shutil, "which", lambda name: "/usr/local/bin/aegis-os")
    argv = aegis.run_argv(["python3", "-c", "print(1)"])
    assert argv == ["/usr/local/bin/aegis-os", "run", "--mode", "implement", "--profile", "code",
                    "--enforcement", "enforced", "--", "python3", "-c", "print(1)"]


def test_run_argv_rejects_hyphen_values_safely(monkeypatch):
    """`cmd` is a trailing var-arg with allow_hyphen_values=true on the real CLI, so an argv
    starting with a flag-shaped token (e.g. `-x`) must still land after `--`, not be swallowed
    as an aegis-os flag."""
    monkeypatch.setattr(aegis.shutil, "which", lambda name: "/usr/local/bin/aegis-os")
    argv = aegis.run_argv(["-x", "weird"])
    assert argv[argv.index("--") + 1:] == ["-x", "weird"]


def test_run_argv_rejects_unknown_enforcement(monkeypatch):
    monkeypatch.setattr(aegis.shutil, "which", lambda name: "/usr/local/bin/aegis-os")
    with pytest.raises(ValueError):
        aegis.run_argv(["echo"], enforcement="yolo")


def test_diff_argv_shape(monkeypatch):
    monkeypatch.setattr(aegis.shutil, "which", lambda name: "/usr/local/bin/aegis-os")
    assert aegis.diff_argv() == ["/usr/local/bin/aegis-os", "diff", "--json"]


def test_parse_diff_empty_stdout_means_no_session():
    assert aegis.parse_diff("") is None
    assert aegis.parse_diff("   \n") is None


def test_parse_diff_parses_real_shape():
    payload = json.dumps({
        "session_id": "sess-1",
        "session_dir": "/aegis-runtime/sessions/sess-1",
        "workspace": "/workspace",
        "shadow": "/aegis-runtime/sessions/sess-1/cow_workspace",
        "changed_count": 2,
        "evidence_hash": "sha256:abc123",
        "raw_diff_hash": "abc123",
        "pinned_commit_command": "aegis-os commit --session sess-1 --expected-diff-hash sha256:abc123",
        "evidence": [],
    })
    d = aegis.parse_diff(payload)
    assert d is not None
    assert d.session_id == "sess-1"
    assert d.session_dir == Path("/aegis-runtime/sessions/sess-1")
    assert d.workspace == Path("/workspace")
    assert d.shadow == Path("/aegis-runtime/sessions/sess-1/cow_workspace")
    assert d.changed_count == 2
    assert d.evidence_hash == "sha256:abc123"


def test_parse_diff_malformed_nonempty_output_raises():
    with pytest.raises(json.JSONDecodeError):
        aegis.parse_diff("not json")
