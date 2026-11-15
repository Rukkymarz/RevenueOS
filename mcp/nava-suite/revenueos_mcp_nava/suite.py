"""NAVA's 15 specialized MCP servers (spec 3.3).

Each server is a narrow MCP surface over one capability domain. None of them executes
anything itself: every tool forwards to the NAVA gateway (runtime-os POST /v1/syscalls),
where the 12-step managed syscall — classification, policy, approvals, quotas, locks,
snapshot/rollback, receipt — happens exactly once (spec 3.2: classification is
single-sourced, so the MCP layer declares `low` and NAVA is the enforcement point;
approval ids are passed through untouched).

The caller is the agent named in the MCP envelope. Its NAVA bearer token is read by
reference from the keychain (`keychain://nava-agent-<agent_id>`, written by
`revenueos-runtime-os issue-token`); the gateway then authenticates the agent itself,
so a facade bug cannot escalate one agent into another's capabilities.
"""
import json
import os
import urllib.error
import urllib.request

from pydantic import BaseModel, Field

from revenueos_mcp_common import create_server

RUNTIME_OS = os.environ.get("RUNTIME_OS_URL", "http://runtime-os:8103")

# domain -> (syscall tool prefix or fixed tools, description)
DOMAINS = {
    "files":     ["fs.read", "fs.write", "fs.list", "fs.delete"],
    "terminal":  ["sandbox.run"],                      # the OpenMuse isolated terminal (30 s cap)
    "python":    ["omni.python.run_python"],
    "processes": ["omni.processes.list_processes", "omni.processes.kill_process"],
    "system":    ["omni.system.get_system_info", "omni.system.get_environment_variable", "omni.system.list_drives"],
    "screen":    ["omni.screen.screenshot", "omni.screen.get_screen_size", "omni.screen.locate_image"],
    "gui":       ["omni.gui.move_mouse", "omni.gui.click", "omni.gui.double_click", "omni.gui.right_click",
                  "omni.gui.drag", "omni.gui.scroll", "omni.gui.type_text", "omni.gui.press_key", "omni.gui.hotkey"],
    "clipboard": ["omni.clipboard.get_clipboard", "omni.clipboard.set_clipboard"],
    "apps":      ["omni.apps.list_applications", "omni.apps.open_application", "omni.apps.close_application",
                  "omni.apps.open_file"],
    "notify":    ["omni.notify.send_notification"],
    "web":       ["omni.web.fetch_url", "omni.web.http_request", "omni.web.download_file", "omni.web.search_web"],
    "browser":   ["omni.browser.open_url"],
    "memory":    [],                                   # kernel surfaces, not syscalls
    "bus":       [],
    "plans":     [],
}
TERMINAL_LIMIT_S = 30                                  # spec 3.5: isolated terminal, 30-second commands


class SyscallArgs(BaseModel):
    args: dict = Field(default_factory=dict)
    mode: str = "auto"
    expect: list = Field(default_factory=list)


def _agent_token(secrets, agent_id: str) -> str:
    token = secrets.get(f"keychain://nava-agent-{agent_id}")
    if not token:
        raise PermissionError(f"no NAVA token provisioned for agent {agent_id} "
                              "(run: revenueos-runtime-os issue-token <agent_id>)")
    return token


