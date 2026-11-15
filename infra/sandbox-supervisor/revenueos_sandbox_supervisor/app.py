"""Sandbox supervisor HTTP surface. /health is green only when the kernel features the
Phase 2 sandbox needs (unshare with mount/net/pid namespaces, overlayfs) are present."""
import os
import shutil
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from revenueos_common.service import create_app


def capabilities() -> dict:
    fs = Path("/proc/filesystems").read_text() if Path("/proc/filesystems").exists() else ""
    return {
        "unshare": shutil.which("unshare") is not None,
        "overlayfs": "overlay" in fs,
        "bubblewrap": shutil.which("bwrap") is not None,
        "user_namespaces": Path("/proc/self/ns/user").exists(),
    }


async def info(_: Request) -> JSONResponse:
    return JSONResponse({"service": "sandbox-supervisor", "component": "C17", "capabilities": capabilities()})


app = create_app("sandbox-supervisor",
                 checks={"unshare": lambda: capabilities()["unshare"], "overlayfs": lambda: capabilities()["overlayfs"]},
                 routes=[Route("/v1/info", info)])


def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8300)))
