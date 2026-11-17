"""Aegis OS engine (C03, named — docs/PINS.md, config/sources.yaml): wires the real,
pinned `heurion-org/aegis-os` binary into the sandbox supervisor as an additional,
explicitly-selected `engine="aegis"` on `run_in_sandbox()` (default stays "bubblewrap",
our own tested path — see supervisor.py).

aegis-os's own `run` subcommand accepts an arbitrary trailing command
(`--trailing-var-arg`, not just the `claude`/`codex`/`agy`/`hermes`/`opencode` CLIs its
README leads with — confirmed from crates/aos-cli/src/main.rs), builds its own
Copy-on-Write shadow workspace under the project directory it is invoked from (cwd),
and runs the command inside its own kernel sandbox (Bubblewrap on Linux). It does
*not* write back to the host workspace itself — `aegis-os run` only ever touches its
own nested shadow; a separate, human-gated `aegis-os commit` promotes it. We do not
call that: RevenueOS already has its own Postgres-backed, approval-hash-bound commit
path (N13/N14, INV-06 — see supervisor.commit()), and routing the actual host write
through a second, un-audited mechanism would be the worse design. Instead we ask
`aegis-os diff --json` for the nested shadow's path and hand that to our own
manifest-diff/commit machinery exactly as if it were our own shadow_ws — aegis-os
supplies the kernel-sandboxed execution and CoW; we keep the single, policy-gated
write path.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


class AegisUnavailable(RuntimeError):
    pass


def binary() -> str | None:
    """Path to the real, pinned `aegis-os` binary, or None if this image wasn't built with it
    (e.g. a non-Linux developer machine, or AEGIS_OS_BIN explicitly unset in a minimal image)."""
    return shutil.which("aegis-os")


def run_argv(argv: list[str], *, profile: str = "code", enforcement: str = "enforced") -> list[str]:
    """`aegis-os run` argv. `cmd` is a trailing var-arg (confirmed from aos-cli's clap definition:
    `#[arg(trailing_var_arg = true, allow_hyphen_values = true, required = true)]`) — it runs
    whatever is given, not only the named coding-agent CLIs its README leads with."""
    bin_path = binary()
    if not bin_path:
        raise AegisUnavailable("aegis-os binary is not installed in this image")
    if enforcement not in ("advisory", "enforced"):
        raise ValueError(f"unknown enforcement level: {enforcement!r}")
    return [bin_path, "run", "--mode", "implement", "--profile", profile,
            "--enforcement", enforcement, "--", *argv]


def diff_argv() -> list[str]:
    bin_path = binary()
    if not bin_path:
        raise AegisUnavailable("aegis-os binary is not installed in this image")
    return [bin_path, "diff", "--json"]


@dataclass(frozen=True)
class SessionDiff:
    session_id: str
    session_dir: Path
    workspace: Path
    shadow: Path
    changed_count: int
    evidence_hash: str


def parse_diff(stdout: str) -> SessionDiff | None:
    """Parse `aegis-os diff --json`'s output (confirmed shape from aos-cli's `diff()`:
    session_id, session_dir, workspace, shadow, changed_count, evidence_hash, raw_diff_hash,
    pinned_commit_command, evidence). Returns None when the run made no session (nothing to
    diff) — aegis-os prints a plain "No sessions under ..." line to stderr, not JSON, in that
    case, so a JSON parse failure with empty/whitespace stdout is treated as "no session",
    while a malformed-but-nonempty stdout is a real error and is raised."""
    text = stdout.strip()
    if not text:
        return None
    data = json.loads(text)
    return SessionDiff(
        session_id=data["session_id"],
        session_dir=Path(data["session_dir"]),
        workspace=Path(data["workspace"]),
        shadow=Path(data["shadow"]),
        changed_count=int(data["changed_count"]),
        evidence_hash=data["evidence_hash"],
    )
