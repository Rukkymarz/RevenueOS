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
RUNTIME_OMNI_URL = os.environ.get("RUNTIME_OMNI_URL", "http://runtime-omni:8102")


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


async def runtime_tool(request: Request) -> JSONResponse:
    """Remote control (spec 3.6): orchestrator -> runtime REST -> tool call -> receipt -> span."""
    import httpx
    from opentelemetry import propagate
    from revenueos_common.secrets import KeychainStore, SecretResolver
    from revenueos_mcp_common import setup_tracing, standard_attributes

    name = request.path_params["name"]
    body = await request.json()
    tracer = setup_tracing(SERVICE)
    attrs = standard_attributes(str(body.get("task_id", "")), str(body.get("agent_id", "")), name, "unclassified")
    with tracer.start_as_current_span("orchestrator.runtime_tool", context=propagate.extract(dict(request.headers)),
                                      attributes=attrs) as span:
        secrets = SecretResolver(KeychainStore(os.environ.get("REVENUEOS_KEYCHAIN_DIR", "/run/revenueos/keychain")))
        token = secrets.get("keychain://runtime-omni-token")
        if not token:
            return JSONResponse({"error": "runtime-omni token not configured"}, status_code=503)
        carrier: dict = {}
        propagate.inject(carrier)
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{RUNTIME_OMNI_URL}/v1/tools/{name}/invoke",
                                  json={**body, "traceparent": carrier.get("traceparent")},
                                  headers={"authorization": f"Bearer {token}"})
        out = r.json()
        if isinstance(out, dict) and out.get("risk_class"):
            span.set_attribute("risk_class", out["risk_class"])
        return JSONResponse({**out, "trace_id": format(span.get_span_context().trace_id, "032x")}, status_code=r.status_code)


app = create_app(SERVICE, checks={"component_map": config_loaded},
                 routes=[Route("/v1/info", info), Route("/v1/probe", probe, methods=["POST"]),
                         Route("/v1/runtime/tools/{name}", runtime_tool, methods=["POST"])])
