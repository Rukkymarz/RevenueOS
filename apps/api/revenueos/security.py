from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, Header, HTTPException, status
import jwt
from jwt import PyJWKClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import Membership

# Public signing keys fetched from configured OIDC provider, never accept a client-selected issuer.
_jwks = PyJWKClient(settings.oidc_jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)

@dataclass(frozen=True)
class Principal:
    subject: str
    email: str
    email_verified: bool

@dataclass(frozen=True)
class Context:
    subject: str
    email: str
    business_id: str
    role: str

ROLE_LEVEL = {"viewer": 0, "operator": 1, "manager": 2, "admin": 3}

def require_role(ctx: Context, minimum: str) -> None:
    if ROLE_LEVEL.get(ctx.role, -1) < ROLE_LEVEL[minimum]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def authenticate(authorization: Annotated[str | None, Header()] = None) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    if len(token) > 12000:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        key = _jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=settings.oidc_audience,
                            issuer=settings.oidc_issuer, options={"require": ["exp", "iat", "sub", "iss", "aud"]}, leeway=30)
        return Principal(subject=claims["sub"], email=claims.get("email", "").lower(),
                         email_verified=claims.get("email_verified") is True)
    except (jwt.PyJWTError, jwt.PyJWKClientError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def get_context(principal: Annotated[Principal, Depends(authenticate)],
                db: Annotated[Session, Depends(get_db)],
                x_business_id: Annotated[str | None, Header()] = None) -> Context:
    if not x_business_id:
        raise HTTPException(status_code=400, detail="Select a business using X-Business-Id")
    member = db.scalar(select(Membership).where(Membership.business_id == x_business_id,
                                                Membership.subject == principal.subject))
    if not member:
        raise HTTPException(status_code=403, detail="Business access denied")
    if db.bind.dialect.name == "postgresql":
        # RLS setting is scoped to this transaction and cannot leak to pooled connections.
        db.execute(text("SELECT set_config('app.business_id', :business_id, true)"), {"business_id": member.business_id})
    return Context(principal.subject, principal.email, member.business_id, member.role)


def ensure_tenant_object(db: Session, cls: type, business_id: str, object_id: str):
    obj = db.scalar(select(cls).where(cls.id == object_id, cls.business_id == business_id))
    if obj is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return obj
