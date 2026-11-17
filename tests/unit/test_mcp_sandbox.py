"""`revenueos-mcp-sandbox` (spec 4.5, 4.7): the trace analyzer on its own, and a real hostile
MCP server run through the real wrapper (Bubblewrap + strace): network egress, secret reads and
writes outside the sandbox are all blocked, and all three are in the trace."""
import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

from revenueos_discovery import sandbox_exec
from revenueos_discovery.sandbox_exec import analyze, build_argv
from sandbox_kit import needs_sandbox

ROOT = Path(__file__).resolve().parents[2]
HAVE_STRACE = shutil.which("strace") is not None
if os.environ.get("REVENUEOS_REQUIRE_SANDBOX") == "1" and not HAVE_STRACE:
    raise RuntimeError("REVENUEOS_REQUIRE_SANDBOX=1 but strace is not installed")
needs_strace = pytest.mark.skipif(not HAVE_STRACE, reason="strace not installed (required in CI)")

TRACE = '''10 execve("/usr/bin/bwrap", ["bwrap"], 0x7ffd /* 3 vars */) = 0
10 openat(AT_FDCWD, "/etc/passwd", O_WRONLY|O_CREAT, 0644) = -1 EACCES (Permission denied)
11 execve("/usr/local/sbin/python3", ["python3", "srv.py"], 0x55 /* 6 vars */) = -1 ENOENT (No such file or directory)
11 execve("/usr/bin/python3", ["python3", "srv.py"], 0x55 /* 6 vars */) = 0
11 openat(AT_FDCWD, "/usr/lib/python3.12/os.py", O_RDONLY|O_CLOEXEC) = 3
11 openat(AT_FDCWD, "/usr/lib/python3.12/__pycache__/os.cpython-312.pyc.1", O_WRONLY|O_CREAT|O_EXCL, 0644) = -1 EROFS (Read-only file system)
11 openat(AT_FDCWD, "notes.txt", O_WRONLY|O_CREAT|O_TRUNC, 0644) = 4
11 openat(AT_FDCWD, "/workspace/out.json", O_WRONLY|O_CREAT, 0644) = 4
11 openat(AT_FDCWD, "/dev/null", O_RDWR) = 5
11 connect(6, {sa_family=AF_INET, sin_port=htons(3128), sin_addr=inet_addr("127.0.0.1")}, 16) = 0
11 connect(6, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT (No such file or directory)
11 connect(7, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.216.34")}, 16 <unfinished ...>
12 openat(AT_FDCWD, "/run/revenueos/keychain/api-token-owner", O_RDONLY) = -1 ENOENT (No such file or directory)
11 <... connect resumed>) = -1 ENETUNREACH (Network is unreachable)
11 connect(7, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.216.34")}, 16) = -1 ENETUNREACH (Network is unreachable)
11 connect(8, {sa_family=AF_INET6, sin6_port=htons(53), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "2606:4700::1111", &sin6_addr), sin6_scope_id=0}, 28) = -1 ENETUNREACH (Network is unreachable)
12 openat(AT_FDCWD, "/workspace/.ssh/id_rsa", O_RDONLY) = 9
12 mkdir("/etc/owned", 0755) = -1 EROFS (Read-only file system)
12 unlinkat(AT_FDCWD, "/usr/bin/python3", 0) = -1 EROFS (Read-only file system)
12 renameat2(AT_FDCWD, "/workspace/a", AT_FDCWD, "/etc/b", 0) = -1 EXDEV (Invalid cross-device link)
12 openat(AT_FDCWD, "/var/data", O_WRONLY|O_CREAT, 0644) = 10
12 connect(9, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("10.0.0.5")}, 16) = 0
12 getpid() = 12
garbage line
'''


def test_analyze_ignores_sandbox_setup_and_reports_each_violation_once():
    got = {(e["kind"], e["target"]) for e in analyze(TRACE, "python3")}
    assert got == {
        ("egress_blocked", "93.184.216.34:443"), ("egress_blocked", "2606:4700::1111:53"),
        ("secret_read_blocked", "/run/revenueos/keychain/api-token-owner"),
        ("secret_read", "/workspace/.ssh/id_rsa"),
        ("sandbox_write_blocked", "/etc/owned"), ("sandbox_write_blocked", "/usr/bin/python3"),
        ("sandbox_write_blocked", "/etc/b"),
        ("sandbox_escape", "/var/data"), ("sandbox_escape", "10.0.0.5:80"),
    }
    by = {e["target"]: e for e in analyze(TRACE, "python3")}
    assert by["/etc/owned"]["errno"] == "EROFS" and by["/etc/owned"]["syscall"] == "mkdir"


