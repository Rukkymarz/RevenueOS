"""MCP server scaffolding. Every RevenueOS MCP server is built with create_server();
CI fails if any server imports the MCP SDK directly (tests/connectivity/test_mcp_boundary.py).

Each tool call goes through, in order: bearer auth (transport), envelope contract
validation, rate limit, OTel span with the four standard attributes, approval
consumption for high/critical risk, argument validation, the handler, and the
receipt. Any failure after the span starts still writes a receipt with an
error verdict, then raises: no silent failures.
"""
import hmac
import os
import re
import time
from typing import Any, Callable

from fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from revenueos_common.db import Database
from revenueos_common.secrets import SecretResolver

from .ratelimit import TokenBucket
from .receipts import Receipts
from .telemetry import extract_context, setup_tracing, standard_attributes
from .validation import validate_envelope

RISK_CLASSES = ("low", "medium", "high", "critical")
TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class _BearerAuth(BaseHTTPMiddleware):
    def __init__(self, app, token_getter: Callable[[], str | None]):
        super().__init__(app)
        self.token_getter = token_getter

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        expected = self.token_getter()
        got = request.headers.get("authorization", "")
        if not expected or not hmac.compare_digest(got, f"Bearer {expected}"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


class RevenueOSMcpServer:
    def __init__(self, name: str, *, db: Database, secrets: SecretResolver, token_ref: str,
                 rate_per_s: float = 5.0, burst: int = 20):
        self.name = name
        self.db = db
        self.secrets = secrets
        self.token_ref = token_ref
        self.mcp = FastMCP(name)
        self.receipts = Receipts(db)
        self.bucket = TokenBucket(rate_per_s, burst)
        self.tracer = setup_tracing(name)
        self.tools: dict[str, str] = {}

    def tool(self, name: str, *, risk_class: str, args_model: type[BaseModel] | None = None, cost: float = 0.0):
        if risk_class not in RISK_CLASSES:
            raise ValueError(f"unknown risk class {risk_class}")
        if not TOOL_NAME.match(name):
            raise ValueError(f"tool name {name!r} must match {TOOL_NAME.pattern}")

        def register(handler: Callable[[dict], Any]):
            server = self

            def call(task_id: str, agent_id: str, args: dict, approval_id: str | None = None,
                     traceparent: str | None = None) -> dict:
                envelope = {"task_id": task_id, "agent_id": agent_id, "server": server.name, "tool": name,
                            "args": args, "risk_class": risk_class, "approval_id": approval_id,
                            "traceparent": traceparent}
                try:
                    validate_envelope(envelope)
                    server.bucket.take(agent_id)
                except Exception as e:  # boundary rejections are audited too: no silent failure
                    server.receipts.deny(task_id=task_id, agent_id=agent_id, server=server.name, tool=name,
                                         args=args if isinstance(args, dict) else {}, risk_class=risk_class,
                                         reason=f"rejected:{type(e).__name__}", trace_id=None)
                    raise
                ctx = extract_context(traceparent)
                with server.tracer.start_as_current_span(f"mcp.tool/{name}", context=ctx,
                                                         attributes=standard_attributes(task_id, agent_id, name, risk_class)) as span:
                    trace_id = format(span.get_span_context().trace_id, "032x")
                    started = time.perf_counter()
                    result, verdict, approved = None, "ok", risk_class in ("low", "medium")
                    try:
                        server.receipts.consume_approval(approval_id, args, risk_class)
                        approved = True
                        if args_model is not None:
                            args_model.model_validate(args)
                        result = handler(args)
                        return {"result": result, "trace_id": trace_id}
                    except ValidationError as e:
                        verdict = "rejected:validation"
                        span.set_status(Status(StatusCode.ERROR, "argument validation failed"))
                        raise ValueError(f"arguments rejected at the boundary: {e.errors()}") from e
                    except Exception as e:
                        verdict = f"error:{type(e).__name__}"
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
                    finally:
                        if not approved:
                            # The database refuses a high/critical receipt without a consumed approval
                            # (INV-06), so a denied call is recorded in the audit ledger instead.
                            server.receipts.deny(task_id=task_id, agent_id=agent_id, server=server.name, tool=name,
                                                 args=args, risk_class=risk_class, reason=verdict, trace_id=trace_id)
                        else:
                            server.receipts.write(task_id=task_id, agent_id=agent_id, server=server.name, tool=name,
                                                  args=args, result=result,
                                                  latency_ms=(time.perf_counter() - started) * 1000,
                                                  cost=cost, risk_class=risk_class, approval_id=approval_id,
                                                  verdict=verdict, trace_id=trace_id)

            call.__name__ = name
            call.__doc__ = handler.__doc__
            self.mcp.tool(call, name=name)
            self.tools[name] = risk_class
            return handler

        return register

    def http_app(self) -> Starlette:
        mcp_app = self.mcp.http_app(path="/mcp")
        server = self

        async def health(_: Request) -> JSONResponse:
            try:
                db_ok = server.db.scalar("SELECT 1 AS ok") == 1
            except Exception:
                db_ok = False
            ok = db_ok and bool(server.tools)
            return JSONResponse({"service": server.name, "status": "ok" if ok else "degraded",
                                 "tools": server.tools, "checks": {"postgres": db_ok}}, status_code=200 if ok else 503)

        app = Starlette(routes=[Route("/health", health), Mount("/", app=mcp_app)], lifespan=mcp_app.lifespan)
        app.add_middleware(_BearerAuth, token_getter=lambda: server.secrets.get(server.token_ref))
        return app


def create_server(name: str, *, db: Database | None = None, secrets: SecretResolver | None = None,
                  token_ref: str | None = None, **kw) -> RevenueOSMcpServer:
    from revenueos_common.secrets import KeychainStore
    db = db or Database(actor=f"mcp:{name}")
    secrets = secrets or SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
    token_ref = token_ref or os.environ.get("REVENUEOS_MCP_TOKEN_REF", f"keychain://mcp-{name}-token")
    return RevenueOSMcpServer(name, db=db, secrets=secrets, token_ref=token_ref, **kw)
