from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
import hmac
from sqlalchemy import text
from .config import settings
from .db import engine
from .routers.core import router as core_router
from .routers.workflows import router as workflows_router
from .services import abuse
from .services.request_limits import BodyLimitMiddleware
from .services.readiness import verify_database

REQUESTS = Counter("revenueos_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("revenueos_http_request_seconds", "HTTP latency", ["route"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema changes are managed by Alembic, never by create_all on startup.
    if settings.app_env == "production":
        verify_database(engine, production=True)
    yield

app = FastAPI(title="RevenueOS API", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Authorization", "Content-Type", "X-Business-Id", "X-RevenueOS-Signature"],
                   allow_credentials=False)
app.add_middleware(BodyLimitMiddleware)
app.include_router(core_router)
app.include_router(workflows_router)

@app.middleware("http")
async def protection(request: Request, call_next):
    import time
    start = time.monotonic()
    try:
        allowed = await abuse.check(request)
    except Exception:
        return JSONResponse({"detail": "Request protection temporarily unavailable"}, status_code=503,
                            headers={"Retry-After": "30", "Cache-Control": "no-store"})
    if not allowed:
        return JSONResponse({"detail": "Too many requests. Try again shortly."}, status_code=429,
                            headers={"Retry-After": "60", "Cache-Control": "no-store"})
    if request.url.path.startswith("/api/") and request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > 1024 * 1024:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid length"}, status_code=400)
    try:
        response = await call_next(request)
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        LATENCY.labels(path).observe(time.monotonic() - start)
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    try:
        verify_database(engine, production=settings.app_env == "production")
        if settings.redis_url:
            from redis import Redis
            with Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1) as redis:
                redis.ping()
        return {"status": "ready"}
    except Exception:
        raise HTTPException(503, "Required services not ready")

@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    # Route is denied by default, including when accidentally exposed through a proxy.
    if not settings.metrics_token or not hmac.compare_digest(request.headers.get("X-Metrics-Token", ""), settings.metrics_token):
        raise HTTPException(status_code=404, detail="Not found")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
