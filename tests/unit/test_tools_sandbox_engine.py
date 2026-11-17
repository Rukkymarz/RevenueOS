"""`engine="aegis"` threaded through `revenueos_runtime_os.tools.shell_run()` itself — the exact
integration point `sandbox.run`'s ToolSpec calls, and the one place `args.get("engine", ...)` is
read and `shadow_root` cleanup happens (see services/runtime-os/revenueos_runtime_os/tools.py).

This is deliberately NOT routed through the full NAVA gateway (`nava.call()`): the gateway's
`classify` step imports `omnipilot.permission.danger` unconditionally for every `sandbox.run`
call, and that package isn't installable in this sandboxed dev environment (no network for pip) —
a known, pre-existing gap unrelated to this engine (see tests/nava/test_nava_invariants.py, where
more than half the tests already fail locally for the identical reason; CI installs the real
package and is where that path is proven). Calling `shell_run()` directly, the way
tests/nava/test_gateway_unit.py already does for other pure-function tool paths, proves the real
`args` -> `run_in_sandbox(engine=...)` wiring and the `shadow_root`-based cleanup without needing
the gateway's risk classifier at all.

Uses the same fake-`aegis-os`-binary technique as tests/unit/test_sandbox_aegis_engine.py (the
real Rust binary only builds in CI — network to crates.io is blocked here too).
"""
import os
import stat

import pytest

from revenueos_runtime_os.nava import CallContext, Workspaces
from revenueos_runtime_os.tools import shell_run, builtin_tools

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
def fake_aegis_bin(tmp_path_factory, monkeypatch):
    bindir = tmp_path_factory.mktemp("aegis-bin")
    script = bindir / "aegis-os"
    script.write_text(FAKE_AEGIS_OS)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    return script


def _ctx(ws):
    return CallContext("sc", "agent1", "task1", "auto", None, ws)


def test_sandbox_run_toolspec_schema_declares_engine_enum():
    spec = builtin_tools()["sandbox.run"]
    assert spec.schema["properties"]["engine"]["enum"] == ["bubblewrap", "aegis"]


def test_shell_run_threads_engine_aegis_into_run_in_sandbox(tmp_path, fake_aegis_bin):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    ctx = _ctx(ws)
    out = shell_run(ctx, {"workspace": "w", "argv": ["sh", "-c", "echo hi > made.txt"], "engine": "aegis"})
    assert out["status"] == "ok"
    assert out["applied"] == ["made.txt"]
    assert (ws.path("agent1", "w") / "made.txt").read_text() == "hi\n"


def test_shell_run_defaults_to_bubblewrap_when_engine_omitted(tmp_path):
    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    ctx = _ctx(ws)
    out = shell_run(ctx, {"workspace": "w", "argv": ["sh", "-c", "echo hi > made.txt"]})
    assert out["status"] == "ok"
    assert (ws.path("agent1", "w") / "made.txt").read_text() == "hi\n"


def test_shell_run_cleans_up_the_true_outer_tempdir_for_aegis(tmp_path, fake_aegis_bin, monkeypatch):
    # Prove the shadow_root fix: the aegis engine's result.shadow is a NESTED session directory,
    # not a direct child of the outer tempdir, so cleanup must use shadow_root, not shadow.parent.
    created_roots = []
    from revenueos_sandbox import supervisor as supervisor_mod
    orig = supervisor_mod.run_in_sandbox

    def spy(*a, **kw):
        r = orig(*a, **kw)
        created_roots.append(r.shadow_root)
        return r

    monkeypatch.setattr("revenueos_sandbox.supervisor.run_in_sandbox", spy)

    ws = Workspaces(tmp_path / "ws", tmp_path / "snap")
    ctx = _ctx(ws)
    shell_run(ctx, {"workspace": "w2", "argv": ["sh", "-c", "echo x > f.txt"], "engine": "aegis"})

    assert len(created_roots) == 1 and created_roots[0] is not None
    assert not created_roots[0].exists()   # cleaned up via shadow_root, not leaked
