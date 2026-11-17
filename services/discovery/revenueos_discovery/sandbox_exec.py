"""`revenueos-mcp-sandbox`: every installed stdio MCP server runs through this (spec 4.7).

The server gets its own Bubblewrap sandbox (own namespaces, read-only system, one private
writable directory, cleared environment with only its own declared variables, no network
unless its own identity was granted egress hosts) and runs under `strace`, so what it *tries*
is on record (spec 4.5: runtime syscall and network monitoring). /proc inside is the sandbox's own PID
namespace, so /proc/1/environ is the sandbox's cleared environment, not the host's. The trace is written outside
the sandbox, where the server cannot reach it; the discovery service turns it into
`tool_events` rows (monitor.py). No strace or no Bubblewrap means no server: an unmonitored
run is refused, never allowed."""
import ctypes
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("REVENUEOS_MCP_ROOT", "/var/lib/revenueos/mcp"))
TRACE_SET = "trace=execve,connect,open,openat,creat,mkdir,mkdirat,unlink,unlinkat,rename,renameat,renameat2"
LOCAL_PREFIXES = ("/opt/revenueos-mcp/", "/opt/mcpfinder/", "/src/infra/discovery/")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")

SECRET_PATHS = re.compile(
    r"(^/run/revenueos|^/run/secrets|/\.ssh/|/\.aws/|/\.gnupg/|/\.netrc$|/\.npmrc$|/\.pypirc$|/\.env$|"
    r"^/etc/shadow|keychain|pgpass|^/var/lib/revenueos/)")
WRITABLE = ("/workspace", "/tmp", "/dev/", "/proc/self/", "/proc/thread-self/")
_LINE = re.compile(r"^(\d+)\s+(\w+)\((.*)\)\s+=\s+(-?\d+|\?)(?:\s+(\w+))?")
_RESUMED = re.compile(r"^(\d+)\s+<\.\.\. (\w+) resumed>(.*)\)\s+=\s+(-?\d+|\?)(?:\s+(\w+))?")
_UNFINISHED = re.compile(r"^(\d+)\s+(\w+)\((.*) <unfinished \.\.\.>$")
_PATH = re.compile(r'"((?:[^"\\]|\\.)*)"')
_ADDR = re.compile(r'sa_family=(AF_INET6?),.*?(?:inet_addr\("([^"]+)"\)|inet_pton\(AF_INET6, "([^"]+)")')
_PORT = re.compile(r"htons\((\d+)\)")


def _calls(text: str):
    """Yield (syscall, args, result, errno) with unfinished/resumed pairs joined."""
    pending: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = _UNFINISHED.match(line)
        if m:
            pending[m.group(1)] = (m.group(2), m.group(3))
            continue
        m = _RESUMED.match(line)
        if m and m.group(1) in pending:
            name, head = pending.pop(m.group(1))
            yield name, head + m.group(3), m.group(4), m.group(5)
            continue
        m = _LINE.match(line)
        if m:
            yield m.group(2), m.group(3), m.group(4), m.group(5)


def analyze(text: str, payload: str) -> list[dict]:
    """Violations in a strace log, counted only from the moment the payload itself was exec'd
    (everything before that is Bubblewrap building the sandbox)."""
    out, seen, started = [], set(), False
    base = payload.rsplit("/", 1)[-1]
    for name, args, result, errno in _calls(text):
        if not started:
            if name == "execve" and result == "0":
                first = _PATH.search(args)
                if first and first.group(1).rsplit("/", 1)[-1] == base:
                    started = True
            continue
        failed = result.startswith("-")
        event = None
        if name == "connect":
            a = _ADDR.search(args)
            if a:
                ip = a.group(2) or a.group(3)
                if not (ip.startswith("127.") or ip in ("::1", "0.0.0.0")):
                    port = _PORT.search(args)
                    event = {"kind": "egress_blocked" if failed else "sandbox_escape",
                             "target": f"{ip}:{port.group(1) if port else '?'}"}
        else:
            paths = [p for p in _PATH.findall(args)]
            if not paths:
                continue
            path = paths[0] if name not in ("rename", "renameat", "renameat2") else paths[-1]
            if name == "execve":
                continue
            write = name in ("creat", "mkdir", "mkdirat", "unlink", "unlinkat", "rename", "renameat", "renameat2") \
                or bool(re.search(r"O_(WRONLY|RDWR|CREAT|TRUNC|APPEND)", args))
            if SECRET_PATHS.search(path):
                event = {"kind": "secret_read_blocked" if failed else "secret_read", "target": path}
            elif write and path.startswith("/") and not path.startswith(WRITABLE) \
                    and "__pycache__" not in path and not path.endswith(".pyc"):
                event = {"kind": "sandbox_write_blocked" if failed else "sandbox_escape", "target": path}
        if event:
            key = (event["kind"], event["target"])
            if key not in seen:
                seen.add(key)
                event["errno"] = errno
                event["syscall"] = name
                out.append(event)
    return out


