"""Sandbox supervisor (C03/C17): runs agent commands under Bubblewrap (INV-11, INV-12).

Every run gets:
  * a copy-on-write shadow of the workspace: the agent writes only to the shadow; the host
    workspace changes only through `commit`, which needs a consumed approval bound to the
    changeset hash;
  * no host mounts beyond read-only system directories (no home, no /var, no host workspace);
  * its own user, pid, net, ipc, uts and cgroup namespaces; no network except the per-session
    egress relay when one is given;
  * resource quotas: CPU seconds, address space, processes, file size, wall clock;
  * the destructive-pattern blocklist, checked before launch in every mode, YOLO included.

On macOS (developer machines) the same contract is approximated with Seatbelt
(`sandbox-exec`); production and CI use Bubblewrap.
"""
import hashlib
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from revenueos_common.canonical import args_hash

from . import blocklist
from .egress import EgressSession

RELAY = Path(__file__).with_name("relay.py")
SYSTEM_DIRS = ["/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32"]
ETC_FILES = ["/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ld.so.conf.d", "/etc/alternatives", "/etc/ssl",
             "/etc/ca-certificates", "/etc/localtime", "/etc/nsswitch.conf", "/etc/mime.types"]
SANDBOX_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Quotas:
    cpu_seconds: int = 60
    memory_mb: int = 1024
    pids: int = 256
    file_mb: int = 512
    wall_seconds: int = 120


@dataclass
class SandboxResult:
    status: str                      # ok | failed | blocked | timeout | killed
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None
    changeset: list[str] = field(default_factory=list)
    changes: dict[str, str] = field(default_factory=dict)   # path -> added | modified | deleted
    command_hash: str = ""
    changeset_hash: str | None = None
    shadow: Path | None = None
    backend: str = "bubblewrap"


def sha256_json(value) -> str:
    """sha256 of the RFC 8785 form: the same hash approvals are bound to (INV-06)."""
    return args_hash(value)


def _manifest(root: Path) -> dict[str, str]:
    """relative path -> content fingerprint (symlinks by target, files by sha256)."""
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                out[rel] = "link:" + os.readlink(p)
            elif stat.S_ISREG(st.st_mode):
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
                out[rel] = f"{stat.S_IMODE(st.st_mode):o}:{h.hexdigest()}"
    return out


