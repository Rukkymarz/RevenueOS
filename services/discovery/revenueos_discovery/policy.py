"""Selection policy engine (spec 4.5): docs/POLICY.md enforced in code, before activation.

Pure: a candidate goes in, a scored verdict comes out. Unknown is never a pass (D10's rule
applied to installs): a candidate whose license or maintenance cannot be established is denied,
not waved through."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "LGPL-2.1", "GPL-2.0",
                    "GPL-3.0", "AGPL-3.0", "PostgreSQL", "ISC", "in-repo"}
KNOWN_SOURCES = {"registry", "npm", "pypi", "smithery", "curated", "mcptoon", "mcpfinder", "manual", "pinned"}
# Launchers the installer will wrap in the sandbox. No docker (no socket is ever mounted), no shells.
ALLOWED_COMMANDS = {"npx", "node", "uvx", "uv", "python", "python3", "revenueos-mcp-test-server"}
LOCAL_PREFIXES = ("/opt/revenueos-mcp/", "/opt/mcpfinder/", "/src/infra/discovery/")
MAX_STALE_DAYS = 365
_SHELL_META = re.compile(r"[;&|`$<>\n]|\$\(")
_DANGEROUS_ARGS = ("--privileged", "--network=host", "--net=host", "docker.sock", "--cap-add", "--pid=host")
_LITERAL_SECRET = re.compile(r"(?i)(?:api[_-]?key|token|secret|password)=\S{8,}|\b(?:sk|ghp|xox[bp])[-_][A-Za-z0-9_-]{16,}")
_UNPINNED = re.compile(r"^(?:latest|next|\*|)$|^[\^~><]")


@dataclass
class PolicyResult:
    allowed: bool
    score: dict = field(default_factory=dict)     # check -> {"ok": bool, "detail": str}
    reasons: list[str] = field(default_factory=list)


def _days_since(value, now: datetime) -> int | None:
    if not value:
        return None
    try:
        d = value if isinstance(value, date) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if isinstance(d, datetime):
        d = d.date()
    return (now.date() - d).days


def evaluate(c: dict, *, now: datetime | None = None, allow_http_hosts: frozenset[str] = frozenset()) -> PolicyResult:
    now = now or datetime.now(timezone.utc)
    score: dict = {}

    def check(name: str, ok: bool, detail: str) -> None:
        score[name] = {"ok": bool(ok), "detail": detail}

    transport = c.get("transport")
    command, args, url = c.get("command"), [str(a) for a in c.get("args") or []], c.get("url")
    remote = transport in ("http", "sse", "streamable-http")

    lic = c.get("license")
    check("license", lic in ALLOWED_LICENSES, f"license {lic!r}" if lic else "license unknown")

    age = _days_since(c.get("last_push"), now)
    if c.get("archived"):
        check("maintenance", False, "repository is archived")
    elif age is None:
        check("maintenance", False, "last activity unknown")
    else:
        check("maintenance", age <= MAX_STALE_DAYS, f"last push {age} days ago (limit {MAX_STALE_DAYS})")

    check("mcp_wrapper", (transport == "stdio" and bool(command)) or (remote and bool(url)),
          f"transport {transport!r}")

    posture = []
    if remote and url:
        host = re.sub(r"^[a-z]+://", "", url).split("/")[0].split(":")[0]
        if not url.startswith("https://") and host not in allow_http_hosts:
            posture.append("remote endpoint is not https")
    if any(_LITERAL_SECRET.search(a) for a in args) or (url and _LITERAL_SECRET.search(url)):
        posture.append("a literal secret is embedded in the launch arguments")
    for k, v in (c.get("secrets") or {}).items():
        if not re.match(r"^(keychain|vault)://", str(v)):
            posture.append(f"secret {k} is not passed by reference")
    check("security_posture", not posture, "; ".join(posture) or "secrets by reference; transport acceptable")

    chain = []
    if c.get("source") not in KNOWN_SOURCES:
        chain.append(f"unknown source {c.get('source')!r}")
    if not remote:
        if _UNPINNED.search(str(c.get("version") or "")):
            chain.append("version is not pinned")
        if not re.match(r"^sha(256|512)[:-]\S{20,}$", str(c.get("checksum") or "")):
            chain.append("no checksum")
    prov = (c.get("provenance") or {}).get("status")
    if prov == "fail":
        chain.append("provenance check failed")
    check("supply_chain", not chain, "; ".join(chain) or "pinned, checksummed, known source")

    static = []
    if not remote and command:
        base = command.rsplit("/", 1)[-1]
        if "/" in command:
            if not command.startswith(LOCAL_PREFIXES):
                static.append(f"command path {command!r} is outside the installable prefixes")
        elif base not in ALLOWED_COMMANDS:
            static.append(f"launcher {base!r} is not allowed")
        if any(_SHELL_META.search(a) for a in args):
            static.append("shell metacharacters in arguments")
        if any(d in a for a in args for d in _DANGEROUS_ARGS):
            static.append("privilege-escalating argument")
    check("static_install", not static, "; ".join(static) or "launcher and arguments acceptable")

    check("runtime_monitoring", remote or bool(c.get("sandboxed", True)),
          "remote server: no local process" if remote else "runs in its own sandbox under syscall tracing")

    reasons = [f"{k}: {v['detail']}" for k, v in score.items() if not v["ok"]]
    return PolicyResult(not reasons, score, reasons)
