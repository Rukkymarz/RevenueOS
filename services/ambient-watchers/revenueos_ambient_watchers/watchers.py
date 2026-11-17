"""ambient-watchers (C02, specialist): native — RevenueOS's own component, not an external pin.

Spec role: a background watcher over ambient agent/desktop state. Rather than watching pixels,
this watches the signals NAVA already makes durable in Postgres — subagents about to be killed
by their TTL, approvals about to expire unused, and syscalls stuck in `running` past a staleness
threshold (candidates for `Gateway.reap()`). Each finding is pushed to the owning agent's A2A
inbox (so the agent gets a chance to react before the hard cutoff) and logged into semantic
memory with provenance, so the ambient state has a durable trail even before a dedicated
timeline writer exists.

Phase 11 (C12, `tares`) will give RevenueOS a real timeline/insight store on the `timeline` bus
(`timeline.event` contract). Until then, `nava_memory` (tier=semantic) is the honest substitute —
it is already real, tested infrastructure, not a stub. When Phase 11 lands, `_log()` below is the
one place to repoint at the tares writer.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass

from revenueos_common.db import Database

WATCHER_CHANNEL = "ambient.alert"


@dataclass(frozen=True)
class Finding:
    kind: str                 # "subagent_expiring" | "approval_expiring" | "syscall_stuck"
    agent_id: str             # the agent this finding is about / should be told about
    task_id: str | None
    detail: dict

    def body(self) -> dict:
        return {"kind": self.kind, **self.detail}


class AmbientWatchers:
    """Stateless scanner: every call re-derives findings from current DB state, so a crashed
    or restarted watcher loop loses nothing — there is no in-process state to lose (mirrors the
    NAVA gateway's own crash-recovery philosophy, N13/N14)."""

    def __init__(self, db: Database, *, self_agent_id: str,
                 subagent_warn_s: int = 60, approval_warn_s: int = 60, syscall_stale_s: int = 300):
        self.db = db
        self.self_agent_id = self_agent_id
        self.subagent_warn_s = subagent_warn_s
        self.approval_warn_s = approval_warn_s
        self.syscall_stale_s = syscall_stale_s

    # ---- individual scans ------------------------------------------------------------------
    def _expiring_subagents(self) -> list[Finding]:
        rows = self.db.rows(
            "SELECT agent_id, parent_agent_id, objective, "
            "extract(epoch FROM (expires_at - now()))::int AS seconds_left "
            "FROM nava_subagents "
            "WHERE expires_at > now() AND expires_at <= now() + make_interval(secs => $w::int)",
            w=self.subagent_warn_s)
        return [Finding("subagent_expiring", r["parent_agent_id"], None,
                         {"subagent_id": r["agent_id"], "objective": r["objective"],
                          "seconds_left": r["seconds_left"]})
                for r in rows]

    def _expiring_approvals(self) -> list[Finding]:
        rows = self.db.rows(
            "SELECT id, task_id, requested_by, "
            "extract(epoch FROM (expires_at - now()))::int AS seconds_left "
            "FROM approvals "
            "WHERE status = 'pending' AND expires_at > now() "
            "AND expires_at <= now() + make_interval(secs => $w::int)",
            w=self.approval_warn_s)
        out = []
        for r in rows:
            # requested_by is stored as "agent:<uuid>" (see Gateway._request_approval); anything
            # else (a human reviewer id, say) has no agent inbox to notify — skip, don't crash.
            who = r["requested_by"]
            if not who.startswith("agent:"):
                continue
            out.append(Finding("approval_expiring", who.removeprefix("agent:"), r["task_id"],
                                {"approval_id": r["id"], "seconds_left": r["seconds_left"]}))
        return out

    def _stuck_syscalls(self) -> list[Finding]:
        rows = self.db.rows(
            "SELECT id, agent_id, task_id, tool, "
            "extract(epoch FROM (now() - started_at))::int AS running_for "
            "FROM syscalls "
            "WHERE status = 'running' AND started_at <= now() - make_interval(secs => $s::int)",
            s=self.syscall_stale_s)
        return [Finding("syscall_stuck", r["agent_id"], r["task_id"],
                         {"syscall_id": r["id"], "tool": r["tool"], "running_for": r["running_for"]})
                for r in rows]

    def scan(self) -> list[Finding]:
        return self._expiring_subagents() + self._expiring_approvals() + self._stuck_syscalls()

    # ---- emit --------------------------------------------------------------------------------
    def _log(self, finding: Finding) -> None:
        """Durable trail for the finding. Stands in for the Phase 11 tares timeline writer
        (see module docstring) using memory tiers that already exist and are tested.
        `episodic` (a timestamped observation, no learned-rule claim) is the correct tier here —
        unlike `semantic`/`procedural` it carries no provenance requirement, which fits: a scan
        finding is not derived from a syscall receipt or submitted evidence."""
        self.db.scalar(
            "INSERT INTO nava_memory(tier, agent_id, task_id, key, value) "
            "VALUES ('episodic', $a::uuid, nullif($t,'')::uuid, $k, #v) "
            "RETURNING id",
            a=self.self_agent_id, t=finding.task_id or "",
            k=f"ambient.{finding.kind}", v=finding.body())

    def emit(self, finding: Finding) -> int:
        self._log(finding)
        return int(self.db.scalar(
            "SELECT a2a_send($f::uuid, $t::uuid, $c, #b, nullif($task,'')::uuid) AS s",
            f=self.self_agent_id, t=finding.agent_id, c=WATCHER_CHANNEL,
            b=finding.body(), task=finding.task_id or ""))

    def scan_and_emit(self) -> list[Finding]:
        findings = self.scan()
        for f in findings:
            self.emit(f)
        return findings


def ensure_registered(db: Database, *, budget_monthly: float = 0) -> str:
    """Idempotent: ambient-watchers needs its own row in `agents` to send/receive A2A mail and
    to own its memory rows, same pattern as the 7 static agents
    (see runtime_os.agents.provision_static_agents). Returns the agent id."""
    row = db.one("SELECT id FROM agents WHERE name = 'ambient-watchers'")
    if row:
        return row["id"]
    return db.scalar(
        "INSERT INTO agents(name, role, framework, budget_monthly) "
        "VALUES ('ambient-watchers', 'watcher', 'nava-static', $b::numeric) RETURNING id",
        b=budget_monthly)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="revenueos-ambient-watchers")
    p.add_argument("--interval", type=float, default=30.0, help="seconds between scans")
    p.add_argument("--once", action="store_true", help="scan once, print findings as JSON, exit")
    args = p.parse_args(argv)

    db = Database(actor="ambient-watchers")
    agent_id = ensure_registered(db)
    watchers = AmbientWatchers(db, self_agent_id=agent_id)

    if args.once:
        findings = watchers.scan_and_emit()
        print(json.dumps([f.body() | {"agent_id": f.agent_id} for f in findings]))
        return 0

    while True:  # pragma: no cover - long-running loop; --once is the tested, scriptable path
        watchers.scan_and_emit()
        time.sleep(args.interval)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
