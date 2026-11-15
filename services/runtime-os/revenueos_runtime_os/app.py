"""HTTP surface of runtime-os (NAVA, C03). Every route authenticates the calling agent with its
bearer token (`nava_...`, digests in nava_tokens); the agent is never taken from the body.

POST /v1/syscalls                 {task_id, tool, args, mode?, approval_id?, expect?, timeout_s?}
GET  /v1/syscalls/{id}            the call and its 12 step records (own calls only)
GET  /v1/tools                    the tool table
POST /v1/bus/send                 {to, channel, body, task_id?}
GET  /v1/bus/inbox?after=N        own inbox only
POST /v1/memory                   {tier, key, value, task_id?, source_syscall?, source_evidence?}
GET  /v1/memory?tier=&key=&task_id=
POST /v1/subagents                {objective, ttl_s?, denies?}  -> {agent_id, name, token}
POST /v1/plans                    {task_id, objective, steps:[{tool, args, max_attempts?}]}
GET  /v1/plans/{id}
POST /v1/plans/{id}/{run|pause|resume|retry}   {mode?, approvals?: {idx: approval_id}}
"""
import os
import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.db import Database, DatabaseError
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check

from . import COMPONENT, SERVICE

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
db = Database(actor=SERVICE)
_state: dict = {}
OMNI_TOKEN_REF = "keychain://runtime-omni-token"


def kernel():
    if "k" not in _state:
        from revenueos_mcp_common.receipts import Receipts

        from .kernel import Kernel
        from .nava import Gateway, Workspaces
        from .tools import OmniClient, builtin_tools, omni_tools
        tools = builtin_tools()
        omni_url = os.environ.get("RUNTIME_OMNI_URL")
        if omni_url:
            secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
            try:
                tools.update(omni_tools(OmniClient(omni_url, secrets.get(OMNI_TOKEN_REF))))
            except OSError:
                pass   # runtime-omni not up yet: built-ins only; retried on the next cold start
        tracer = None
        try:
            from revenueos_mcp_common.telemetry import setup_tracing
            tracer = setup_tracing(SERVICE)
        except Exception:  # noqa: BLE001 - tracing is best-effort; receipts are the record
            pass
        root = os.environ.get("REVENUEOS_WORKSPACE_ROOT", "/var/lib/revenueos/workspaces")
        ws = Workspaces(root, os.environ.get("NAVA_SNAPSHOT_ROOT", os.path.join(root, ".nava-snapshots")))
        gw = Gateway(db, Receipts(db), tools, ws, tracer=tracer)
        _state["k"] = Kernel(db, gw)
    return _state["k"]


