"""HTTP surface of the social service."""
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.registry import components_for, config_loaded
from revenueos_common.service import create_app

from . import COMPONENT, SERVICE


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": SERVICE, "component": COMPONENT, "hosts": components_for(COMPONENT)})


app = create_app(SERVICE, checks={"component_map": config_loaded}, routes=[Route("/v1/info", info)])
