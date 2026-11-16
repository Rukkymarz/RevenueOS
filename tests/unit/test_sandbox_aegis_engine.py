"""`engine="aegis"` end-to-end through supervisor.run_in_sandbox(), against a FAKE `aegis-os`
binary (a small Python script standing in for the real Rust one) rather than mocking
subprocess calls directly. This proves the actual plumbing — argv construction with `--`,
AOS_RUNTIME_DIR scoping, cwd handling, the `run` then `diff --json` sequence, and feeding the
result into the existing commit() path — independently of whether the real binary (built only
in CI/the Docker image — see tests/e2e for that proof) behaves exactly like our stand-in.

The fake mirrors the real CLI's documented behavior, read from aos-cli's source at the pinned
commit (crates/aos-cli/src/main.rs / launcher.rs):
  * `run --mode M --profile P --enforcement E -- <cmd...>` creates a session under
    $AOS_RUNTIME_DIR/sessions/<id>/cow_workspace (a copy of cwd), execs <cmd...> with that as
    cwd, and writes session.json with {session_id, workspace, shadow}.
  * `diff --json` reads the latest session.json and prints {session_id, session_dir, workspace,
    shadow, changed_count, evidence_hash}.
"""
import os
import stat
import uuid
from pathlib import Path

import pytest

from revenueos_sandbox.supervisor import SandboxUnavailable, Quotas, commit, run_in_sandbox

AGENT, TASK = str(uuid.uuid4()), str(uuid.uuid4())

FAKE_AEGIS_OS = r"""#!/usr/bin/env python3
import json, os, shutil, subprocess, sys, uuid
from pathlib import Path

def manifest(root):
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = Path(dirpath) / n
            out[str(p.relative_to(root))] = p.read_bytes()
    return out

args = sys.argv[1:]
if args[0] == "run":
    i = args.index("--")
    cmd = args[i + 1:]
    runtime_dir = Path(os.environ["AOS_RUNTIME_DIR"])
    sid = "sess-" + uuid.uuid4().hex[:8]
    session_dir = runtime_dir / "sessions" / sid
    shadow = session_dir / "cow_workspace"
    shadow.mkdir(parents=True)
    project = Path.cwd()
    shutil.copytree(project, shadow, dirs_exist_ok=True)
    session_dir.joinpath("session.json").write_text(json.dumps(
        {"session_id": sid, "workspace": str(project), "shadow": str(shadow)}))
    rc = subprocess.call(cmd, cwd=shadow)
    sys.exit(rc)
elif args[0] == "diff":
    runtime_dir = Path(os.environ["AOS_RUNTIME_DIR"])
    sessions = sorted((runtime_dir / "sessions").iterdir(), key=lambda p: p.stat().st_mtime)
    if not sessions:
        print("")
        sys.exit(0)
    session_dir = sessions[-1]
    meta = json.loads((session_dir / "session.json").read_text())
    before = manifest(meta["workspace"])
    after = manifest(meta["shadow"])
    changed = len(before.keys() ^ after.keys()) + sum(
        1 for k in before.keys() & after.keys() if before[k] != after[k])
    print(json.dumps({
        "session_id": meta["session_id"], "session_dir": str(session_dir),
        "workspace": meta["workspace"], "shadow": meta["shadow"],
        "changed_count": changed, "evidence_hash": "sha256:fake",
    }))
    sys.exit(0)
else:
    sys.exit(2)
"""


@pytest.fixture
def fake_aegis_bin(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "aegis-os"
    script.write_text(FAKE_AEGIS_OS)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    return script


def test_engine_aegis_unavailable_without_the_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(SandboxUnavailable):
        run_in_sandbox(["true"], tmp_path, engine="aegis")


def test_engine_aegis_rejects_egress_and_env(tmp_path, fake_aegis_bin):
    # run_in_sandbox only checks `egress is not None` before engine="aegis" raises, so any
    # truthy sentinel proves the rejection without needing a real EgressSession's constructor args.
    with pytest.raises(NotImplementedError):
        run_in_sandbox(["true"], tmp_path, engine="aegis", egress=object())
    with pytest.raises(NotImplementedError):
        run_in_sandbox(["true"], tmp_path, engine="aegis", env={"X": "1"})


def test_engine_aegis_runs_and_diffs_a_file_write(tmp_path, fake_aegis_bin):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "existing.txt").write_text("hello")

    result = run_in_sandbox(
        ["python3", "-c", "open('new.txt','w').write('x'); open('existing.txt','w').write('bye')"],
        workspace, agent_id=AGENT, task_id=TASK, quotas=Quotas(wall_seconds=10),
        keep_shadow=True, engine="aegis")

    assert result.status == "ok"
    assert result.backend == "aegis-os"
    assert result.changes == {"new.txt": "added", "existing.txt": "modified"}
    assert result.shadow is not None
    assert (result.shadow / "new.txt").read_text() == "x"
    # the ORIGINAL workspace is untouched: aegis-os's own run never writes back on its own
    assert not (workspace / "new.txt").exists()
    assert (workspace / "existing.txt").read_text() == "hello"


def test_engine_aegis_result_can_be_committed(tmp_path, fake_aegis_bin):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    result = run_in_sandbox(["python3", "-c", "open('made.txt','w').write('ok')"], workspace,
                            agent_id=AGENT, task_id=TASK, quotas=Quotas(wall_seconds=10),
                            keep_shadow=True, engine="aegis")

    applied = commit(result, workspace, result.changeset_hash)
    assert applied == ["made.txt"]
    assert (workspace / "made.txt").read_text() == "ok"


def test_engine_aegis_reports_failure_from_the_wrapped_command(tmp_path, fake_aegis_bin):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    result = run_in_sandbox(["python3", "-c", "import sys; sys.exit(3)"], workspace,
                            agent_id=AGENT, task_id=TASK, quotas=Quotas(wall_seconds=10),
                            engine="aegis")

    assert result.status == "failed"
    assert result.exit_code == 3


def test_engine_aegis_runs_from_an_empty_workspace_with_no_changes(tmp_path, fake_aegis_bin):
    result = run_in_sandbox(["true"], None, agent_id=AGENT, task_id=TASK,
                            quotas=Quotas(wall_seconds=10), engine="aegis")
    assert result.status == "ok"
    assert result.changes == {}


def test_engine_aegis_rejects_blocklisted_commands(tmp_path, fake_aegis_bin):
    result = run_in_sandbox(["rm", "-rf", "/"], tmp_path, engine="aegis")
    assert result.status == "blocked"
