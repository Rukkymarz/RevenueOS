"""NAVA's seven static agents (spec 3.3), implemented as deterministic plan compilers.

Each static agent is a real `agents` row fenced by capability denies (N04): the deny set is the
complement of its domain, so a CodingAgent cannot press GUI buttons and a ReviewerAgent cannot
write files — the database refuses it at step 3 whatever the agent's code does. Objectives
compile to durable plans (OpenMuse), and every step runs as a managed syscall through the same
gateway, so the agents inherit policy, approvals, quotas, locks, rollback and receipts without
any code of their own. There is no LLM in this layer by design: plans are deterministic
functions of the objective's parameters, which is what makes them verifiable and replayable.

JIT subagents (Kernel.spawn) are the dynamic counterpart: synthesized per objective, fenced at
least as tightly as their parent, and mortal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Tool families the deny fences are built from. A family not in an agent's `allow` list is
# denied outright; `allow` entries are families (prefix match) the agent keeps.
FAMILIES = ["fs.read", "fs.list", "fs.write", "fs.delete", "sandbox.*",
            "omni.fs.*", "omni.shell.*", "omni.python.*", "omni.processes.*", "omni.system.*",
            "omni.screen.*", "omni.gui.*", "omni.clipboard.*", "omni.apps.*", "omni.notify.*",
            "omni.web.*", "omni.browser.*"]


@dataclass(frozen=True)
class StaticAgent:
    name: str
    role: str
    allow: tuple                                      # families this agent keeps
    compile: Callable[[dict], list] = field(repr=False, default=None)

    @property
    def denies(self) -> list[str]:
        return [f for f in FAMILIES if f not in self.allow]


def _coding_plan(p: dict) -> list:
    """params: files: {path: content}, workspace, check: argv to prove the change (tests)."""
    steps = [{"tool": "fs.write", "args": {"workspace": p["workspace"], "path": path, "content": content}}
             for path, content in sorted(p.get("files", {}).items())]
    if p.get("check"):
        steps.append({"tool": "sandbox.run", "args": {"workspace": p["workspace"], "argv": list(p["check"])}})
    return steps


def _terminal_plan(p: dict) -> list:
    """params: workspace, commands: [argv, ...] — each capped at the OpenMuse 30 s terminal limit."""
    return [{"tool": "sandbox.run",
             "args": {"workspace": p["workspace"], "argv": list(argv),
                      "timeout_s": min(int(p.get("timeout_s", 30)), 30)}}
            for argv in p["commands"]]


def _reviewer_plan(p: dict) -> list:
    """params: workspace, paths. Read-only: the fence (no fs.write/delete, no shell) is the point."""
    return [{"tool": "fs.read", "args": {"workspace": p["workspace"], "path": path}} for path in p["paths"]]


def _verifier_plan(p: dict) -> list:
    """params: workspace, checks: [{argv, expect?}] — commands with postconditions (step 11)."""
    return [{"tool": "sandbox.run", "args": {"workspace": p["workspace"], "argv": list(c["argv"])},
             "expect": c.get("expect", [{"exit_code": 0}])} for c in p["checks"]]


def _scraper_plan(p: dict) -> list:
    return [{"tool": "omni.web.fetch_url", "args": {"url": u}} for u in p["urls"]]


def _browser_plan(p: dict) -> list:
    return [{"tool": "omni.browser.open_url", "args": {"url": u}} for u in p["urls"]]


def _computer_plan(p: dict) -> list:
    steps = [{"tool": "omni.screen.screenshot", "args": {"attach": False}}]
    for text in p.get("type_texts", []):
        steps.append({"tool": "omni.gui.type_text", "args": {"text": text}})
    if p.get("notify"):
        steps.append({"tool": "omni.notify.send_notification", "args": {"message": p["notify"], "title": "NAVA"}})
    return steps


STATIC_AGENTS = {a.name: a for a in [
    StaticAgent("CodingAgent",     "coder",    ("fs.read", "fs.list", "fs.write", "fs.delete", "sandbox.*"), _coding_plan),
    StaticAgent("TerminalAgent",   "terminal", ("sandbox.*",), _terminal_plan),
    StaticAgent("ReviewerAgent",   "reviewer", ("fs.read", "fs.list"), _reviewer_plan),
    StaticAgent("VerifierAgent",   "verifier", ("fs.read", "fs.list", "sandbox.*"), _verifier_plan),
    StaticAgent("WebScraperAgent", "scraper",  ("fs.read", "fs.list", "fs.write", "omni.web.*"), _scraper_plan),
    StaticAgent("BrowserAgent",    "browser",  ("fs.read", "fs.list", "fs.write", "omni.web.*", "omni.browser.*"), _browser_plan),
    StaticAgent("ComputerAgent",   "computer", ("omni.screen.*", "omni.gui.*", "omni.clipboard.*", "omni.apps.*",
                                                "omni.notify.*"), _computer_plan),
]}


def provision_static_agents(kernel, budget_monthly: float = 50.0) -> dict[str, str]:
    """Idempotent: create each missing static agent with its deny fence. Returns name -> agent id.
    Email/calendar/browser identities come from the Phase 2 provisioner (revenueos-identity)."""
    out = {}
    for a in STATIC_AGENTS.values():
        row = kernel.db.one("SELECT id FROM agents WHERE name = $n", n=a.name)
        if row:
            out[a.name] = row["id"]
            continue
        aid = kernel.db.scalar("INSERT INTO agents(name, role, framework, budget_monthly) "
                               "VALUES ($n, $r, 'nava-static', $b::numeric) RETURNING id",
                               n=a.name, r=a.role, b=budget_monthly)
        for pat in a.denies:
            kernel.db.scalar("INSERT INTO nava_denies(agent_id, tool_pattern) VALUES ($a::uuid, $p) RETURNING agent_id",
                             a=aid, p=pat)
        out[a.name] = aid
    return out


def run_objective(kernel, agent_name: str, agent_id: str, task_id: str, objective: str, params: dict,
                  mode: str = "auto", approvals: dict | None = None) -> dict:
    """Compile the objective to a durable plan and run it through the gateway."""
    spec = STATIC_AGENTS[agent_name]
    steps = spec.compile(params)
    if not steps:
        raise ValueError(f"{agent_name}: objective compiled to an empty plan")
    pid = kernel.plan_create(agent_id, task_id, objective, steps)
    return kernel.plan_run(pid, agent_id, mode=mode, approvals=approvals or {})