def _post(path: str, body: dict, token: str, timeout: int = 330) -> dict:
    req = urllib.request.Request(RUNTIME_OS + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {"status": "failed", "reason": f"runtime-os HTTP {e.code}"}


def _get(path: str, token: str) -> dict:
    req = urllib.request.Request(RUNTIME_OS + path, headers={"authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _syscall(secrets, ctx, tool: str, payload: dict, approval_id=None) -> dict:
    body = {"task_id": ctx["task_id"], "tool": tool, "args": payload.get("args", {}),
            "mode": payload.get("mode", "auto"), "expect": payload.get("expect", [])}
    if approval_id:
        body["approval_id"] = approval_id
    out = _post("/v1/syscalls", body, _agent_token(secrets, ctx["agent_id"]))
    if out.get("status") not in ("committed",):
        # surface the gateway verdict (denied / rolled_back / failed / approval pending) verbatim
        return {"status": out.get("status"), "reason": out.get("reason"), "step": out.get("step"),
                "approval_id": out.get("approval_id"), "risk_class": out.get("risk_class")}
    return {"status": "committed", "output": out.get("output"), "receipt_id": out.get("receipt_id"),
            "syscall_id": out.get("id")}


def build(domain: str, *, db=None, secrets=None, token_ref: str | None = None):
    """Build one of the 15 servers. Its MCP name is nava-<domain>."""
    if domain not in DOMAINS:
        raise KeyError(f"unknown NAVA domain {domain!r}; one of {sorted(DOMAINS)}")
    server = create_server(f"nava-{domain}", db=db, secrets=secrets,
                           token_ref=token_ref or os.environ.get("NAVA_MCP_TOKEN_REF",
                                                                 f"keychain://mcp-nava-{domain}-token"))
    secrets = server.secrets

    for tool in DOMAINS[domain]:
        short = tool.split(".")[-1]

        def make(tool=tool):
            def handler(args: dict, ctx: dict) -> dict:
                payload = SyscallArgs.model_validate(args).model_dump()
                if tool == "sandbox.run":   # OpenMuse terminal: hard 30 s, workspace only, no host mounts
                    a = dict(payload["args"])
                    a["timeout_s"] = min(int(a.get("timeout_s", TERMINAL_LIMIT_S)), TERMINAL_LIMIT_S)
                    payload["args"] = a
                return _syscall(secrets, ctx, tool, payload, approval_id=args.get("approval_id"))
            handler.__doc__ = f"Run the governed NAVA syscall {tool} (12-step gateway, receipted)."
            return handler

        server.tool(short, risk_class="low", args_model=SyscallArgs)(make())

    if domain == "memory":
        class RememberArgs(BaseModel):
            tier: str
            key: str
            value: dict = Field(default_factory=dict)
            task_id: str | None = None
            source_syscall: str | None = None

        @server.tool("remember", risk_class="low", args_model=RememberArgs)
        def remember(args: dict, ctx: dict) -> dict:
            return _post("/v1/memory", args, _agent_token(secrets, ctx["agent_id"]))

        @server.tool("recall", risk_class="low")
        def recall(args: dict, ctx: dict) -> dict:
            q = "&".join(f"{k}={v}" for k, v in args.items() if k in ("tier", "key", "task_id") and v)
            return _get(f"/v1/memory?{q}", _agent_token(secrets, ctx["agent_id"]))

    if domain == "bus":
        class SendArgs(BaseModel):
            to: str
            channel: str = "default"
            body: dict = Field(default_factory=dict)
            task_id: str | None = None

        @server.tool("send", risk_class="low", args_model=SendArgs)
        def send(args: dict, ctx: dict) -> dict:
            return _post("/v1/bus/send", args, _agent_token(secrets, ctx["agent_id"]))

        @server.tool("inbox", risk_class="low")
        def inbox(args: dict, ctx: dict) -> dict:
            return _get(f"/v1/bus/inbox?after={int(args.get('after', 0))}", _agent_token(secrets, ctx["agent_id"]))

    if domain == "plans":
        class PlanArgs(BaseModel):
            task_id: str
            objective: str = ""
            steps: list

        @server.tool("create", risk_class="low", args_model=PlanArgs)
        def create(args: dict, ctx: dict) -> dict:
            return _post("/v1/plans", args, _agent_token(secrets, ctx["agent_id"]))

        for action in ("run", "pause", "resume", "retry"):
            def make_action(action=action):
                def act(args: dict, ctx: dict) -> dict:
                    return _post(f"/v1/plans/{args['plan_id']}/{action}",
                                 {k: v for k, v in args.items() if k in ("mode", "approvals")},
                                 _agent_token(secrets, ctx["agent_id"]))
                act.__doc__ = f"{action} a durable plan (OpenMuse pause/resume/retry)."
                return act
            server.tool(action, risk_class="low")(make_action())

        @server.tool("status", risk_class="low")
        def status(args: dict, ctx: dict) -> dict:
            return _get(f"/v1/plans/{args['plan_id']}", _agent_token(secrets, ctx["agent_id"]))

    return server


def main() -> None:  # pragma: no cover - process entrypoint
    import sys

    import uvicorn
    domain = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NAVA_MCP_DOMAIN", "all")
    app = build_all() if domain == "all" else build(domain).http_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8400)))


def build_all():
    """All 15 servers in one Starlette app, each mounted at /<domain>/ with its own bearer token
    and its own receipts; one process for the whole suite (compose service nava-mcp)."""
    import contextlib

    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    servers = {d: build(d) for d in DOMAINS}
    apps = {d: s.http_app() for d, s in servers.items()}

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with contextlib.AsyncExitStack() as stack:
            for d, sub in apps.items():
                await stack.enter_async_context(sub.router.lifespan_context(sub))
            yield

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"service": "nava-mcp", "status": "ok", "count": len(apps),
                             "servers": {d: sorted(servers[d].tools) for d in sorted(apps)}})

    return Starlette(routes=[Route("/health", health),
                             *[Mount(f"/{d}", app=a) for d, a in apps.items()]], lifespan=lifespan)
