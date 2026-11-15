"""Sandbox supervisor: blocklist, COW commit, quotas, and the identity-pinned egress path
(sandbox -> relay -> per-session Unix socket -> forwarder -> proxy)."""
import http.server
import json
import threading
import uuid

import pytest

from revenueos_common import egress_identity
from revenueos_sandbox import blocklist
from revenueos_sandbox.egress import EgressSession, rewrite_head
from revenueos_sandbox.supervisor import Quotas, commit, run_in_sandbox, seatbelt_profile
from sandbox_kit import needs_sandbox

AGENT, TASK, KEY = str(uuid.uuid4()), str(uuid.uuid4()), "k" * 32


@pytest.mark.parametrize("argv", [
    ["rm", "-rf", "/"], ["rm", "-fr", "/*"], ["/bin/rm", "--recursive", "--force", "/home"], ["rm", "-rf", "~"],
    ["rm", "--no-preserve-root", "-r", "x"], ["sudo", "rm", "-rf", "/etc"], ["timeout", "5", "rm", "-rf", "/usr"],
    ["mkfs.ext4", "/dev/sda1"], ["dd", "if=/dev/zero", "of=/dev/nvme0n1"], ["chmod", "-R", "777", "/"],
    ["chown", "-R", "x", "/var"], ["shutdown", "-h", "now"], ["systemctl", "reboot"], ["find", "/", "-delete"],
    ["sh", "-c", "ls; rm -rf / && echo"], ["bash", "-lc", "echo hi > /dev/sda"], ["sh", "-c", ":(){ :|:& };:"],
    ["busybox", "rm", "-rf", "/"], ["mv", "/etc", "/tmp/x"], ["init", "0"], [],
])
def test_blocklist_blocks_destructive_commands(argv):
    assert blocklist.check(argv)


@pytest.mark.parametrize("argv", [
    ["rm", "-rf", "build"], ["rm", "-rf", "./node_modules"], ["rm", "file.txt"], ["ls", "-la", "/"],
    ["chmod", "-R", "u+w", "dist"], ["sh", "-c", "echo 'rm -rf /' > notes.txt"], ["dd", "if=a", "of=b"],
    ["python3", "-c", "print(1)"], ["find", ".", "-name", "*.pyc", "-delete"],
])
def test_blocklist_allows_ordinary_work(argv):
    assert blocklist.check(argv) is None


def test_rewrite_head_strips_spoofed_identity_and_forces_close():
    head = (b"GET http://h:80/x HTTP/1.1\r\nHost: h\r\nX-RevenueOS-Agent: someone-else\r\n"
            b"x-revenueos-sig: forged\r\nConnection: keep-alive")
    out = rewrite_head(head, {"x-revenueos-agent": AGENT, "x-revenueos-sig": "real"}).decode()
    assert "someone-else" not in out and "forged" not in out
    assert f"x-revenueos-agent: {AGENT}" in out and out.count("x-revenueos-sig") == 1
    assert "connection: close" in out and "keep-alive" not in out.lower()


def test_rewrite_head_refuses_connect_tunnels_and_garbage():
    assert rewrite_head(b"CONNECT h:443 HTTP/1.1\r\nHost: h:443", {}) is None
    assert rewrite_head(b"garbage", {}) is None


def test_identity_signature_round_trip_and_tamper():
    s = egress_identity.sign(KEY, "s1", AGENT, TASK, ts=1000)
    args = (s["x-revenueos-session"], s["x-revenueos-agent"], s["x-revenueos-task"], s["x-revenueos-ts"], s["x-revenueos-sig"])
    assert egress_identity.verify(KEY, *args, now=1010) is None
    assert "invalid" in egress_identity.verify(KEY, "s1", str(uuid.uuid4()), TASK, *args[3:], now=1010)
    assert "expired" in egress_identity.verify(KEY, *args, now=1000 + 301)
    assert "not identity-pinned" in egress_identity.verify(KEY, "", AGENT, TASK, "", "", now=1000)
    assert "invalid" in egress_identity.verify("other-key", *args, now=1010)