def _diff(before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
    changes = {p: "added" for p in after.keys() - before.keys()}
    changes |= {p: "deleted" for p in before.keys() - after.keys()}
    changes |= {p: "modified" for p in before.keys() & after.keys() if before[p] != after[p]}
    return dict(sorted(changes.items()))


def _limits(q: Quotas) -> Callable[[], None]:
    def apply():
        resource.setrlimit(resource.RLIMIT_CPU, (q.cpu_seconds, q.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (q.memory_mb << 20, q.memory_mb << 20))
        # RLIMIT_NPROC is NOT set here: before the sandbox's user namespace exists it is counted
        # against the host uid, which every RevenueOS container shares, so a busy host made
        # bwrap fail with EAGAIN. It is applied inside the namespace instead (see _pid_cap).
        resource.setrlimit(resource.RLIMIT_FSIZE, (q.file_mb << 20, q.file_mb << 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def _pid_cap(argv: list[str], q: Quotas) -> list[str]:
    """Cap processes from inside the sandbox's own user namespace, where the kernel counts only
    the sandbox's tasks (per-namespace accounting), so the quota is exact and a fork bomb is
    contained whatever else the host uid is running. The sandbox has no capabilities, so the
    hard limit cannot be raised again."""
    return ["prlimit", f"--nproc={q.pids}:{q.pids}", "--", *argv]


def bwrap_argv(argv: list[str], shadow_ws: Path, egress_dir: Path | None) -> list[str]:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise SandboxUnavailable("bubblewrap (bwrap) is not installed")
    # --unshare-user is explicit so the agent is an unprivileged uid even when the supervisor is root.
    a = [bwrap, "--unshare-all", "--unshare-user", "--uid", "1000", "--gid", "1000", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL",
         "--hostname", "sandbox"]
    for d in SYSTEM_DIRS:
        if os.path.islink(d):
            a += ["--symlink", os.readlink(d), d]
        elif os.path.isdir(d):
            a += ["--ro-bind", d, d]
    for f in ETC_FILES:
        a += ["--ro-bind-try", f, f]
    prefix = os.path.realpath(sys.base_prefix)   # interpreter outside /usr (e.g. CI toolcache)
    if not any(prefix == d or prefix.startswith(d + "/") for d in SYSTEM_DIRS):
        a += ["--ro-bind", prefix, prefix]
    path = f"{prefix}/bin:{SANDBOX_PATH}"
    a += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
          "--bind", str(shadow_ws), "/workspace", "--chdir", "/workspace",
          "--setenv", "HOME", "/workspace", "--setenv", "PATH", path, "--setenv", "LANG", "C.UTF-8"]
    egress_mounts = ["--ro-bind", str(RELAY), "/run/revenueos/relay.py", "--bind", str(egress_dir),
                     "/run/revenueos/egress"] if egress_dir is not None else []
    # Root (bwrap's tmpfs holding the mount points) read-only: only /workspace and /tmp are writable.
    a += egress_mounts + ["--remount-ro", "/"]
    if egress_dir is not None:
        proxy = "http://127.0.0.1:3128"
        for k in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
            a += ["--setenv", k, proxy]
        if (egress_dir / "ca.pem").exists():   # trust only the egress CA: all TLS ends at the forwarder
            for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
                      "GIT_SSL_CAINFO"):   # git reads its own variable (Aegis: in-sandbox clones)
                a += ["--setenv", k, "/run/revenueos/egress/ca.pem"]
        a += ["--setenv", "NO_PROXY", "", "--setenv", "no_proxy", ""]
        a += ["--", "python3", "/run/revenueos/relay.py", "/run/revenueos/egress/egress.sock", *argv]
    else:
        a += ["--", *argv]
    return a


def seatbelt_profile(shadow_ws: Path, egress_sock: Path | None) -> str:
    """macOS developer backend: deny by default, write only the shadow, no network but the relay."""
    rules = ["(version 1)", "(deny default)", "(allow process*)", "(allow sysctl-read)", "(allow mach-lookup)",
             "(allow file-read*)",
             f'(allow file-write* (subpath "{shadow_ws}") (subpath "/private/tmp") (literal "/dev/null"))']
    if egress_sock is not None:
        rules.append(f'(allow network-outbound (remote unix-socket (path-literal "{egress_sock}")))')
    return "\n".join(rules)


def run_in_sandbox(argv: list[str], workspace: Path | str | None = None, *, yolo: bool = False,
                   agent_id: str | None = None, task_id: str | None = None, quotas: Quotas | None = None,
                   egress: EgressSession | None = None, env: dict[str, str] | None = None,
                   keep_shadow: bool = False, recorder=None) -> SandboxResult:
    """Run argv in a fresh sandbox. `yolo` skips approval prompts upstream; it never relaxes the
    blocklist, the namespaces, the quotas or the shadow workspace."""
    argv = [str(x) for x in argv]
    q = quotas or Quotas()
    command_hash = sha256_json(argv)
    session = recorder.start(agent_id, task_id, yolo, workspace, command_hash) if recorder else None

    reason = blocklist.check(argv)
    if reason:
        result = SandboxResult("blocked", None, reason=f"blocked by supervisor: {reason}", command_hash=command_hash)
        if recorder:
            recorder.finish(session, result)
        return result

    shadow = Path(tempfile.mkdtemp(prefix="rvos-shadow-"))
    shadow_ws = shadow / "ws"
    src = Path(workspace) if workspace else None
    if src is not None:
        shutil.copytree(src, shadow_ws, symlinks=True)
    else:
        shadow_ws.mkdir()
    before = _manifest(src) if src is not None else {}

    if sys.platform == "darwin":  # pragma: no cover - developer machines only
        cmd = ["sandbox-exec", "-p", seatbelt_profile(shadow_ws, egress.socket_path if egress else None), *argv]
        backend, cwd = "seatbelt", shadow_ws
    else:
        cmd = bwrap_argv(_pid_cap(argv, q), shadow_ws, egress.dir if egress else None)
        backend, cwd = "bubblewrap", None
    extra = []
    for k, v in (env or {}).items():
        if k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "PATH", "HOME", "LD_PRELOAD", "LD_LIBRARY_PATH",
                         "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
                         "GIT_SSL_CAINFO"}:
            raise ValueError(f"{k} is controlled by the supervisor")
        extra += ["--setenv", k, v]
    if extra and backend == "bubblewrap":
        i = cmd.index("--")
        cmd = cmd[:i] + extra + cmd[i:]

    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            preexec_fn=_limits(q), start_new_session=True, env={"PATH": SANDBOX_PATH})
    status, reason = None, None
    try:
        out, err = proc.communicate(timeout=q.wall_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        status, reason = "timeout", f"wall-clock quota of {q.wall_seconds}s exceeded"
    rc = proc.returncode
    if status is None:
        if rc < 0 or rc in (128 + signal.SIGKILL, 128 + signal.SIGXCPU, 128 + signal.SIGXFSZ):
            status, reason = "killed", "terminated by a resource quota or signal"
        else:
            status = "ok" if rc == 0 else "failed"

    changes = _diff(before, _manifest(shadow_ws))
    result = SandboxResult(status, None if status == "timeout" else rc,
                           out.decode(errors="replace"), err.decode(errors="replace"), reason,
                           changeset=list(changes), changes=changes, command_hash=command_hash,
                           changeset_hash=sha256_json(changes) if changes else None,
                           shadow=shadow_ws if keep_shadow else None, backend=backend)
    if recorder:
        recorder.finish(session, result)
    if not keep_shadow:
        shutil.rmtree(shadow, ignore_errors=True)
    return result


def commit(result: SandboxResult, workspace: Path | str, approved_changeset_hash: str) -> list[str]:
    """Apply a finished run's changeset to the real workspace. The caller must have consumed an
    approval bound to `result.changeset_hash` (the database enforces this for recorded sessions)."""
    if result.status != "ok" or result.shadow is None:
        raise PermissionError("only a successful run kept with keep_shadow=True can be committed")
    if not result.changeset_hash or approved_changeset_hash != result.changeset_hash:
        raise PermissionError("approval is not bound to this changeset")
    ws = Path(workspace).resolve()
    applied = []
    for rel, kind in result.changes.items():
        dst = (ws / rel)
        if not str(dst.resolve(strict=False)).startswith(str(ws) + os.sep):
            raise PermissionError(f"{rel} escapes the workspace")
        if kind == "deleted":
            dst.unlink(missing_ok=True)
        else:
            src = result.shadow / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_symlink():
                # A link is committed only if it is relative and stays inside the workspace
                # (source trees carry them); anything pointing out is an escape and is refused.
                target = os.readlink(src)
                landing = os.path.normpath(os.path.join(dst.parent, target))
                if os.path.isabs(target) or not (landing + os.sep).startswith(str(ws) + os.sep):
                    raise PermissionError(f"{rel}: symlink leaves the workspace")
                if dst.is_symlink() or dst.exists():
                    dst.unlink()
                os.symlink(target, dst)
                applied.append(rel)
                continue
            shutil.copy2(src, dst)
        applied.append(rel)
    return applied
