"""HTTP surface of runtime-omni (spec 3.1, 3.6): OmniPilot's 41 tools by remote control.

GET  /v1/tools                      tool list with base risk and parameters
POST /v1/tools/{name}/invoke        {task_id, agent_id, args, approval_id?, mode?, traceparent?}
"""
import hmac
import os
import re
import subprocess

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.db import Database
from revenueos_common.registry import components_for, config_loaded
from revenueos_common.secrets import KeychainStore, SecretResolver
from revenueos_common.service import create_app, postgres_check

from . import COMPONENT, SERVICE
from .runtime import SERVER

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
        from .openmuse import Browser, Takeover
        _state["takeover"] = Takeover(display=os.environ.get("DISPLAY", ":1"))
        _state["rt"].takeover = _state["takeover"]
        _state["browser"] = Browser(db, egress, os.environ.get("RUNTIME_WORKDIR", "/workspace"),
                                    display=os.environ.get("DISPLAY", ":1"),
                                    executable=os.environ.get("OPENMUSE_CHROMIUM", "/usr/bin/chromium"))
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
    syscall = request.headers.get("x-nava-syscall")
    if syscall:
        # a NAVA-delegated call must match a live syscall that has passed snapshot (0003: nava_delegation)
        if not UUID.match(syscall):
            return JSONResponse({"error": "x-nava-syscall must be a UUID"}, status_code=400)
        from revenueos_mcp_common.receipts import args_hash as _h
        ok = await run_in_threadpool(
            lambda: db.scalar("SELECT nava_delegation($s::uuid, $a::uuid, $t::uuid, $tool, $h) IS NOT NULL AS ok",
                              s=syscall, a=agent, t=task, tool=name, h=_h(args)))
        if not ok:
            return JSONResponse({"error": "no live NAVA syscall matches this delegated call"}, status_code=403)

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
    from .openmuse import TakenOver
    try:
        res = go() if name in MAIN_THREAD_TOOLS else await run_in_threadpool(go)
    except TakenOver as e:
        return JSONResponse({"status": "paused", "error": str(e)}, status_code=423)
    code = {"ok": 200, "error": 200, "blocked": 403, "approval_required": 403}[res.status]
    return JSONResponse(res.__dict__, status_code=code)


