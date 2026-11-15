"""HTTP surface of runtime-omni (spec 3.1, 3.6): OmniPilot's 41 tools by remote control.

GET  /v1/tools                      tool list with base risk and parameters
POST /v1/tools/{name}/invoke        {task_id, agent_id, args, approval_id?, mode?, traceparent?}
"""
import hmac
import os
import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.db import Database
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check

from . import COMPONENT, SERVICE

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
db = Database(actor=SERVICE)
_state: dict = {}


def runtime():
    """Built on first use (imports OmniPilot, mcp-common and the keychain)."""
    if "rt" not in _state:
        from revenueos_mcp_common.receipts import Receipts
        from revenueos_mcp_common.telemetry import setup_tracing

        from .egress import proxy_address, session_factory
        from .runtime import Runtime
        secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
        egress = session_factory(db, secrets, proxy_address()) if os.environ.get("EGRESS_PROXY") else None
        _state["rt"] = Runtime(Receipts(db), workdir=os.environ.get("RUNTIME_WORKDIR", "/workspace"), egress=egress,
                               tracer=setup_tracing(SERVICE))
    return _state["rt"]


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT),
                         "runtime": "omnipilot", "display": os.environ.get("DISPLAY")})


async def tools(_: Request) -> JSONResponse:
    rt = await run_in_threadpool(runtime)
    return JSONResponse({"count": len(rt.registry), "tools": rt.tools()})


TOKEN_REF = "keychain://runtime-omni-token"
MAIN_THREAD_TOOLS = {"python.run_python"}


def _authorized(request: Request) -> bool:
    """Bearer token from the keychain (same pattern as the MCP servers); missing token = closed."""
    secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
    want = secrets.get(TOKEN_REF)
    got = request.headers.get("authorization", "")
    return bool(want) and hmac.compare_digest(got.encode(), f"Bearer {want}".encode())


async def invoke(request: Request) -> JSONResponse:
    if not await run_in_threadpool(_authorized, request):
        return JSONResponse({"error": "missing or invalid bearer token"}, status_code=401)
    name = request.path_params["name"]
    body = await request.json()
    task, agent = str(body.get("task_id", "")), str(body.get("agent_id", ""))
    args = body.get("args") or {}
    if not UUID.match(task) or not UUID.match(agent) or not isinstance(args, dict):
        return JSONResponse({"error": "task_id and agent_id must be UUIDs; args an object"}, status_code=400)
    mode = body.get("mode", "auto")
    if mode not in ("ask", "auto", "yolo"):
        return JSONResponse({"error": "mode must be ask, auto or yolo"}, status_code=400)
    rt = await run_in_threadpool(runtime)
    if rt.registry.get(name) is None:
        return JSONResponse({"error": f"unknown tool {name}"}, status_code=404)

    def go():
        from opentelemetry import trace
        from revenueos_mcp_common.telemetry import extract_context, standard_attributes
        tracer = rt.tracer or trace.get_tracer(SERVICE)
        with tracer.start_as_current_span(f"runtime-omni/{name}", context=extract_context(body.get("traceparent"))) as span:
            res = rt.invoke(name, args, task_id=task, agent_id=agent, approval_id=body.get("approval_id"), mode=mode,
                            trace_id=format(span.get_span_context().trace_id, "032x"))
            for k, v in standard_attributes(task, agent, name, res.risk_class).items():
                span.set_attribute(k, v)
            return res

    # OmniPilot's Python tool arms a SIGALRM watchdog, which works only on the main thread, so it
    # runs on the event-loop (main) thread; every other tool runs on a worker thread.
    res = go() if name in MAIN_THREAD_TOOLS else await run_in_threadpool(go)
    code = {"ok": 200, "error": 200, "blocked": 403, "approval_required": 403}[res.status]
    return JSONResponse(res.__dict__, status_code=code)


# Postgres is checked wherever the service is deployed with one (compose sets PGHOST).
checks = {"component_map": config_loaded, **({"postgres": postgres_check(db)} if os.environ.get("PGHOST") else {})}
app = create_app(SERVICE, checks=checks,
                 routes=[Route("/v1/info", info), Route("/v1/tools", tools),
                         Route("/v1/tools/{name}/invoke", invoke, methods=["POST"])])
