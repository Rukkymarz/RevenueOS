"""HTTP surface of the ambient-watchers service: /health and /v1/info only. The actual work --
scanning NAVA's durable state and A2A-notifying the owning agent (watchers.py) -- runs in a
background thread started from __main__.py, so the container is a single process that looks
like every other service to compose's healthcheck and the Command Center (spec 1.1), while the
real scan loop keeps running underneath it."""
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.registry import components_for, config_loaded
from revenueos_common.service import create_app

from . import COMPONENT, SERVICE


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT)})


app = create_app(SERVICE, checks={"component_map": config_loaded}, routes=[Route("/v1/info", info)])
