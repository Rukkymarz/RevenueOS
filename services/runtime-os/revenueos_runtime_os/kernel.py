"""NAVA kernel services around the syscall gateway: agent credentials, the A2A message bus,
four-tier memory, JIT subagents and durable plans (OpenMuse pause / resume / retry)."""
from __future__ import annotations

import hashlib
import secrets as _secrets

TIERS = ("working", "episodic", "semantic", "procedural")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Kernel:
    def __init__(self, db, gateway):
        self.db, self.gw = db, gateway

    # ---- credentials (step 2) --------------------------------------------------------------
    def issue_token(self, agent_id: str, ttl_s: int | None = None) -> str:
        token = "nava_" + _secrets.token_urlsafe(32)
        self.db.scalar("INSERT INTO nava_tokens(digest, agent_id, expires_at) VALUES ($d, $a::uuid, "
                       "CASE WHEN $ttl = '' THEN NULL ELSE now() + make_interval(secs => $ttl::int) END) RETURNING digest",
                       d=digest(token), a=agent_id, ttl="" if ttl_s is None else str(int(ttl_s)))
        return token

    def authenticate(self, token: str | None) -> str | None:
        if not token or not token.startswith("nava_"):
            return None
        return self.db.scalar("SELECT nava_authenticate($d) AS a", d=digest(token))

    # ---- A2A bus (N18, N19) ----------------------------------------------------------------
    def send(self, sender: str, to: str, channel: str, body: dict, task_id: str | None = None) -> int:
        return int(self.db.scalar("SELECT a2a_send($f::uuid, $t::uuid, $c, #b, nullif($task,'')::uuid) AS s",
                                  f=sender, t=to, c=channel, b=body, task=task_id or ""))

    def inbox(self, agent: str, after: int = 0, limit: int = 100) -> list[dict]:
        return self.db.rows("SELECT seq, channel, from_agent, task_id, body, sent_at FROM a2a_receive($a::uuid, "
                            "$after::bigint, $lim::int)", a=agent, after=int(after), lim=int(limit))

    # ---- memory (N20) ----------------------------------------------------------------------
    def remember(self, agent: str, tier: str, key: str, value, task_id: str | None = None,
                 source_syscall: str | None = None, source_evidence: str | None = None) -> str:
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        return self.db.scalar(
            "INSERT INTO nava_memory(agent_id, tier, task_id, key, value, source_syscall, source_evidence) "
            "VALUES ($a::uuid, $tier::memory_tier, nullif($t,'')::uuid, $k, #v, nullif($s,'')::uuid, nullif($e,'')::uuid) "
            "RETURNING id", a=agent, tier=tier, t=task_id or "", k=key, v=value, s=source_syscall or "",
            e=source_evidence or "")

    def recall(self, agent: str, tier: str | None = None, key: str | None = None, task_id: str | None = None,
               limit: int = 50) -> list[dict]:
        """Own memory, plus a subagent reads its parent's semantic and procedural memory."""
        return self.db.rows(
            """SELECT id, agent_id, tier, task_id, key, value, source_syscall, source_evidence, created_at
                 FROM nava_memory m
                WHERE (m.agent_id = $a::uuid OR (m.tier IN ('semantic','procedural') AND m.agent_id =
                       (SELECT parent_agent_id FROM nava_subagents WHERE agent_id = $a::uuid)))
                  AND ($tier = '' OR m.tier = $tier::memory_tier)
                  AND ($k = '' OR m.key = $k)
                  AND ($t = '' OR m.task_id = $t::uuid)
                ORDER BY m.created_at DESC LIMIT $lim::int""",
            a=agent, tier=tier or "", k=key or "", t=task_id or "", lim=min(int(limit), 500))

    # ---- JIT subagents (N21) ---------------------------------------------------------------
    def spawn(self, parent: str, objective: str, ttl_s: int = 3600, denies: list[str] | None = None) -> dict:
        p = self.db.one("SELECT name, role, framework, status FROM agents WHERE id = $p::uuid", p=parent)
        if not p or p["status"] != "active":
            raise PermissionError("parent agent is not active")
        if self.db.scalar("SELECT 1 AS x FROM nava_subagents WHERE agent_id = $p::uuid", p=parent):
            raise PermissionError("subagents do not spawn subagents")
        name = f"{p['name']}.jit-{_secrets.token_hex(4)}"
        child = self.db.scalar(
            "INSERT INTO agents(name, role, framework, budget_monthly) VALUES ($n, $r, 'nava-jit', 0) RETURNING id",
            n=name, r=f"subagent of {p['role']}")
        self.db.scalar("INSERT INTO nava_subagents(agent_id, parent_agent_id, objective, expires_at) VALUES "
                       "($c::uuid, $p::uuid, $o, now() + make_interval(secs => $ttl::int)) RETURNING agent_id",
                       c=child, p=parent, o=objective[:2000], ttl=int(ttl_s))
        for pat in denies or []:
            self.db.scalar("INSERT INTO nava_denies(agent_id, tool_pattern) VALUES ($c::uuid, $p) RETURNING agent_id",
                           c=child, p=pat)
        return {"agent_id": child, "name": name, "token": self.issue_token(child, ttl_s)}

    # ---- durable plans (OpenMuse) ----------------------------------------------------------
    def plan_create(self, agent: str, task_id: str, objective: str, steps: list[dict]) -> str:
        pid = self.db.scalar("INSERT INTO plans(agent_id, task_id, objective) VALUES ($a::uuid, $t::uuid, $o) "
                             "RETURNING id", a=agent, t=task_id, o=objective)
        for i, s in enumerate(steps):
            self.db.scalar("INSERT INTO plan_steps(plan_id, idx, tool, args, expect, max_attempts) VALUES "
                           "($p::uuid, $i::int, $tool, #args, #expect, $m::int) RETURNING idx",
                           p=pid, i=i, tool=s["tool"], args=s.get("args", {}), expect=s.get("expect", []),
                           m=int(s.get("max_attempts", 3)))
        return pid

    def plan(self, pid: str) -> dict:
        p = self.db.one("SELECT * FROM plans WHERE id = $p::uuid", p=pid)
        if p:
            p["steps"] = self.db.rows("SELECT idx, tool, args, expect, status, attempts, max_attempts, syscall_id, "
                                      "output FROM plan_steps WHERE plan_id = $p::uuid ORDER BY idx", p=pid)
        return p

    def plan_set(self, pid: str, status: str) -> None:
        self.db.scalar("UPDATE plans SET status = $s::plan_status, updated_at = now() WHERE id = $p::uuid RETURNING id",
                       p=pid, s=status)

    def plan_run(self, pid: str, caller: str, mode: str = "auto", approvals: dict | None = None) -> dict:
        """Run pending steps in order through the gateway. Stops at a failed step (status
        `failed`, retry with plan_retry), at an approval request, or when the plan is paused.
        Each step's syscall is recorded, so a restart resumes at the first pending step."""
        approvals = approvals or {}
        while True:
            p = self.plan(pid)
            if p is None:
                raise KeyError(pid)
            if p["status"] != "running":
                return p
            pending = [s for s in p["steps"] if s["status"] != "done"]
            if not pending:
                self.plan_set(pid, "completed")
                return self.plan(pid)
            s = pending[0]
            if s["status"] == "failed":
                self.plan_set(pid, "failed")
                return self.plan(pid)
            r = self.gw.syscall(caller_agent=caller, agent_id=p["agent_id"], task_id=p["task_id"], tool=s["tool"],
                                args=s["args"], mode=mode, approval_id=approvals.get(str(s["idx"])),
                                expect=s.get("expect") or [])
            waiting = bool(r.approval_id)          # asked a human: not an attempt
            attempts = int(s["attempts"]) + (0 if waiting else 1)
            done = r.status == "committed"
            status = "done" if done else ("pending" if waiting or attempts < int(s["max_attempts"]) else "failed")
            self.db.scalar("UPDATE plan_steps SET status = $st, attempts = $n::int, syscall_id = $sid::uuid, "
                           "output = #out WHERE plan_id = $p::uuid AND idx = $i::int RETURNING idx",
                           st=status, n=attempts, sid=r.id, out={"status": r.status, "reason": r.reason,
                                                                  "approval_id": r.approval_id},
                           p=pid, i=int(s["idx"]))
            if waiting:                  # pause; resume with the approval id once a human decides
                self.plan_set(pid, "paused")
                return self.plan(pid)
            if not done and status == "failed":
                self.plan_set(pid, "failed")
                return self.plan(pid)

    def plan_retry(self, pid: str, caller: str, mode: str = "auto", approvals: dict | None = None) -> dict:
        self.db.scalar("UPDATE plan_steps SET status = 'pending', attempts = 0 WHERE plan_id = $p::uuid "
                       "AND status = 'failed' RETURNING idx", p=pid)
        self.plan_set(pid, "running")
        return self.plan_run(pid, caller, mode, approvals)
