"""Redis-backed bounded access to expensive/unauthenticated routes.

Ingress proxy must overwrite X-Real-IP; API must never be publicly reachable except
through the proxy. Fail closed for protected writes if Redis is unavailable.
"""
import hashlib
import time
from fastapi import Request
from ..config import settings

# fixed-window per source IP; no raw IP stored in keys
LIMITS = (
    ("/api/v1/public/unsubscribe/", 30),
    ("/api/v1/assistant/chat", 40),
    ("/api/v1/ai/drafts", 20),
    ("/api/v1/outreach/", 25),
    ("/api/v1/setup", 5),
    ("/api/v1/media", 10),
    ("/api/v1/", 120),
)

async def check(request: Request) -> bool:
    if not settings.redis_url:
        return True  # local development; production config validator fails closed
    path = request.url.path
    matches = [(prefix, limit) for prefix, limit in LIMITS if path.startswith(prefix)]
    if not matches or request.method not in {"POST", "PATCH", "DELETE"}:
        return True
    group, limit = matches[0]
    # The production ingress unconditionally overwrites this header; never trust
    # it when running a public API outside the supplied production proxy.
    source = (request.headers.get("x-real-ip") if settings.trust_proxy_headers else None) or (request.client.host if request.client else "unknown")
    source_digest = hashlib.sha256(source.encode()).hexdigest()[:24]
    bucket = int(time.time() // 60)
    key = f"revenueos:limit:{group}:{source_digest}:{bucket}"
    from redis.asyncio import Redis
    client = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 65)
            result = await pipe.execute()
        return int(result[0]) <= limit
    finally:
        await client.aclose()
