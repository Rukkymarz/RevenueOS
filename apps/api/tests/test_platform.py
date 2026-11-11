import hashlib
import hmac
import io
import json
import zipfile
from revenueos.services.scoring import score_lead, opportunity_score
from revenueos.services.agent_graph import respond
from revenueos.routers import workflows


def test_lead_scoring_never_fabricates_unknowns():
    assert score_lead({}).score is None
    assert score_lead({"seo": 100}).confidence == 25
    assert score_lead({"seo": 100}).score == 100
    assert opportunity_score({"seo": 100}).score == 0


def test_lead_crud_tenant_isolation_and_role(harness):
    client, _, state, first, second = harness
    response = client.post("/api/v1/leads", json={"business_name": "Acme Cleaning", "industry": "cleaning",
                                                  "email": "contact@example.org", "metrics": {"seo": 30}})
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["business_id"] == first
    assert record["score"] == 30
    assert record["score_confidence"] == 25
    lead_id = record["id"]
    assert len(client.get("/api/v1/leads").json()) == 1
    assert client.patch(f"/api/v1/leads/{lead_id}", json={"stage": "qualified"}).status_code == 200
    assert client.patch(f"/api/v1/leads/{lead_id}", json={"stage": "random"}).status_code == 422
    state["business_id"] = second
    assert client.get("/api/v1/leads").json() == []
    assert client.get(f"/api/v1/leads/{lead_id}").status_code == 404
    state["business_id"] = first
    state["role"] = "viewer"
    assert client.get("/api/v1/leads").status_code == 200
    assert client.post("/api/v1/leads", json={"business_name": "Not permitted"}).status_code == 403


def test_human_approvals_and_outreach_gates(harness):
    client, _, state, _, _ = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Local Services", "email": "test@example.org"}).json()
    draft = client.post("/api/v1/outreach/drafts", json={"lead_id": lead["id"], "subject": "Proposal for you", "body": "Hello. Here is our offer and next steps."})
    assert draft.status_code == 201, draft.text
    payload = draft.json()
    approval_id = payload["approval"]["id"]
    assert client.get("/api/v1/approvals").status_code == 200
    state["role"] = "operator"
    assert client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved"}).status_code == 403
    state["role"] = "manager"
    review_hash = client.get(f"/api/v1/approvals/{approval_id}/preview").json()["review_hash"]
    assert client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved", "review_hash": review_hash}).status_code == 200
    assert client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved"}).status_code == 409
    # No provider configured => no external send occurs; real send needs documented lawful basis.
    assert client.post(f'/api/v1/outreach/{payload["draft"]["id"]}/send').status_code == 503


def test_proposals_and_generated_websites(harness):
    client, _, _, _, _ = harness
    proposal = client.post("/api/v1/proposals", json={"title": "SEO Growth", "content": "We will complete a tailored audit and create an optimization roadmap.", "amount": 450}).json()
    assert client.get(f'/api/v1/proposals/{proposal["id"]}/export?format=pdf').content.startswith(b"%PDF")
    docx = client.get(f'/api/v1/proposals/{proposal["id"]}/export?format=docx')
    assert docx.status_code == 200 and docx.content.startswith(b"PK")
    site = client.post("/api/v1/websites", json={"company": "Northeast Services", "industry": "cleaning",
                                                     "tagline": "Clean spaces. Clear minds.", "contact_email": "info@example.org",
                                                     "city": "Chicago", "services": ["Residential cleaning", "Office cleaning"]})
    assert site.status_code == 201, site.text
    zip_response = client.get(f'/api/v1/websites/{site.json()["id"]}/download')
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as z:
        names = z.namelist()
        assert any(n.endswith("app/page.tsx") for n in names)
        assert any(n.endswith("README.md") for n in names)


def test_no_legacy_quote_integrations_in_standalone_app(harness):
    client, _, _, _, _ = harness
    # RevenueOS must not have an inbound connector to a separate business's CRM.
    response = client.post("/api/v1/integrations/quotes/events", json={"event_id": "legacy"})
    assert response.status_code == 404
    assert client.get("/api/v1/leads").json() == []


