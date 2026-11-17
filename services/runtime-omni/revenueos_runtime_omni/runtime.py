"""Governed OmniPilot runtime (spec 3.1, 3.6).

OmniPilot (named, C02, pinned) provides the 41 desktop tools: shell, persistent Python, files,
apps, screen, GUI, clipboard, processes, notifications, web. Its own REST API only runs whole
LLM tasks, so RevenueOS drives the tool registry directly, one call at a time, through the
same path as every other tool call:

  orchestrator -> POST /v1/tools/{name}/invoke -> shared risk classification (3.2)
    -> critical: blocked (every mode)   -> high: hash-bound approval bound to task + tool
    -> OmniPilot tool runs on this container's desktop, its web traffic through the pinned
       egress proxy for that agent and task
    -> receipt in tool_calls (INV-02) + OTel span with task_id, agent_id, tool, risk_class

Calls are serialized: the desktop, clipboard and process environment are shared state.
"""
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from revenueos_risk import classify, decide

SERVER = "runtime-omni"
EXCLUDED = {"plugin.broken"}          # OmniPilot's own test plugin, not a runtime tool
OUTPUT_LIMIT = 60_000


class Blocked(PermissionError):
    pass


@dataclass
class Invocation:
    status: str                     # ok | error | blocked | approval_required
    risk_class: str
    reasons: list
    output: str = ""
    data: dict | None = None
    image_b64: str | None = None
    receipt_id: str | None = None
    latency_ms: int = 0


def build_registry():
    from omnipilot.tools.registry import ToolRegistry
    reg = ToolRegistry.build_default(include_plugins=False)
    for name in EXCLUDED & set(reg.names()):
        reg.unregister(name)
    return reg


class Runtime:
    def __init__(self, receipts, *, workdir: str, egress=None, tracer=None, registry=None):
        """receipts: revenueos_mcp_common.Receipts; egress: callable(agent, task) -> context
        manager yielding a proxy URL (or None for no network)."""
        self.receipts, self.workdir, self.egress, self.tracer = receipts, workdir, egress, tracer
        self.registry = registry or build_registry()
        self._lock = threading.Lock()
        self.takeover = None            # set by the app; .require_free() pauses the agent (spec 3.5)
        from omnipilot.config.settings import Settings
        self.settings = Settings()      # OmniPilot defaults; risk and approvals are ours, not its prompts
        self.settings.agent.workdir = workdir

    def tools(self) -> list[dict]:
        out = []
        for name in self.registry.names():
            t = self.registry.get(name)
            out.append({"name": name, "description": t.description, "base_risk": t.risk, "parameters": t.parameters})
        return out

    @contextmanager
    def _proxied(self, agent_id: str, task_id: str):
        if self.egress is None:
            yield
            return
        with self.egress(agent_id, task_id) as proxy:
            keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
            saved = {k: os.environ.get(k) for k in keys}
            url, ca = proxy
            for k in keys[:4]:
                os.environ[k] = url
            if ca:
                os.environ["SSL_CERT_FILE"] = os.environ["REQUESTS_CA_BUNDLE"] = ca
            try:
                yield
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    def invoke(self, name: str, args: dict, *, task_id: str, agent_id: str, approval_id: str | None = None,
               mode: str = "auto", trace_id: str | None = None) -> Invocation:
        tool = self.registry.get(name)
        if tool is None:
            raise KeyError(name)
        if self.takeover is not None:
            self.takeover.require_free()   # raises TakenOver -> 423: the human holds the desk
        risk = classify(name, args, declared=tool.risk, context="contained")
        action = decide(risk, mode)
        common = dict(task_id=task_id, agent_id=agent_id, server=SERVER, tool=name, args=args,
                      risk_class=risk.level, trace_id=trace_id)
        if action == "block":
            self.receipts.deny(reason="critical: " + "; ".join(risk.reasons), **common)
            return Invocation("blocked", risk.level, list(risk.reasons))
        if action == "prompt":
            try:
                from revenueos_mcp_common.receipts import ApprovalRequired
            except ImportError:   # pragma: no cover - mcp-common is installed in the runtime image
                ApprovalRequired = PermissionError
            try:
                # medium in "ask" mode is also a prompt: it needs the same hash-bound approval
                self.receipts.consume_approval(approval_id, args, "high", task_id=task_id, tool=name)
            except (ApprovalRequired, PermissionError) as e:
                self.receipts.deny(reason=str(e), **common)
                return Invocation("approval_required", risk.level, list(risk.reasons) + [str(e)])

        from omnipilot.tools.base import ToolContext
        with self._lock, self._proxied(agent_id, task_id):
            start = time.monotonic()
            try:
                result = tool.execute(ToolContext(settings=self.settings, cwd=self.workdir), dict(args))
            except Exception as e:   # a tool crash is a recorded error, never a silent drop
                from omnipilot.tools.base import ToolResult
                result = ToolResult.fail(f"{type(e).__name__}: {e}")
            latency = int((time.monotonic() - start) * 1000)
        output = (result.output or "")[:OUTPUT_LIMIT]
        verdict = "ok" if result.success else "error"
        receipt = self.receipts.write(result={"success": result.success, "output": output, "data": result.data},
                                      latency_ms=latency, cost=0, approval_id=approval_id if action == "prompt" else None,
                                      verdict=verdict, **common)
        image = getattr(result.image, "data", None) if result.image is not None else None
        return Invocation(verdict, risk.level, list(risk.reasons), output=output, data=result.data or {},
                          image_b64=image if isinstance(image, str) else None, receipt_id=receipt, latency_ms=latency)
