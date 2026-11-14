"""HTTP surface of the orchestrator service (C01).

Phase 1 exposes the trace probe used to prove context propagation
api -> orchestrator -> MCP server. Agent orchestration lands in Phase 13.
"""
import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.registry import components_for, config_loaded
from revenueos_common.service import create_app

from . import COMPONENT, SERVICE

ECHO_PROBE_URL = os.environ.get("ECHO_PROBE_URL", "http://echo-probe:8201")


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT)})


async def probe(request: Request) -> JSONResponse:
    # Imported here so the health endpoint does not depend on the MCP/OTel stack being importable.
    from opentelemetry import propagate
    from revenueos_common.secrets import KeychainStore, SecretResolver
    from revenueos_contracts import models
    from revenueos_mcp_common import McpClient, setup_tracing, standard_attributes

    try:
        req = models.ProbeRequest.model_validate(await request.json())
    except Exception as e:  # contract violation at the boundary
        return JSONResponse({"error": "contract violation", "detail": str(e)}, status_code=400)
    tracer = setup_tracing(SERVICE)
    parent = propagate.extract(dict(request.headers))
    attrs = standard_attributes(str(req.task_id), str(req.agent_id), "probe_echo", "low")
    with tracer.start_as_current_span("orchestrator.probe", context=parent, attributes=attrs) as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
        token = secrets.get("keychain://mcp-echo-probe-token")
        if not token:
            return JSONResponse({"error": "echo-probe token not configured"}, status_code=503)
        out = await McpClient(ECHO_PROBE_URL, token).acall(
            "probe_echo", task_id=str(req.task_id), agent_id=str(req.agent_id), args={"message": req.message})
    body = models.ProbeResponse.model_validate({"trace_id": trace_id, "echo": out["result"]["echo"]})
    return JSONResponse(body.model_dump(mode="json"))


app = create_app(SERVICE, checks={"component_map": config_loaded},
                 routes=[Route("/v1/info", info), Route("/v1/probe", probe, methods=["POST"])])
