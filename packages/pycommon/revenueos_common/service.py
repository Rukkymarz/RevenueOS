"""Service skeleton shared by every Python service: a Starlette app with /health,
optional readiness checks, and a uvicorn entrypoint.

/health returns 200 only when every registered check passes; a check that
raises or returns False makes the service report 503 with the failing check
named, so compose health and the Command Center see the real state.
"""
import os
import time
from typing import Callable

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

VERSION = os.environ.get("REVENUEOS_VERSION", "0.1.0")


def _run_check(fn: Callable[[], bool]) -> tuple[bool, str]:
    try:
        ok = fn()
        return bool(ok), "ok" if ok else "failed"
    except Exception as e:  # a crashing check is a failing check, never a pass
        return False, f"error: {type(e).__name__}: {e}"


def create_app(service: str, checks: dict[str, Callable[[], bool]] | None = None,
               routes: list[Route] | None = None) -> Starlette:
    checks = checks or {}
    started = time.time()

    async def health(_: Request) -> JSONResponse:
        results = {name: _run_check(fn) for name, fn in checks.items()}
        healthy = all(ok for ok, _ in results.values())
        body = {
            "service": service,
            "status": "ok" if healthy else "degraded",
            "version": VERSION,
            "uptime_s": round(time.time() - started, 3),
            "checks": {name: detail for name, (_, detail) in results.items()},
        }
        return JSONResponse(body, status_code=200 if healthy else 503)

    return Starlette(routes=[Route("/health", health)] + list(routes or []))


def postgres_check(db) -> Callable[[], bool]:
    return lambda: db.scalar("SELECT 1 AS ok") == 1


def run(app: Starlette, default_port: int = 8000) -> None:  # pragma: no cover - process entrypoint
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", default_port)),
                log_level=os.environ.get("LOG_LEVEL", "info"))
