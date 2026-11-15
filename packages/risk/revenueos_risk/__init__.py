"""Risk classification shared by every runtime (spec 3.2): OmniPilot, NAVA, the sandbox
supervisor and the approval path all classify through `classify` and act through `decide`, so a
tool call gets the same answer wherever it runs.

Levels: low < medium < high < critical. A call's level is the highest of
  * the tool's declared base risk,
  * OmniPilot's argument-aware danger patterns (shell, Python, files, processes, GUI, web),
  * the RevenueOS destructive-command blocklist (critical).

Context: "host" (a person's own machine, OmniPilot's default view) or "contained" (an isolated
RevenueOS runtime or sandbox: no host mounts, egress only through the pinned proxy). In a
contained runtime, running code is the job, so the code-execution tools start at medium instead
of high; their arguments still escalate them (rm -rf / stays critical, system paths stay high).

Actions (`decide`):
  critical -> block, in every mode including YOLO (spec 3.2, INV-12);
  high     -> prompt: a hash-bound human approval in every mode (INV-06 outranks YOLO);
  medium   -> prompt in "ask" mode, auto in "auto" and "yolo";
  low      -> auto.
"""
import re
from dataclasses import dataclass

from . import blocklist

LEVELS = ("low", "medium", "high", "critical")
MODES = ("ask", "auto", "yolo")
_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
SHELL_TOOLS = {"shell.run_command", "sandbox.run", "terminal.run"}
CONTAINED_BASE = {"shell.run_command": "medium", "python.run_python": "medium", "processes.kill_process": "medium",
                  "sandbox.run": "medium", "terminal.run": "medium"}
CONTEXTS = ("host", "contained")
# Reasons that only describe the tool itself; inside a contained runtime they do not raise risk.
CONTAINED_GENERIC = {"killing a process"}
SYSTEM_WRITE = re.compile(r"(>>?|\btee\b(\s+-a)?|\bsed\s+-i\S*\s+\S+)\s*/(etc|usr|bin|sbin|lib\w*|boot|sys|proc|root|var/lib)\b")


@dataclass(frozen=True)
class Risk:
    level: str
    reasons: tuple[str, ...] = ()

    @property
    def critical(self) -> bool:
        return self.level == "critical"


def _max(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def _command_of(tool: str, args: dict) -> str | None:
    if tool == "sandbox.run":
        argv = args.get("argv") or []
        return " ".join(str(a) for a in argv) if isinstance(argv, list) else str(argv)
    if tool in SHELL_TOOLS:
        return str(args.get("command", ""))
    return None


def classify(tool: str, args: dict | None = None, declared: str = "low", context: str = "host") -> Risk:
    if declared not in _RANK:
        raise ValueError(f"unknown risk level {declared!r}")
    if context not in CONTEXTS:
        raise ValueError(f"unknown context {context!r}")
    if context == "contained" and tool in CONTAINED_BASE:
        declared = CONTAINED_BASE[tool]
    args = args or {}
    level, reasons = declared, [f"declared {declared}"] if declared != "low" else []

    from omnipilot.permission import danger   # OmniPilot (named): argument-aware patterns
    omni_tool = "shell.run_command" if tool in SHELL_TOOLS else tool
    omni_args = {**args, "command": _command_of(tool, args)} if tool in SHELL_TOOLS else args
    a = danger.assess(omni_tool, omni_args)
    dynamic = "critical" if a.critical else a.level
    if (context == "contained" and tool in CONTAINED_BASE and dynamic == "high"
            and set(a.reasons) <= CONTAINED_GENERIC):
        dynamic = "medium"   # only generic to the tool (or its base), nothing in the arguments
    level = _max(level, dynamic)
    reasons += [r for r in a.reasons if r not in reasons]

    command = _command_of(tool, args)
    if command is not None and SYSTEM_WRITE.search(command):
        level = _max(level, "high")
        reasons.append("writes into a system path")
    if command is not None:
        hit = (blocklist.check([str(x) for x in args.get("argv")]) if tool == "sandbox.run" and isinstance(args.get("argv"), list)
               else blocklist.check_command(command))
        if hit:
            level = "critical"
            reasons.append(f"blocklist: {hit}")
    if tool == "python.run_python":
        for line in str(args.get("code", "")).splitlines():
            if "os.system(" in line or "subprocess" in line:
                inner = line.split("(", 1)[-1].strip("()'\" ")
                hit = blocklist.check_command(inner)
                if hit:
                    level, reasons = "critical", reasons + [f"blocklist: {hit}"]
    return Risk(level, tuple(reasons))


def decide(risk: Risk, mode: str = "auto") -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if risk.level == "critical":
        return "block"
    if risk.level == "high":
        return "prompt"
    if risk.level == "medium":
        return "prompt" if mode == "ask" else "auto"
    return "auto"


__all__ = ["LEVELS", "MODES", "CONTEXTS", "Risk", "classify", "decide", "blocklist"]
