"""Gated writes and executable artifact factories."""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from pathlib import Path
from typing import Annotated
import hashlib
import hmac
import json
import os
import re
import uuid
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import (Lead, Proposal, WebsiteProject, MediaJob, Approval, MessageDraft,
                      AIRun, Knowledge, Campaign)
from ..schemas import DecisionIn, MessageIn, MediaIn, ChatIn, AIDraftIn
from ..security import Context, get_context, ensure_tenant_object, require_role
from ..services.audit import record
from ..services.agent_graph import respond
from ..services.proposals import make_docx, make_pdf
from ..services.website_factory import site_zip
from ..services.media import banner_svg, render_video
from ..services.gateway import generate
from ..services.ai_usage import reserve, complete, fail
from ..plugins.registry import manifests
from .core import asdict

router = APIRouter(prefix="/api/v1", tags=["workflows"])
DB = Annotated[Session, Depends(get_db)]
CTX = Annotated[Context, Depends(get_context)]


@router.get("/proposals/{proposal_id}/export")
def proposal_export(proposal_id: str, format: str, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    obj = ensure_tenant_object(db, Proposal, ctx.business_id, proposal_id)
    if format not in {"pdf", "docx"}:
        raise HTTPException(422, "format must be pdf or docx")
    body = make_pdf(obj.title, obj.content, float(obj.amount) if obj.amount is not None else None) if format == "pdf" else make_docx(obj.title, obj.content, float(obj.amount) if obj.amount is not None else None)
    content_type = "application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    record(db, ctx, "proposal.export", "proposals", obj.id, {"format": format})
    db.commit()
    return Response(body, media_type=content_type,
                    headers={"Content-Disposition": f'attachment; filename="proposal-{obj.id}.{format}"',
                             "Cache-Control": "no-store"})


@router.get("/websites/{website_id}/download")
def website_download(website_id: str, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    obj = ensure_tenant_object(db, WebsiteProject, ctx.business_id, website_id)
    output = site_zip(obj.company, obj.industry, obj.tagline, obj.contact_email, obj.city, obj.services)
    record(db, ctx, "website.download", "websites", obj.id)
    db.commit()
    return Response(output, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="site-{obj.id}.zip"', "Cache-Control": "no-store"})


@router.post("/media", status_code=201)
def create_media(payload: MediaIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    job = MediaJob(business_id=ctx.business_id, kind=payload.kind, title=payload.title,
                   subtitle=payload.subtitle, status="processing")
    db.add(job)
    db.flush()
    folder = Path(settings.media_dir)
    folder.mkdir(parents=True, exist_ok=True)
    # Generated filename exclusively derived from server UUID, not user input.
    file = f"{job.id}.svg" if payload.kind == "image" else f"{job.id}.mp4"
    destination = folder / file
    try:
        if payload.kind == "image":
            destination.write_bytes(banner_svg(payload.title, payload.subtitle))
        else:
            render_video(payload.title, payload.subtitle, destination)
        job.output_file = file
        job.status = "done"
    except (OSError, RuntimeError, __import__("subprocess").SubprocessError):
        job.status = "failed"
        job.error = "Video rendering unavailable; verify FFmpeg and storage"
    record(db, ctx, "media.create", "media_jobs", job.id, {"kind": job.kind, "status": job.status})
    result = asdict(job)
    db.commit()
    return result


@router.get("/media/{job_id}/download")
def media_download(job_id: str, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    job = ensure_tenant_object(db, MediaJob, ctx.business_id, job_id)
    if job.status != "done" or not job.output_file or not re.fullmatch(r"[0-9a-f-]{36}\.(svg|mp4)", job.output_file):
        raise HTTPException(404, "Media not ready")
    target = Path(settings.media_dir) / job.output_file
    if not target.is_file():
        raise HTTPException(404, "Media artifact missing")
    media_type = "image/svg+xml" if job.kind == "image" else "video/mp4"
    return FileResponse(target, filename=target.name, media_type=media_type,
                        headers={"Cache-Control": "private, no-store", "Content-Security-Policy": "sandbox"})


@router.post("/outreach/drafts", status_code=201)
def create_draft(payload: MessageIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    lead = ensure_tenant_object(db, Lead, ctx.business_id, payload.lead_id)
    if not lead.email:
        raise HTTPException(422, "Lead has no contact email")
    draft = MessageDraft(business_id=ctx.business_id, lead_id=lead.id, recipient_email=lead.email,
                         subject=payload.subject, body=payload.body, status="draft")
    db.add(draft)
    db.flush()
    approval = Approval(business_id=ctx.business_id, action="message.send", resource_type="message_drafts",
                        resource_id=draft.id, requested_by=ctx.subject, decision="pending")
    db.add(approval)
    record(db, ctx, "outreach.draft", "message_drafts", draft.id)
    db.commit()
    return {"draft": asdict(draft), "approval": asdict(approval)}


@router.get("/outreach/drafts")
def drafts(ctx: CTX, db: DB):
    require_role(ctx, "operator")
    items = db.scalars(select(MessageDraft).where(MessageDraft.business_id == ctx.business_id)
                       .order_by(MessageDraft.created_at.desc()).limit(50)).all()
    approvals = db.scalars(select(Approval).where(Approval.business_id == ctx.business_id,
                         Approval.action == "message.send", Approval.resource_type == "message_drafts",
                         Approval.resource_id.in_([item.id for item in items]))).all() if items else []
    decisions = {approval.resource_id: approval.decision for approval in approvals}
    return [{**asdict(d), "approval_decision": decisions.get(d.id, "pending")} for d in items]


@router.get("/approvals")
def approvals(ctx: CTX, db: DB):
    require_role(ctx, "operator")
    return [asdict(a) for a in db.scalars(select(Approval).where(Approval.business_id == ctx.business_id)
                                         .order_by(Approval.created_at.desc()).limit(100))]


def review_fingerprint(approval: Approval, draft: MessageDraft) -> str:
    # Server-computed exact-content digest, revalidated before approval and transmission.
    payload = json.dumps([approval.action, draft.recipient_email.lower(), draft.subject,
                          delivery_body(draft) if settings.outreach_postal_address and
                          len(settings.unsubscribe_secret) >= 32 and settings.public_base_url else draft.body],
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@router.get("/approvals/{approval_id}/preview")
def approval_preview(approval_id: str, ctx: CTX, db: DB):
    """Return exact content for an informed human decision. Never approve by ID alone."""
    require_role(ctx, "operator")
    approval = ensure_tenant_object(db, Approval, ctx.business_id, approval_id)
    if approval.resource_type != "message_drafts" or approval.action != "message.send":
        raise HTTPException(422, "No reviewed preview is available for this action")
    draft = ensure_tenant_object(db, MessageDraft, ctx.business_id, approval.resource_id)
    return {"id": approval.id, "action": approval.action, "decision": approval.decision,
            "recipient_email": draft.recipient_email, "subject": draft.subject, "body": delivery_body(draft) if settings.outreach_postal_address and
            len(settings.unsubscribe_secret) >= 32 and settings.public_base_url else draft.body,
            "draft_status": draft.status, "review_hash": review_fingerprint(approval, draft)}


@router.post("/approvals/{approval_id}/decision")
def decide(approval_id: str, payload: DecisionIn, ctx: CTX, db: DB):
    require_role(ctx, "manager")
    # Serialize decisions for the same approval across concurrent requests.
    approval = db.scalar(select(Approval).where(Approval.id == approval_id,
                    Approval.business_id == ctx.business_id).with_for_update())
    if approval is None:
        raise HTTPException(404, "Resource not found")
    if approval.decision != "pending":
        raise HTTPException(409, "Approval is already decided")
    if approval.action == "message.send":
        draft = ensure_tenant_object(db, MessageDraft, ctx.business_id, approval.resource_id)
        if draft.status != "draft":
            raise HTTPException(409, "Draft is no longer eligible for approval")
        current_hash = review_fingerprint(approval, draft)
        if payload.decision == "approved" and (not payload.review_hash or not hmac.compare_digest(payload.review_hash, current_hash)):
            raise HTTPException(409, "Content has not been verified; open the exact preview and approve again")
        approval.review_hash = current_hash if payload.decision == "approved" else None
    approval.decision = payload.decision
    approval.decided_by = ctx.subject
    approval.decided_at = datetime.now(timezone.utc)
    approval.reason = payload.reason
    record(db, ctx, "approval." + payload.decision, "approvals", approval.id,
           {"action": approval.action, "resource_type": approval.resource_type})
    db.commit()
    return asdict(approval)


@router.post("/outreach/{draft_id}/send")
def send_email(draft_id: str, ctx: CTX, db: DB):
    require_role(ctx, "manager")
    if not settings.resend_api_key or not settings.resend_from:
        raise HTTPException(503, "Email provider is not configured")
    # For PostgreSQL serialize concurrent approval/send requests on the draft row.
    stmt = select(MessageDraft).where(MessageDraft.id == draft_id,
                                     MessageDraft.business_id == ctx.business_id).with_for_update()
    draft = db.scalar(stmt)
    if not draft:
        raise HTTPException(404, "Draft not found")
    if draft.status != "draft":
        raise HTTPException(409, "Draft was already sent, attempted or cancelled")
    approval = db.scalar(select(Approval).where(Approval.business_id == ctx.business_id,
                                                 Approval.action == "message.send", Approval.resource_id == draft.id))
    if not approval or approval.decision != "approved" or not approval.review_hash or not hmac.compare_digest(
            approval.review_hash, review_fingerprint(approval, draft)):
        raise HTTPException(403, "Exact-content human approval required")
    lead = ensure_tenant_object(db, Lead, ctx.business_id, draft.lead_id)
    if lead.opted_out or not lead.lawful_basis or not lead.lawful_basis_note:
        raise HTTPException(403, "Recipient is suppressed or lawful basis is undocumented")
    if not lead.email or lead.email.lower() != draft.recipient_email.lower():
        raise HTTPException(409, "Recipient changed; issue a new draft and approval")
    if len(settings.unsubscribe_secret) < 32 or not settings.public_base_url.startswith("https://") or not settings.outreach_postal_address:
        raise HTTPException(503, "Email compliance footer and unsubscribe configuration missing")
    unsubscribe = unsubscribe_url(draft.business_id, draft.lead_id)
    compliant_body = delivery_body(draft)
    draft.status = "sending"  # Mark before external call; ambiguous failures require manual reconciliation.
    record(db, ctx, "outreach.send_attempt", "message_drafts", draft.id)
    db.commit()
    # The status reservation was committed intentionally before provider I/O.
    # Reestablish the transaction-scoped tenant after commit for final updates.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.business_id', :business_id, true)"), {"business_id": ctx.business_id})
    try:
        with httpx.Client(timeout=15.0, follow_redirects=False) as client:
            response = client.post("https://api.resend.com/emails",
                                   headers={"Authorization": f"Bearer {settings.resend_api_key}",
                                            "Idempotency-Key": draft.id},
                                   json={"from": settings.resend_from, "to": [draft.recipient_email],
                                         "subject": draft.subject, "text": compliant_body,
                                         "headers": {"List-Unsubscribe": f"<{unsubscribe}>"}})
            response.raise_for_status()
            provider_id = response.json().get("id")
            if not isinstance(provider_id, str) or not provider_id.strip() or len(provider_id) > 160:
                raise ValueError("Invalid provider acknowledgment")
        draft.status, draft.provider_id, draft.sent_at = "sent", provider_id, datetime.now(timezone.utc)
        lead.last_contact = draft.sent_at
        record(db, ctx, "outreach.sent", "message_drafts", draft.id)
    except (httpx.HTTPError, ValueError):
        draft.status = "unknown"  # Never auto-retry potentially accepted mail.
        record(db, ctx, "outreach.send_unconfirmed", "message_drafts", draft.id)
        db.commit()
        raise HTTPException(502, "Provider response uncertain. Check Resend before any retry")
    db.commit()
    return {"id": draft.id, "status": draft.status, "provider_id": draft.provider_id}


def unsubscribe_token(business_id: str, lead_id: str) -> str:
    if len(settings.unsubscribe_secret) < 32:
        raise HTTPException(503, "Unsubscribe service unavailable")
    payload = f"{business_id}:{lead_id}".encode("utf-8")
    return hmac.new(settings.unsubscribe_secret.encode(), payload, hashlib.sha256).hexdigest()


def unsubscribe_url(business_id: str, lead_id: str) -> str:
    return (f"{settings.public_base_url.rstrip('/')}/api/v1/public/unsubscribe/"
            f"{business_id}/{lead_id}/{unsubscribe_token(business_id, lead_id)}")


def validated_optout(business_id: str, lead_id: str, token: str, db: Session) -> Lead:
    if not hmac.compare_digest(token, unsubscribe_token(business_id, lead_id)):
        raise HTTPException(404, "Unsubscribe link invalid")
    if db.bind.dialect.name == "postgresql":
        # Only the server-signed business is given RLS scope; no user-selected
        # business is trusted without its HMAC. Never use superuser DB credentials.
        db.execute(text("SELECT set_config('app.business_id', :business_id, true)"), {"business_id": business_id})
    lead = db.scalar(select(Lead).where(Lead.business_id == business_id, Lead.id == lead_id))
    if lead is None:
        raise HTTPException(404, "Unsubscribe link invalid")
    return lead


@router.get("/public/unsubscribe/{business_id}/{lead_id}/{token}")
def unsubscribe_confirmation(business_id: str, lead_id: str, token: str, db: DB):
    # GET never mutates data; email scanners automatically fetch links.
    lead = validated_optout(business_id, lead_id, token, db)
    return {"confirmation_required": not lead.opted_out,
            "message": "POST this link to confirm opt-out" if not lead.opted_out else "Already unsubscribed"}


@router.post("/public/unsubscribe/{business_id}/{lead_id}/{token}")
def unsubscribe_contact(business_id: str, lead_id: str, token: str, db: DB):
    lead = validated_optout(business_id, lead_id, token, db)
    if not lead.opted_out:
        lead.opted_out = True
        db.commit()
    return {"unsubscribed": True}


def delivery_body(draft: MessageDraft) -> str:
    return (f"{draft.body.rstrip()}\n\n---\n{settings.outreach_postal_address}\n"
            f"To opt out of future outreach: {unsubscribe_url(draft.business_id, draft.lead_id)}")


@router.post("/assistant/chat")
async def chat(payload: ChatIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    role = payload.role or "revenue"
    routed = respond(payload.message, role)
    if payload.use_ai:
        entry = reserve(db, ctx, role)
        try:
            draft = await generate(payload.message, "marketing" if routed["intent"] == "marketing" else "reasoning", role)
            complete(db, entry, draft)
            return {"intent": routed["intent"], "role": role, "message": draft.text,
                    "provider": draft.provider, "model": draft.model, "requires_approval": True}
        except RuntimeError as exc:
            fail(db, entry)
            return {"intent": routed["intent"], "role": role, "message": routed["result"], "notice": str(exc)}
    return {"intent": routed["intent"], "role": role, "message": routed["result"], "requires_approval": True}


@router.post("/ai/drafts")
async def ai_draft(payload: AIDraftIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    entry = reserve(db, ctx, payload.role)
    try:
        answer = await generate(payload.prompt, payload.task, payload.role)
        complete(db, entry, answer)
        return {"id": entry.id, "draft": answer.text, "provider": answer.provider, "model": answer.model,
                "status": "draft", "requires_approval": True}
    except RuntimeError as exc:
        fail(db, entry)
        raise HTTPException(503, str(exc)) from exc


@router.get("/plugins")
def plugins(ctx: CTX):
    """Registry contains first-party trusted adapters and declared capability scopes."""
    require_role(ctx, "operator")
    return manifests()