def test_seatbelt_profile_denies_by_default_and_writes_only_the_shadow(tmp_path):
    p = seatbelt_profile(tmp_path, tmp_path / "egress.sock")
    assert "(deny default)" in p and f'(subpath "{tmp_path}")' in p and "network-outbound (remote unix-socket" in p
    assert "network*" not in p


def test_commit_requires_the_approved_changeset_hash(tmp_path):
    from revenueos_sandbox.supervisor import SandboxResult
    r = SandboxResult("ok", 0, changes={"a": "added"}, changeset=["a"], changeset_hash="h", shadow=tmp_path)
    with pytest.raises(PermissionError):
        commit(r, tmp_path, "other")
    with pytest.raises(PermissionError):
        commit(SandboxResult("failed", 1, changeset_hash="h", shadow=tmp_path), tmp_path, "h")


class _Proxy(http.server.BaseHTTPRequestHandler):
    """Stands in for Envoy + egress-authz: records what the forwarder sent."""
    seen: list = []

    def do_GET(self):
        h = {k.lower(): v for k, v in self.headers.items()}
        _Proxy.seen.append({"path": self.path, "headers": h})
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def proxy():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Proxy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Proxy.seen = []
    yield srv.server_address
    srv.shutdown()


@needs_sandbox
def test_sandbox_egress_goes_only_through_the_signed_forwarder(proxy):
    opened, closed = [], []
    with EgressSession(AGENT, TASK, KEY, proxy, on_open=opened.append, on_close=closed.append) as s:
        code = ("import urllib.request as u; r=u.Request('http://upstream-echo:8080/ok', headers={'x-revenueos-agent':'evil'});"
                "print(u.urlopen(r, timeout=10).read().decode())")
        r = run_in_sandbox(["python3", "-c", code], egress=s)
        direct = run_in_sandbox(["python3", "-c", "import socket; socket.create_connection(('1.1.1.1', 80), 3)"], egress=s)
    assert r.status == "ok", r.stderr
    assert json.loads(r.stdout) == {"ok": True}
    seen = _Proxy.seen[-1]["headers"]
    assert seen["x-revenueos-agent"] == AGENT and seen["x-revenueos-task"] == TASK
    assert seen["x-revenueos-session"] == s.session_id
    assert egress_identity.verify(KEY, seen["x-revenueos-session"], seen["x-revenueos-agent"], seen["x-revenueos-task"],
                                  seen["x-revenueos-ts"], seen["x-revenueos-sig"]) is None
    assert _Proxy.seen[-1]["path"] == "http://upstream-echo:8080/ok"
    assert direct.exit_code != 0 and "Network is unreachable" in direct.stderr
    assert opened == [s] and closed == [s]


@needs_sandbox
def test_https_tunnels_from_the_sandbox_are_refused(proxy):
    with EgressSession(AGENT, TASK, KEY, proxy) as s:
        code = "import urllib.request as u; u.urlopen('https://example.com', timeout=10)"
        r = run_in_sandbox(["python3", "-c", code], egress=s)
    assert r.status == "failed" and "403" in r.stderr
    assert _Proxy.seen == []


@needs_sandbox
def test_quotas_bound_time_memory_cpu_and_processes():
    assert run_in_sandbox(["sleep", "5"], quotas=Quotas(wall_seconds=1)).status == "timeout"
    assert run_in_sandbox(["python3", "-c", "while True: pass"], quotas=Quotas(cpu_seconds=1)).status == "killed"
    mem = run_in_sandbox(["python3", "-c", "x = bytearray(400 << 20)"], quotas=Quotas(memory_mb=200))
    assert mem.exit_code != 0 and "MemoryError" in mem.stderr
    lim = run_in_sandbox(["sh", "-c", "grep -E 'Max processes' /proc/self/limits"], quotas=Quotas(pids=64))
    assert lim.stdout.split()[2:4] == ["64", "64"]


@needs_sandbox
def test_agent_runs_unprivileged_and_env_cannot_override_the_proxy():
    assert "uid=1000" in run_in_sandbox(["id"]).stdout
    with pytest.raises(ValueError):
        run_in_sandbox(["true"], env={"HTTP_PROXY": "http://elsewhere"})