def test_analyze_reports_nothing_before_the_payload_starts_or_for_a_clean_server():
    assert analyze(TRACE, "node") == []          # payload never exec'd: only sandbox setup in the log
    clean = "\n".join(TRACE.splitlines()[:11])
    assert analyze(clean, "/usr/bin/python3") == []


def test_build_argv_refuses_bad_names_and_missing_strace(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_exec, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        build_argv("../etc", ["true"], {})
    monkeypatch.setattr(sandbox_exec.shutil, "which", lambda _: None)
    from revenueos_sandbox.supervisor import SandboxUnavailable
    with pytest.raises(SandboxUnavailable, match="unmonitored"):
        build_argv("ok", ["true"], {})


@needs_sandbox
@needs_strace
def test_build_argv_wraps_in_strace_and_bwrap_and_forwards_only_declared_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_exec, "ROOT", tmp_path)
    cmd, log = build_argv("srv", ["python3", "/src/infra/discovery/x.py"], {"FILES_TOKEN": "v"})
    assert cmd[0].endswith("strace") and "-f" in cmd and str(log) in cmd
    assert any(c.endswith("bwrap") for c in cmd) and "--unshare-all" in cmd and "--clearenv" in cmd
    i = cmd.index("FILES_TOKEN")
    assert cmd[i - 1] == "--setenv" and cmd[i + 1] == "v"
    assert cmd[-2:] == ["python3", "/src/infra/discovery/x.py"]
    assert log.parent == tmp_path / "srv" / "trace" and (tmp_path / "srv" / "ws").is_dir()
    assert log.with_suffix(".payload").read_text() == "python3"
    assert sandbox_exec._egress("srv") is None      # no egress.json: no network at all


@needs_sandbox
@needs_strace
def test_hostile_mcp_server_is_blocked_on_all_three_and_all_three_are_traced(tmp_path):
    """Acceptance 4 at unit level: the real malicious test server, through the real wrapper."""
    from revenueos_mcp_common import RawStdioClient
    ws = tmp_path / "evil" / "ws"
    pkg = ws / "revenueos_mcp_common"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    shutil.copy(ROOT / "packages/mcp-common/revenueos_mcp_common/plain.py", pkg / "plain.py")
    shutil.copy(ROOT / "infra/discovery/test-servers/malicious_server.py", ws / "malicious_server.py")
    env = {"PATH": os.environ["PATH"], "REVENUEOS_MCP_ROOT": str(tmp_path), "HOST_ONLY_SECRET": "must-not-leak",
           "PGPASSWORD": "must-not-leak",
           "PYTHONPATH": os.pathsep.join(str(ROOT / p) for p in ("services/discovery", "infra/sandbox-supervisor",
                                                                 "packages/pycommon", "packages/risk"))}
    client = RawStdioClient(sys.executable, ["-m", "revenueos_discovery.sandbox_exec", "evil", "--env", "HOST_ONLY_SECRET_X",
                                             "--", "python3", "/workspace/malicious_server.py"], env=env, timeout_s=60)
    out = asyncio.run(client.acall("attack", {}))
    assert out["egress"] and all(v.startswith("blocked") for v in out["egress"].values()), out
    assert out["secrets"] and all(v.startswith("blocked") for v in out["secrets"].values()), out
    assert out["writes"] and all(v.startswith("blocked") for v in out["writes"].values()), out
    assert out["env_leaks"] == []

    logs = list((tmp_path / "evil" / "trace").glob("*.log"))
    assert len(logs) == 1
    events = analyze(logs[0].read_text(errors="replace"), logs[0].with_suffix(".payload").read_text())
    kinds = {e["kind"] for e in events}
    assert {"egress_blocked", "secret_read_blocked", "sandbox_write_blocked"} <= kinds, events
    assert not kinds & {"secret_read", "sandbox_escape"}, events
    assert "must-not-leak" not in logs[0].read_text(errors="replace")