async def _caller(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    k = await run_in_threadpool(kernel)
    return k, await run_in_threadpool(k.authenticate, token)


def _deny():
    return JSONResponse({"error": "unauthenticated"}, status_code=401)


def _bad(msg):
    return JSONResponse({"error": msg}, status_code=400)


async def _body(request: Request) -> dict:
    try:
        b = await request.json()
    except ValueError:
        return {}
    return b if isinstance(b, dict) else {}


def _db_error(e: DatabaseError):
    return JSONResponse({"error": e.message}, status_code=403 if re.match(r"N\d\d|INV-", e.message) else 400)


async def syscall(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    b = await _body(request)
    task, tool, args = b.get("task_id", ""), b.get("tool"), b.get("args", {})
    if not UUID.match(str(task)) or not isinstance(tool, str):
        return _bad("task_id (uuid) and tool are required")
    try:
        r = await run_in_threadpool(lambda: k.gw.syscall(
            caller_agent=me, agent_id=me, task_id=task, tool=tool, args=args, mode=b.get("mode", "auto"),
            approval_id=b.get("approval_id"), expect=b.get("expect") or [], timeout_s=int(b.get("timeout_s", 30)),
            trace_id=request.headers.get("traceparent")))
    except DatabaseError as e:
        return _db_error(e)
    except (TypeError, ValueError) as e:
        return _bad(str(e))
    code = {"committed": 200, "rolled_back": 409, "failed": 422, "denied": 403}.get(r.status, 500)
    if r.approval_id:
        code = 202
    return JSONResponse(r.as_dict(), status_code=code)


async def syscall_get(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    sid = request.path_params["id"]
    if not UUID.match(sid):
        return _bad("bad id")
    row = await run_in_threadpool(db.one, "SELECT * FROM syscalls WHERE id = $id::uuid AND agent_id = $a::uuid",
                                  id=sid, a=me)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    row["steps"] = await run_in_threadpool(db.rows, "SELECT step, name, outcome, detail, at FROM syscall_steps "
                                           "WHERE syscall_id = $id::uuid ORDER BY step", id=sid)
    return JSONResponse(row)


async def tools(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    return JSONResponse({"tools": [{"name": t.name, "risk": t.risk, "mutating": t.mutating, "schema": t.schema,
                                    "delegated": t.delegated} for t in k.gw.tools.values()]})


async def bus_send(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    b = await _body(request)
    if not UUID.match(str(b.get("to", ""))) or not isinstance(b.get("body"), dict):
        return _bad("to (uuid) and body (object) are required")
    try:
        seq = await run_in_threadpool(k.send, me, b["to"], str(b.get("channel", "default")), b["body"], b.get("task_id"))
    except DatabaseError as e:
        return _db_error(e)
    return JSONResponse({"seq": seq})


async def bus_inbox(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    try:
        after, limit = int(request.query_params.get("after", 0)), int(request.query_params.get("limit", 100))
    except ValueError:
        return _bad("after and limit must be integers")
    return JSONResponse({"messages": await run_in_threadpool(k.inbox, me, after, limit)})


async def memory(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    if request.method == "GET":
        q = request.query_params
        return JSONResponse({"items": await run_in_threadpool(k.recall, me, q.get("tier"), q.get("key"), q.get("task_id"))})
    b = await _body(request)
    try:
        mid = await run_in_threadpool(k.remember, me, b.get("tier", ""), str(b.get("key", "")), b.get("value"),
                                      b.get("task_id"), b.get("source_syscall"), b.get("source_evidence"))
    except ValueError as e:
        return _bad(str(e))
    except DatabaseError as e:
        return _db_error(e)
    return JSONResponse({"id": mid})


async def subagents(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    b = await _body(request)
    if not b.get("objective"):
        return _bad("objective is required")
    try:
        out = await run_in_threadpool(k.spawn, me, str(b["objective"]), int(b.get("ttl_s", 3600)), b.get("denies") or [])
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except DatabaseError as e:
        return _db_error(e)
    return JSONResponse(out)


async def plans(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    b = await _body(request)
    steps = b.get("steps")
    if not UUID.match(str(b.get("task_id", ""))) or not isinstance(steps, list) or not steps:
        return _bad("task_id and a non-empty steps list are required")
    try:
        pid = await run_in_threadpool(k.plan_create, me, b["task_id"], str(b.get("objective", "")), steps)
    except (DatabaseError, KeyError) as e:
        return _bad(getattr(e, "message", str(e)))
    return JSONResponse({"id": pid})


async def plan_get(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    p = await run_in_threadpool(k.plan, request.path_params["id"]) if UUID.match(request.path_params["id"]) else None
    if not p or p["agent_id"] != me:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(p)


async def plan_action(request: Request):
    k, me = await _caller(request)
    if not me:
        return _deny()
    pid, action = request.path_params["id"], request.path_params["action"]
    p = await run_in_threadpool(k.plan, pid) if UUID.match(pid) else None
    if not p or p["agent_id"] != me:
        return JSONResponse({"error": "not found"}, status_code=404)
    b = await _body(request)
    mode, approvals = b.get("mode", "auto"), b.get("approvals") or {}
    if action == "pause":
        await run_in_threadpool(k.plan_set, pid, "paused")
        return JSONResponse(await run_in_threadpool(k.plan, pid))
    if action == "resume":
        await run_in_threadpool(k.plan_set, pid, "running")
        return JSONResponse(await run_in_threadpool(k.plan_run, pid, me, mode, approvals))
    if action == "run":
        return JSONResponse(await run_in_threadpool(k.plan_run, pid, me, mode, approvals))
    if action == "retry":
        return JSONResponse(await run_in_threadpool(k.plan_retry, pid, me, mode, approvals))
    return JSONResponse({"error": "unknown action"}, status_code=404)


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT),
                         "kernel": "nava", "steps": 12})


_checks = {"component_map": config_loaded}
if os.environ.get("PGHOST"):               # in compose; unit tests run the app without a database
    _checks["postgres"] = postgres_check(db)

app = create_app(SERVICE, checks=_checks, routes=[
    Route("/v1/info", info),
    Route("/v1/syscalls", syscall, methods=["POST"]),
    Route("/v1/syscalls/{id}", syscall_get),
    Route("/v1/tools", tools),
    Route("/v1/bus/send", bus_send, methods=["POST"]),
    Route("/v1/bus/inbox", bus_inbox),
    Route("/v1/memory", memory, methods=["GET", "POST"]),
    Route("/v1/subagents", subagents, methods=["POST"]),
    Route("/v1/plans", plans, methods=["POST"]),
    Route("/v1/plans/{id}", plan_get),
    Route("/v1/plans/{id}/{action}", plan_action, methods=["POST"]),
])
