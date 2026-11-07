"""Disposable loopback-only browser fixture. Never deploy this as an identity service.

REVENUEOS_E2E_TEST=true .venv/Scripts/python scripts/e2e_fixture.py
Then run Next dev with the public API/issuer URLs printed below.
No real accounts, provider calls, or production databases are used.
"""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import urlencode

if os.environ.get("REVENUEOS_E2E_TEST") != "true":
    raise SystemExit("Test-only fixture: set REVENUEOS_E2E_TEST=true explicitly")

temporary = tempfile.TemporaryDirectory(prefix="revenueos-e2e-")
issuer = "http://127.0.0.1:8765/identity"
origin = "http://127.0.0.1:3000"
os.environ.update(APP_ENV="test", DATABASE_URL="sqlite+pysqlite:///" + str(Path(temporary.name) / "test.sqlite"),
                  OIDC_ISSUER=issuer, OIDC_JWKS_URL=issuer + "/jwks", OIDC_AUDIENCE="revenueos-api",
                  BOOTSTRAP_ADMIN_EMAIL="e2e@example.org", CORS_ORIGINS=origin, REDIS_URL="",
                  AI_ENABLED="false", RESEND_API_KEY="", RESEND_FROM="", MEDIA_DIR=temporary.name)

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from revenueos.db import Base, engine
from revenueos.main import app as api
from revenueos import models  # noqa: F401

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
public_key.update(kid="disposable-e2e", use="sig", alg="RS256")
codes = {}
fixture = FastAPI(title="RevenueOS disposable test identity")
fixture.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=["POST", "GET", "PATCH"], allow_headers=["Content-Type", "Authorization", "X-Business-Id"])


@fixture.get("/identity/.well-known/openid-configuration")
def discovery():
    return {"issuer": issuer, "authorization_endpoint": issuer + "/authorize", "token_endpoint": issuer + "/token",
            "jwks_uri": issuer + "/jwks", "end_session_endpoint": issuer + "/logout",
            "response_types_supported": ["code"], "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"], "code_challenge_methods_supported": ["S256"]}


@fixture.get("/identity/jwks")
def jwks():
    return {"keys": [public_key]}


@fixture.get("/identity/authorize")
def authorize(request: Request):
    values = dict(request.query_params)
    if values.get("client_id") != "revenueos-web" or values.get("redirect_uri") != origin + "/" or values.get("code_challenge_method") != "S256":
        raise HTTPException(400, "Invalid test client")
    code = secrets.token_urlsafe(24)
    codes[code] = {**values, "created": time.time()}
    callback = origin + "/?" + urlencode({"code": code, "state": values.get("state", "")})
    from html import escape
    return HTMLResponse(f'<main><h1>Disposable test identity</h1><p>Local browser QA only. No real account or password.</p><a href="{escape(callback, quote=True)}">Continue as test administrator</a></main>')


@fixture.post("/identity/token")
async def token(request: Request):
    form = await request.form()
    code = codes.pop(str(form.get("code", "")), None)
    verifier = str(form.get("code_verifier", ""))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    if not code or time.time() - code["created"] > 120 or not secrets.compare_digest(challenge, code.get("code_challenge", "")):
        raise HTTPException(400, "Invalid test authorization code")
    if form.get("redirect_uri") != origin + "/" or form.get("client_id") != "revenueos-web" or form.get("grant_type") != "authorization_code":
        raise HTTPException(400, "Invalid token request")
    now = int(time.time())
    claims = {"sub": "e2e-test-administrator", "iss": issuer, "iat": now, "exp": now + 900,
              "email": "e2e@example.org", "email_verified": True, "name": "E2E test administrator"}
    def sign(audience, **extra):
        return jwt.encode({**claims, "aud": audience, **extra}, key, algorithm="RS256", headers={"kid": "disposable-e2e"})
    return {"access_token": sign("revenueos-api"), "id_token": sign("revenueos-web", nonce=code.get("nonce")),
            "token_type": "Bearer", "expires_in": 900, "scope": "openid profile email"}


@fixture.get("/identity/logout")
def logout(post_logout_redirect_uri: str = origin + "/"):
    if post_logout_redirect_uri != origin + "/":
        raise HTTPException(400, "Invalid logout destination")
    return RedirectResponse(origin + "/")


fixture.mount("/", api)

if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(engine)
    print("DISPOSABLE TESTS ONLY: API http://127.0.0.1:8765 | issuer " + issuer)
    try:
        uvicorn.run(fixture, host="127.0.0.1", port=8765)
    finally:
        engine.dispose()
        temporary.cleanup()
