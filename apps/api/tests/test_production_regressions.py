"""Exercise real control boundaries without spending provider budget."""
from dataclasses import replace
from types import SimpleNamespace

import pytest
from revenueos.config import settings, validate_production
from revenueos.main import app
from revenueos.security import get_context
from revenueos.services import abuse


def test_import_is_validated_atomic_and_idempotent(harness):
    client, _, state, _, other = harness
    record = {"business_name": "Verified import", "source": "authorized-file", "external_id": "source-1"}
    assert client.post("/api/v1/leads/import", json={"leads": [record, {"business_name": "x"}]}).status_code == 422
    assert client.get("/api/v1/leads").json() == []
    assert client.post("/api/v1/leads/import", json={"leads": [record, record]}).json() == {"imported": 1, "skipped": 1}
    assert client.post("/api/v1/leads/import", json={"leads": [record]}).json() == {"imported": 0, "skipped": 1}
    state["business_id"] = other
    assert client.get("/api/v1/leads").json() == []
    assert client.post("/api/v1/leads/import", json={"leads": [record]}).json()["imported"] == 1
    state["role"] = "viewer"
    assert client.post("/api/v1/leads/import", json={"leads": [record]}).status_code == 403


def test_lead_patch_validation_and_suppression(harness):
    client, *_ = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Contact record"}).json()
    url = f"/api/v1/leads/{lead['id']}"
    for body in ({"stage": None}, {"metrics": {"seo": 200}}, {"metrics": {"seo": True}}, {"metrics": {"invented": 5}}, {"unknown": True}):
        assert client.patch(url, json=body).status_code == 422
    result = client.patch(url, json={"opted_out": True, "metrics": {"seo": 75}, "lawful_basis": "consent", "lawful_basis_note": "Documented registration"})
    assert result.status_code == 200
    assert result.json()["score"] == 75
    assert result.json()["opted_out"] is True
    assert client.post("/api/v1/leads", json={"business_name": "   "}).status_code == 422


def test_pipeline_updates_and_audit_access(harness):
    client, _, state, _, other = harness
    deal = client.post("/api/v1/opportunities", json={"name": "Service deal", "value": 600}).json()
    assert client.get("/api/v1/reports/pipeline").json()["pipeline_value"] == 600
    assert client.patch(f"/api/v1/opportunities/{deal['id']}", json={"stage": "won"}).status_code == 200
    assert client.get("/api/v1/reports/pipeline").json()["pipeline_value"] == 0
    assert client.patch(f"/api/v1/opportunities/{deal['id']}", json={"value": None}).status_code == 422
    client_record = client.post("/api/v1/clients", json={"name": "Customer", "monthly_revenue": 100}).json()
    assert client.patch(f"/api/v1/clients/{client_record['id']}", json={"active": False}).status_code == 200
    assert client.get("/api/v1/reports/pipeline").json()["mrr"] == 0
    assert any(e["action"] == "opportunity.update" for e in client.get("/api/v1/audit-events").json())
    export = client.get("/api/v1/workspace/export").json()
    assert len(export["records"]["opportunities"]) == 1
    state["business_id"] = other
    assert client.patch(f"/api/v1/opportunities/{deal['id']}", json={"stage": "lost"}).status_code == 404
    assert client.get("/api/v1/workspace/export").json()["records"]["opportunities"] == []
    state["role"] = "operator"
    assert client.get("/api/v1/audit-events").status_code == 403
    assert client.get("/api/v1/workspace/export").status_code == 403


def test_real_membership_dependency_denies_spoofed_business(harness):
    client, _, _, own, other = harness
    override = app.dependency_overrides.pop(get_context)
    try:
        assert client.get("/api/v1/leads").status_code == 400
        assert client.get("/api/v1/leads", headers={"X-Business-Id": own}).status_code == 200
        assert client.get("/api/v1/leads", headers={"X-Business-Id": other}).status_code == 403
    finally:
        app.dependency_overrides[get_context] = override


def test_rate_limit_is_enforced_and_fails_closed(harness, monkeypatch):
    client, *_ = harness
    async def denied(request):
        return False
    monkeypatch.setattr(abuse, "check", denied)
    response = client.post("/api/v1/leads", json={"business_name": "Blocked"})
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"
    async def unavailable(request):
        raise ConnectionError("Redis unavailable")
    monkeypatch.setattr(abuse, "check", unavailable)
    assert client.post("/api/v1/leads", json={"business_name": "Blocked"}).status_code == 503


def test_chunked_body_is_bounded(harness):
    client, *_ = harness
    def chunks():
        for _ in range(20):
            yield b"x" * 65536
    assert client.post("/api/v1/leads", content=chunks(), headers={"Content-Type": "application/json"}).status_code == 413


def test_paginated_leads_and_search(harness):
    client, *_ = harness
    for name in ("Alpha customer", "Beta customer", "Gamma customer"):
        assert client.post("/api/v1/leads", json={"business_name": name}).status_code == 201
    first = client.get("/api/v1/leads?limit=2").json()
    second = client.get("/api/v1/leads?limit=2&offset=2").json()
    assert len(first) == 2 and len(second) == 1
    assert not {row["id"] for row in first} & {row["id"] for row in second}
    assert client.get("/api/v1/leads?q=beta").json()[0]["business_name"] == "Beta customer"


def test_production_rejects_owner_database_role():
    config = replace(settings, app_env="production", database_url="postgresql://postgres:long-ci-only-test-password-1234@localhost/revenueos")
    with pytest.raises(RuntimeError, match="non-owner"):
        validate_production(config)


def test_signed_access_tokens_pin_audience_issuer_and_algorithm(monkeypatch):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import HTTPException
    from revenueos import security
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(security, "_jwks", SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    claims = {"sub": "verified-user", "email": "user@example.org", "email_verified": True,
              "iss": settings.oidc_issuer, "aud": settings.oidc_audience, "iat": int(time.time()), "exp": int(time.time()) + 120}
    def authenticate(payload):
        return security.authenticate("Bearer " + jwt.encode(payload, key, algorithm="RS256"))
    assert authenticate(claims).email_verified is True
    for altered in ({**claims, "aud": "other-app"}, {**claims, "iss": "https://untrusted.example.org"},
                    {**claims, "exp": int(time.time()) - 120}):
        with pytest.raises(HTTPException) as error:
            authenticate(altered)
        assert error.value.status_code == 401
    with pytest.raises(HTTPException):
        security.authenticate("Bearer " + jwt.encode(claims, "test-only-signing-secret-32-chars-long", algorithm="HS256"))