def test_assistant_is_bounded_and_read_only():
    result = respond("Please create a proposal for my company", "sales")
    assert result["intent"] == "proposal"
    assert "Proposals" in result["result"]


def test_monitoring_is_private_by_default(harness):
    client, _, _, _, _ = harness
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 404


def test_plugin_contract_and_media_svg(harness, tmp_path, monkeypatch):
    from revenueos.plugins.registry import manifests, required_approvals
    from revenueos.services.media import banner_svg
    entries = manifests()
    assert any(p["id"] == "crm" and p["enabled"] for p in entries)
    assert required_approvals("message.send")
    assert not required_approvals("lead.list")
    assert b"&lt;script&gt;" in banner_svg("<script>", "safe")
    client, _, _, _, _ = harness
    response = client.get("/api/v1/plugins")
    assert response.status_code == 200
    assert isinstance(response.json()[0]["capabilities"], list)


def test_no_outreach_to_suppressed_contact_even_with_approval(harness, monkeypatch):
    client, _, state, _, _ = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Suppressed Lead",
                         "email": "no-contact@example.org", "opted_out": True,
                         "lawful_basis": "consent", "lawful_basis_note": "Previously opted in, now withdrawn"}).json()
    payload = client.post("/api/v1/outreach/drafts", json={"lead_id": lead["id"],
                        "subject": "Follow-up request", "body": "Hello, I wanted to share our service proposal."}).json()
    approval_id = payload["approval"]["id"]
    state["role"] = "manager"
    review_hash = client.get(f"/api/v1/approvals/{approval_id}/preview").json()["review_hash"]
    assert client.post(f"/api/v1/approvals/{approval_id}/decision", json={"decision": "approved", "review_hash": review_hash}).status_code == 200
    monkeypatch.setattr(workflows, "settings", type("TestSettings", (), {
        "resend_api_key": "dummy-for-test", "resend_from": "verified@example.org",
        "outreach_postal_address": "123 Main Street, Chicago, IL", "unsubscribe_secret": "x" * 48,
        "public_base_url": "https://example.org"})())
    # This must return before any network call to the email provider.
    assert client.post(f'/api/v1/outreach/{payload["draft"]["id"]}/send').status_code == 403


def test_cross_tenant_reference_is_not_linkable(harness):
    client, _, state, first, second = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Private Lead"}).json()
    state["business_id"] = second
    response = client.post("/api/v1/tasks", json={"title": "Do not link", "lead_id": lead["id"]})
    assert response.status_code == 404


def test_approval_preview_requires_exact_tenant_content(harness):
    client, _, state, first, second = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Review Candidate", "email":"review@example.org"}).json()
    created = client.post("/api/v1/outreach/drafts", json={"lead_id":lead["id"],
                         "subject":"Human review subject", "body":"This is the exact content that must be displayed first."}).json()
    approval_id = created["approval"]["id"]
    response = client.get(f"/api/v1/approvals/{approval_id}/preview")
    assert response.status_code == 200
    assert response.json()["recipient_email"] == "review@example.org"
    assert response.json()["body"] == "This is the exact content that must be displayed first."
    state["business_id"] = second
    assert client.get(f"/api/v1/approvals/{approval_id}/preview").status_code == 404


def test_draft_send_control_shows_approval_state(harness):
    client, _, state, _, _ = harness
    lead = client.post("/api/v1/leads", json={"business_name": "Approval Status", "email":"status@example.org"}).json()
    created = client.post("/api/v1/outreach/drafts", json={"lead_id":lead["id"],
                     "subject": "Subject to review", "body": "Email body with all of the human-reviewed details."}).json()
    records = client.get("/api/v1/outreach/drafts").json()
    assert records[0]["approval_decision"] == "pending"
    state["role"] = "manager"
    approval_id = created["approval"]["id"]
    review_hash = client.get(f"/api/v1/approvals/{approval_id}/preview").json()["review_hash"]
    client.post(f'/api/v1/approvals/{approval_id}/decision', json={"decision":"approved", "review_hash": review_hash})
    assert client.get("/api/v1/outreach/drafts").json()[0]["approval_decision"] == "approved"
