"""Regression tests for production boundaries; no external calls are made."""
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from revenueos.config import settings as base_settings, validate_production
from revenueos.routers import workflows
from revenueos.services import ai_usage
from revenueos.services.gateway import Completion


def test_approval_requires_preview_fingerprint(harness):
    client, _, state, _, _ = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Proposal Customer", "email": "approve@example.org"}).json()
    draft = client.post("/api/v1/outreach/drafts", json={
        "lead_id": lead["id"], "subject": "Proposed cleaning services",
        "body": "We propose recurring office cleaning twice per week."}).json()
    path = f'/api/v1/approvals/{draft["approval"]["id"]}'
    state["role"] = "manager"
    assert client.post(path + "/decision", json={"decision": "approved"}).status_code == 409
    assert client.post(path + "/decision", json={"decision": "approved", "review_hash": "f" * 64}).status_code == 409
    good = client.get(path + "/preview").json()["review_hash"]
    assert client.post(path + "/decision", json={"decision": "approved", "review_hash": good}).status_code == 200
    assert client.post(path + "/decision", json={"decision": "rejected"}).status_code == 409


def test_standalone_deployment_has_no_quote_ingestion_route(harness):
    client, _, state, first, second = harness
    assert client.post("/api/v1/integrations/quotes/events", json={"business_id": first}).status_code == 404
    state["business_id"] = second
    assert client.get("/api/v1/leads").json() == []


def test_optout_is_signed_one_lead_only_and_get_is_non_mutating(harness, monkeypatch):
    client, _, state, first, second = harness
    monkeypatch.setattr(workflows, "settings", SimpleNamespace(
        unsubscribe_secret="u" * 48, public_base_url="https://revenue.example.org"))
    lead = client.post("/api/v1/leads", json={"business_name": "Marketing contact",
        "email": "optout@example.org"}).json()
    token = workflows.unsubscribe_token(first, lead["id"])
    url = f"/api/v1/public/unsubscribe/{first}/{lead['id']}/{token}"
    assert client.get(url).json()["confirmation_required"] is True
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["opted_out"] is False
    assert client.post(url[:-1] + "0").status_code == 404
    assert client.post(f"/api/v1/public/unsubscribe/{second}/{lead['id']}/{token}").status_code == 404
    assert client.post(url).json()["unsubscribed"] is True
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["opted_out"] is True
    assert client.post(url).json()["unsubscribed"] is True


def test_chat_and_drafts_share_single_persistent_ai_quota(harness, monkeypatch):
    client, Session, state, first, _ = harness
    monkeypatch.setattr(ai_usage, "settings", SimpleNamespace(ai_daily_run_limit=1))
    async def mock_generate(message, task, role):
        return Completion("provider", "model", "Safe draft", 20, 10)
    monkeypatch.setattr(workflows, "generate", mock_generate)
    response = client.post("/api/v1/assistant/chat", json={"message": "Generate a marketing proposal", "use_ai": True})
    assert response.status_code == 200, response.text
    blocked = client.post("/api/v1/ai/drafts", json={"prompt": "Create a follow-up email", "task": "marketing"})
    assert blocked.status_code == 429
    from sqlalchemy import select
    from revenueos.models import AIRun
    with Session() as db:
        runs = db.scalars(select(AIRun).where(AIRun.business_id == first)).all()
        assert len(runs) == 1 and runs[0].status == "completed"


def test_production_config_denies_insecure_defaults():
    secure = replace(base_settings, app_env="production", oidc_issuer="https://auth.revenue.example.org/realms/revenueos",
        database_url="postgresql+psycopg://revenueos_app:ci-only-password-32-characters-long@localhost/revenueos",
        bootstrap_admin_email="admin@example.org",
        public_base_url="https://revenue.example.org", cors_origins=("https://revenue.example.org",),
        metrics_token="m" * 64, resend_api_key="", ai_daily_run_limit=20,
        redis_url="redis://redis:6379/0")
    assert validate_production(secure) is None
    import pytest
    with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
        validate_production(replace(secure, oidc_issuer="http://identity"))
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        validate_production(replace(secure, metrics_token="short"))