async def takeover(request: Request) -> JSONResponse:
    """The human takeover console (spec 3.5). action: attach | type | key | release | status.
    While attached, every agent tool call is refused with 423 and the human drives the same
    desktop over loopback VNC or the typing channel; release resumes the agent."""
    if not await run_in_threadpool(_authorized, request):
        return JSONResponse({"error": "missing or invalid bearer token"}, status_code=401)
    rt = await run_in_threadpool(runtime)
    t = _state["takeover"]
    action = request.path_params["action"]
    if request.method == "GET" or action == "status":
        return JSONResponse(t.status())
    body = await request.json()
    holder = str(body.get("holder", "")) or "human"
    try:
        if action == "attach":
            out = t.attach(holder)
        elif action == "type":
            out = await run_in_threadpool(t.type_text, holder, str(body.get("text", "")))
        elif action == "key":
            out = await run_in_threadpool(t.key, holder, str(body.get("key", "Return")))
        elif action == "release":
            out = t.release(holder)
        else:
            return JSONResponse({"error": "unknown action"}, status_code=404)
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=403)
    except (ValueError, subprocess.CalledProcessError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    await run_in_threadpool(
        db.scalar, "SELECT audit_append($who, $act, 'runtime-omni/desk', #payload) IS NULL AS done",
        who=f"human:{holder}", act=f"takeover.{action}", payload={"status": out})
    return JSONResponse(out)


async def openmuse_browser(request: Request) -> JSONResponse:
    """OpenMuse persistent browser: open/goto/fill/click/text/download/close, per-agent profile,
    identity-pinned egress, receipted as openmuse.browser.<action> (same ledger as every tool)."""
    if not await run_in_threadpool(_authorized, request):
        return JSONResponse({"error": "missing or invalid bearer token"}, status_code=401)
    from .openmuse import BROWSER_TOOLS, TakenOver
    action = request.path_params["action"]
    if action not in BROWSER_TOOLS:
        return JSONResponse({"error": f"unknown action {action}"}, status_code=404)
    body = await request.json()
    task, agent = str(body.get("task_id", "")), str(body.get("agent_id", ""))
    if not UUID.match(task) or not UUID.match(agent):
        return JSONResponse({"error": "task_id and agent_id must be UUIDs"}, status_code=400)
    rt = await run_in_threadpool(runtime)
    browser = _state["browser"]
    method, required = BROWSER_TOOLS[action]
    missing = [k for k in required if k not in body and k != "task_id"]
    if missing:
        return JSONResponse({"error": f"missing argument(s) {missing}"}, status_code=400)
    tool_name = f"openmuse.browser.{action}"
    args = {k: v for k, v in body.items() if k not in ("agent_id", "approval_id", "traceparent")}

    def go():
        import time as _t
        from revenueos_risk import classify, decide
        _state["takeover"].require_free()
        risk = classify(tool_name, args, declared="medium" if action in ("fill", "click", "download") else "low",
                        context="contained")
        decision = decide(risk, body.get("mode", "auto"))
        approval = body.get("approval_id")
        if decision == "block":
            rt.receipts.deny(task_id=task, agent_id=agent, server=SERVER, tool=tool_name, args=args,
                             risk_class=risk.level, reason="; ".join(risk.reasons) or "critical", trace_id=None)
            return 403, {"status": "blocked", "risk_class": risk.level, "reasons": list(risk.reasons)}
        if decision == "prompt":
            try:
                from revenueos_mcp_common.receipts import ApprovalRequired
                rt.receipts.consume_approval(approval, args, "high", task_id=task, tool=tool_name)
            except (ApprovalRequired, PermissionError) as e:
                rt.receipts.deny(task_id=task, agent_id=agent, server=SERVER, tool=tool_name, args=args,
                                 risk_class=risk.level, reason=str(e), trace_id=None)
                return 403, {"status": "approval_required", "risk_class": risk.level, "error": str(e)}
        else:
            approval = None
        start = _t.monotonic()
        kwargs = {k: body[k] for k in required if k in body}
        try:
            out = getattr(browser, method)(agent, **kwargs)
            verdict = "ok"
        except (KeyError, PermissionError) as e:
            return 403, {"status": "denied", "error": str(e)}
        except Exception as e:  # recorded failure
            out, verdict = {"error": f"{type(e).__name__}: {e}"}, "error"
        receipt = rt.receipts.write(task_id=task, agent_id=agent, server=SERVER, tool=tool_name, args=args,
                                    result=out, latency_ms=int((_t.monotonic() - start) * 1000), cost=0,
                                    risk_class=risk.level, approval_id=approval, verdict=verdict, trace_id=None)
        return (200 if verdict == "ok" else 422), {"status": verdict, "receipt_id": receipt, **out}

    try:
        code, out = await run_in_threadpool(go)
    except TakenOver as e:
        return JSONResponse({"status": "paused", "error": str(e)}, status_code=423)
    return JSONResponse(out, status_code=code)


async def openmuse_pipeline(request: Request) -> JSONResponse:
    """Acceptance 3.1, unattended: signup via the agent's Phase 2 identity, OTP from its own
    inbox, PDF download, nib fill, deterministic review, reply draft in its Drafts mailbox."""
    if not await run_in_threadpool(_authorized, request):
        return JSONResponse({"error": "missing or invalid bearer token"}, status_code=401)
    body = await request.json()
    task, agent = str(body.get("task_id", "")), str(body.get("agent_id", ""))
    if not UUID.match(task) or not UUID.match(agent):
        return JSONResponse({"error": "task_id and agent_id must be UUIDs"}, status_code=400)
    rt = await run_in_threadpool(runtime)

    def go():
        import time as _t
        from revenueos_common.secrets import KeychainStore, SecretResolver

        from .openmuse import TakenOver
        from .pipeline import run_signup_pipeline
        _state["takeover"].require_free()
        ident = db.one("SELECT address, meta FROM agent_identities WHERE agent_id = $a::uuid AND kind = 'email' "
                       "AND status = 'active' ORDER BY created_at DESC LIMIT 1", a=agent)
        if not ident:
            return 403, {"status": "denied", "error": "agent has no email identity (INV-09)"}
        meta = ident.get("meta") or {}
        secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
        pw_ref = meta.get("password_ref")
        password = secrets.get(pw_ref) if pw_ref else None
        if not password:
            return 403, {"status": "denied", "error": "mailbox password reference unavailable (fail closed)"}
        login = meta.get("login") or ident["address"].split("@", 1)[0]
        start = _t.monotonic()
        res = run_signup_pipeline(_state["browser"], agent, task,
                                  email_addr=ident["address"], login=login, password=password,
                                  signup_url=str(body.get("signup_url", "http://signup-test:8090")).rstrip("/"),
                                  imap_host=os.environ.get("ALLMAIL_SELFHOSTED_IMAP_HOST", "stalwart"),
                                  workdir=os.environ.get("RUNTIME_WORKDIR", "/workspace"))
        receipt = rt.receipts.write(task_id=task, agent_id=agent, server=SERVER, tool="openmuse.pipeline.signup",
                                    args={"signup_url": body.get("signup_url", "http://signup-test:8090")},
                                    result={"status": res.status, "stages": [s["stage"] for s in res.stages],
                                            "review": res.review, "reason": res.reason},
                                    latency_ms=int((_t.monotonic() - start) * 1000), cost=0, risk_class="medium",
                                    approval_id=None, verdict="ok" if res.status == "completed" else "error",
                                    trace_id=None)
        out = {"status": res.status, "stages": res.stages, "filled_pdf": res.filled_pdf, "review": res.review,
               "draft_uid": res.draft_uid, "reason": res.reason, "receipt_id": receipt, "login": login}
        return (200 if res.status == "completed" else 422), out

    from .openmuse import TakenOver
    try:
        code, out = await run_in_threadpool(go)
    except TakenOver as e:
        return JSONResponse({"status": "paused", "error": str(e)}, status_code=423)
    return JSONResponse(out, status_code=code)


# Postgres is checked wherever the service is deployed with one (compose sets PGHOST).
checks = {"component_map": config_loaded, **({"postgres": postgres_check(db)} if os.environ.get("PGHOST") else {})}
app = create_app(SERVICE, checks=checks,
                 routes=[Route("/v1/info", info), Route("/v1/tools", tools),
                         Route("/v1/tools/{name}/invoke", invoke, methods=["POST"]),
                         Route("/v1/takeover/{action}", takeover, methods=["GET", "POST"]),
                         Route("/v1/openmuse/browser/{action}", openmuse_browser, methods=["POST"]),
                         Route("/v1/openmuse/pipeline/signup", openmuse_pipeline, methods=["POST"])])