def build_argv(name: str, argv: list[str], forward_env: dict[str, str], egress_dir: Path | None = None) -> tuple[list[str], Path]:
    from revenueos_sandbox.supervisor import SandboxUnavailable, bwrap_argv
    if not NAME_RE.match(name):
        raise ValueError(f"bad server name {name!r}")
    strace = shutil.which("strace")
    if not strace:
        raise SandboxUnavailable("strace is not installed: an unmonitored MCP server is refused")
    base = ROOT / name
    ws, trace = base / "ws", base / "trace"
    ws.mkdir(parents=True, exist_ok=True)
    trace.mkdir(parents=True, exist_ok=True)
    cmd = bwrap_argv(argv, ws, egress_dir)
    binds = []                # a server shipped in the image is visible read-only; nothing else of /opt or /src is
    for prefix in LOCAL_PREFIXES:
        top = prefix.rstrip("/")
        if any(a.startswith(prefix) for a in argv) and os.path.isdir(top):
            binds += ["--ro-bind", top, top]
    i = cmd.index("--remount-ro")
    cmd = cmd[:i] + binds + cmd[i:]
    i = cmd.index("--")
    extra = ["--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "npm_config_update_notifier", "false"]
    for k, v in forward_env.items():
        extra += ["--setenv", k, v]
    cmd = cmd[:i] + extra + cmd[i:]
    log = trace / f"{os.getpid()}.log"
    (trace / f"{os.getpid()}.payload").write_text(cmd[cmd.index("--") + 1])
    return [strace, "-f", "-qq", "-s", "256", "-e", TRACE_SET, "-o", str(log), *cmd], log


def _egress(name: str):
    """An identity-pinned egress session for this server, only when its own identity was granted
    hosts at install (ROOT/<name>/egress.json). Fails closed."""
    spec = ROOT / name / "egress.json"
    if not spec.exists():
        return None
    cfg = json.loads((ROOT / "sandbox-env.json").read_text())
    os.environ.update(cfg["env"])
    from revenueos_common import egress_identity
    from revenueos_common.db import Database
    from revenueos_common.secrets import KeychainStore, SecretResolver
    from revenueos_sandbox.egress import EgressSession
    from revenueos_sandbox.records import egress_hooks
    from revenueos_sandbox.tls import EgressCA
    secrets = SecretResolver(KeychainStore(cfg["env"]["REVENUEOS_KEYCHAIN_DIR"]))
    key = secrets.get(egress_identity.KEY_REF)
    if not key:
        raise RuntimeError("egress identity key unavailable (fail closed)")
    host, _, port = cfg["egress_proxy"].rpartition(":")
    opened, closed = egress_hooks(Database(actor="discovery"))
    return EgressSession(json.loads(spec.read_text())["agent_id"], "", key, (host, int(port)),
                         on_open=opened, on_close=closed, ca=EgressCA.from_vault(secrets))


def main() -> None:  # pragma: no cover - process entrypoint (exercised by tests/unit/test_mcp_sandbox.py)
    args = sys.argv[1:]
    if "--" not in args or not args:
        sys.exit("usage: revenueos-mcp-sandbox NAME [--env KEY]... -- COMMAND [ARGS...]")
    cut = args.index("--")
    name, opts, argv = args[0], args[1:cut], args[cut + 1:]
    keys = [opts[i + 1] for i in range(0, len(opts) - 1, 2) if opts[i] == "--env"]
    forward = {k: os.environ[k] for k in keys if k in os.environ}
    egress = _egress(name)
    cmd, _ = build_argv(name, argv, forward, egress.dir if egress else None)

    def pdeathsig():
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)   # PR_SET_PDEATHSIG

    proc = subprocess.Popen(cmd, env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")},
                            preexec_fn=pdeathsig)
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, lambda *_: proc.terminate())
    try:
        rc = proc.wait()
    finally:
        if egress:
            egress.close()
    sys.exit(rc if rc >= 0 else 128 - rc)


if __name__ == "__main__":  # pragma: no cover
    main()
