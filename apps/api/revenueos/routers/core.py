from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import (Business, Membership, Lead, Task, Client, Opportunity, Campaign, Proposal,
                      WebsiteProject, MediaJob, Approval, MessageDraft, AuditEvent, AIRun)
from ..schemas import (BusinessIn, MemberIn, LeadIn, LeadPatch, LeadOut, TaskIn, TaskPatch,
                       ClientIn, OpportunityIn, CampaignIn, ProposalIn, WebsiteIn, MediaIn,
                       LeadImport, ClientPatch, OpportunityPatch, CampaignPatch, ProposalPatch)
from ..security import Principal, Context, authenticate, get_context, require_role, ensure_tenant_object
from ..services.audit import record
from ..services.scoring import score_lead, opportunity_score
from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["business"])
DB = Annotated[Session, Depends(get_db)]
CTX = Annotated[Context, Depends(get_context)]


def asdict(obj):
    return {col.key: (float(val) if isinstance((val := getattr(obj, col.key)), Decimal) else val)
            for col in obj.__table__.columns}


def save(db: Session, item, ctx: Context, event: str):
    db.add(item)
    db.flush()
    record(db, ctx, event, item.__tablename__, item.id)
    # No tenant-scoped refresh after commit: transaction-local PostgreSQL RLS
    # context is cleared at COMMIT, and a new SELECT would be denied.
    result = asdict(item)
    db.commit()
    return result


def list_items(db: Session, ctx: Context, model, limit: int = 50, offset: int = 0):
    require_role(ctx, "viewer")
    return [asdict(x) for x in db.scalars(select(model).where(model.business_id == ctx.business_id)
                                        .order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)).all()]


def tenant_fk(db: Session, ctx: Context, model, id_: str | None):
    if id_:
        ensure_tenant_object(db, model, ctx.business_id, id_)


@router.get("/me")
def me(principal: Annotated[Principal, Depends(authenticate)], db: DB):
    ms = db.scalars(select(Membership).where(Membership.subject == principal.subject)).all()
    return {"subject": principal.subject, "email": principal.email,
            "businesses": [{"id": m.business_id, "role": m.role, "name": db.get(Business, m.business_id).name} for m in ms]}


@router.post("/setup", status_code=201)
def setup(payload: BusinessIn, principal: Annotated[Principal, Depends(authenticate)], db: DB):
    if not settings.bootstrap_admin_email or not principal.email_verified or principal.email != settings.bootstrap_admin_email:
        raise HTTPException(403, "Only the verified bootstrap administrator can initialize RevenueOS")
    # PostgreSQL lock serializes concurrent first-install calls. SQLite path is for isolated tests only.
    if db.bind.dialect.name == "postgresql":
        db.execute(__import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(7814569)"))
    existing = db.scalar(select(Business).limit(1))
    if existing:
        raise HTTPException(409, "Workspace already initialized")
    business = Business(name=payload.name, industry=payload.industry)
    db.add(business)
    db.flush()
    db.add(Membership(business_id=business.id, subject=principal.subject, email=principal.email, role="admin"))
    db.commit()
    return {"id": business.id, "name": business.name}


@router.post("/businesses", status_code=201)
def create_business(payload: BusinessIn, ctx: CTX, db: DB):
    require_role(ctx, "admin")
    business = Business(name=payload.name, industry=payload.industry)
    db.add(business)
    db.flush()
    db.add(Membership(business_id=business.id, subject=ctx.subject, email=ctx.email, role="admin"))
    db.commit()
    return {"id": business.id, "name": business.name}


@router.post("/members", status_code=201)
def add_member(payload: MemberIn, ctx: CTX, db: DB):
    require_role(ctx, "admin")
    m = Membership(business_id=ctx.business_id, subject=payload.subject, email=str(payload.email), role=payload.role)
    try:
        return save(db, m, ctx, "member.add")
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Member already exists") from exc


@router.get("/members")
def members(ctx: CTX, db: DB):
    require_role(ctx, "admin")
    return [{"id": m.id, "email": m.email, "role": m.role, "subject": m.subject}
            for m in db.scalars(select(Membership).where(Membership.business_id == ctx.business_id))]


@router.get("/leads")
def leads(ctx: CTX, db: DB, stage: str | None = None, limit: int = Query(50, ge=1, le=100),
          offset: int = Query(0, ge=0), q: str = Query("", max_length=180)):
    require_role(ctx, "viewer")
    stmt = select(Lead).where(Lead.business_id == ctx.business_id)
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    if q:
        stmt = stmt.where(Lead.business_name.icontains(q, autoescape=True))
    return [asdict(x) for x in db.scalars(stmt.order_by(Lead.created_at.desc(), Lead.id).offset(offset).limit(limit))]


@router.post("/leads", status_code=201)
def create_lead(payload: LeadIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    metrics = dict(payload.metrics)
    scoring = score_lead(metrics)
    item = Lead(business_id=ctx.business_id, business_name=payload.business_name, industry=payload.industry,
                website=str(payload.website) if payload.website else None, phone=payload.phone,
                email=str(payload.email) if payload.email else None, location=payload.location,
                source=payload.source, external_id=payload.external_id,
                metrics=metrics, score=scoring.score, grade=scoring.grade,
                score_confidence=scoring.confidence, opted_out=payload.opted_out,
                lawful_basis=payload.lawful_basis, lawful_basis_note=payload.lawful_basis_note)
    try:
        return save(db, item, ctx, "lead.create")
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Duplicate external lead identifier") from exc


@router.get("/leads/{lead_id}")
def get_lead(lead_id: str, ctx: CTX, db: DB):
    require_role(ctx, "viewer")
    return asdict(ensure_tenant_object(db, Lead, ctx.business_id, lead_id))


@router.post("/leads/import", status_code=201)
def import_leads(payload: LeadImport, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    imported = 0
    skipped = 0
    for lead in payload.leads:
        if lead.external_id and db.scalar(select(Lead.id).where(Lead.business_id == ctx.business_id,
                Lead.source == lead.source, Lead.external_id == lead.external_id)):
            skipped += 1
            continue
        score = score_lead(lead.metrics)
        values = lead.model_dump(mode="json")
        db.add(Lead(business_id=ctx.business_id, **values, score=score.score,
                    grade=score.grade, score_confidence=score.confidence))
        db.flush()
        imported += 1
    record(db, ctx, "lead.import", "leads", ctx.business_id, {"imported": imported, "skipped": skipped})
    db.commit()
    return {"imported": imported, "skipped": skipped}


@router.patch("/leads/{lead_id}")
def update_lead(lead_id: str, payload: LeadPatch, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    obj = ensure_tenant_object(db, Lead, ctx.business_id, lead_id)
    data = payload.model_dump(exclude_unset=True)
    for k in ("business_name", "industry", "website", "email", "phone", "location", "stage", "opted_out", "lawful_basis", "lawful_basis_note"):
        if k in data:
            setattr(obj, k, str(data[k]) if k in {"website", "email"} and data[k] is not None else data[k])
    if "metrics" in data and data["metrics"] is not None:
        score = score_lead(data["metrics"])
        obj.metrics, obj.score, obj.grade, obj.score_confidence = data["metrics"], score.score, score.grade, score.confidence
    record(db, ctx, "lead.update", "leads", obj.id, {"fields": list(data)})
    db.commit()
    return asdict(obj)


@router.get("/tasks")
def tasks(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, Task, limit, offset)


@router.post("/tasks", status_code=201)
def create_task(payload: TaskIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    tenant_fk(db, ctx, Lead, payload.lead_id)
    return save(db, Task(business_id=ctx.business_id, **payload.model_dump()), ctx, "task.create")


@router.patch("/tasks/{task_id}")
def patch_task(task_id: str, payload: TaskPatch, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    item = ensure_tenant_object(db, Task, ctx.business_id, task_id)
    item.status = payload.status
    record(db, ctx, "task.update", "tasks", item.id, {"status": item.status})
    db.commit()
    return asdict(item)


@router.get("/clients")
def clients(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, Client, limit, offset)


@router.post("/clients", status_code=201)
def create_client(payload: ClientIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    tenant_fk(db, ctx, Lead, payload.lead_id)
    return save(db, Client(business_id=ctx.business_id, **payload.model_dump()), ctx, "client.create")


@router.get("/opportunities")
def opportunities(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, Opportunity, limit, offset)


@router.post("/opportunities", status_code=201)
def create_opportunity(payload: OpportunityIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    tenant_fk(db, ctx, Lead, payload.lead_id)
    return save(db, Opportunity(business_id=ctx.business_id, **payload.model_dump()), ctx, "opportunity.create")


@router.get("/campaigns")
def campaigns(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, Campaign, limit, offset)


@router.post("/campaigns", status_code=201)
def create_campaign(payload: CampaignIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    return save(db, Campaign(business_id=ctx.business_id, **payload.model_dump()), ctx, "campaign.draft")


@router.get("/proposals")
def proposals(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, Proposal, limit, offset)


@router.post("/proposals", status_code=201)
def create_proposal(payload: ProposalIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    tenant_fk(db, ctx, Lead, payload.lead_id)
    return save(db, Proposal(business_id=ctx.business_id, **payload.model_dump()), ctx, "proposal.draft")


@router.get("/websites")
def websites(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, WebsiteProject, limit, offset)


@router.post("/websites", status_code=201)
def create_website(payload: WebsiteIn, ctx: CTX, db: DB):
    require_role(ctx, "operator")
    return save(db, WebsiteProject(business_id=ctx.business_id, **payload.model_dump()), ctx, "website.generate")


@router.get("/media")
def media(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_items(db, ctx, MediaJob, limit, offset)


@router.get("/reports/pipeline")
def pipeline(ctx: CTX, db: DB):
    lead_counts = db.execute(select(Lead.stage, func.count()).where(Lead.business_id == ctx.business_id)
                             .group_by(Lead.stage)).all()
    counts = {s: c for s, c in lead_counts}
    total = sum(counts.values())
    active = db.scalars(select(Client).where(Client.business_id == ctx.business_id, Client.active == True)).all()
    opportunities = db.scalars(select(Opportunity).where(Opportunity.business_id == ctx.business_id,
                                                         Opportunity.stage == "open")).all()
    done_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.business_id == ctx.business_id,
                                                                         Task.status == "done"))
    return {"lead_volume": total, "stages": counts, "conversion_rate": round(100 * counts.get("client", 0) / total, 2) if total else None,
            "clients_active": len(active), "mrr": round(sum(float(x.monthly_revenue) for x in active), 2),
            "pipeline_value": round(sum(float(o.value) for o in opportunities), 2),
            "tasks_completed": done_tasks, "notes": ["Revenue is user-entered, not bank verified", "Pipeline excludes closed opportunities"]}


@router.get("/dashboard")
def dashboard(ctx: CTX, db: DB):
    stats = pipeline(ctx, db)
    now = datetime.now(timezone.utc)
    due = db.scalars(select(Task).where(Task.business_id == ctx.business_id, Task.status != "done",
                                            Task.due_at <= now).order_by(Task.due_at).limit(10)).all()
    pending = db.scalars(select(Approval).where(Approval.business_id == ctx.business_id,
                                                Approval.decision == "pending").order_by(Approval.created_at.desc()).limit(10)).all()
    return {**stats, "due_tasks": [asdict(t) for t in due], "pending_approvals": [asdict(a) for a in pending]}


def patch_record(db, ctx, model, id_, payload, event):
    require_role(ctx, "operator")
    item = ensure_tenant_object(db, model, ctx.business_id, id_)
    values = payload.model_dump(exclude_unset=True, mode="json")
    nullable = {"email", "amount"}
    if any(value is None and key not in nullable for key, value in values.items()):
        raise HTTPException(422, "Required fields cannot be set to null")
    for key, value in values.items():
        setattr(item, key, value)
    record(db, ctx, event, model.__tablename__, item.id, {"fields": list(values)})
    db.flush()
    result = asdict(item)
    db.commit()
    return result


@router.patch("/clients/{id_}")
def patch_client(id_: str, payload: ClientPatch, ctx: CTX, db: DB):
    return patch_record(db, ctx, Client, id_, payload, "client.update")


@router.patch("/opportunities/{id_}")
def patch_opportunity(id_: str, payload: OpportunityPatch, ctx: CTX, db: DB):
    return patch_record(db, ctx, Opportunity, id_, payload, "opportunity.update")


@router.patch("/campaigns/{id_}")
def patch_campaign(id_: str, payload: CampaignPatch, ctx: CTX, db: DB):
    return patch_record(db, ctx, Campaign, id_, payload, "campaign.update")


@router.patch("/proposals/{id_}")
def patch_proposal(id_: str, payload: ProposalPatch, ctx: CTX, db: DB):
    return patch_record(db, ctx, Proposal, id_, payload, "proposal.update")


@router.get("/audit-events")
def audit_events(ctx: CTX, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    require_role(ctx, "admin")
    return list_items(db, ctx, AuditEvent, limit, offset)


@router.get("/ai/usage")
def ai_usage(ctx: CTX, db: DB):
    require_role(ctx, "operator")
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(AIRun).where(AIRun.business_id == ctx.business_id,
        AIRun.subject == ctx.subject, AIRun.created_at >= today)) or 0
    return {"runs_today": count, "daily_limit": settings.ai_daily_run_limit,
            "remaining": max(0, settings.ai_daily_run_limit - count),
            "enabled": settings.ai_enabled, "scope": "workspace and user", "resets": "00:00 UTC"}


@router.get("/workspace/export")
def export_workspace(ctx: CTX, db: DB):
    require_role(ctx, "admin")
    data = {}
    for model in (Lead, Client, Opportunity, Task, Campaign, Proposal, WebsiteProject, MediaJob, Approval, MessageDraft):
        items = db.scalars(select(model).where(model.business_id == ctx.business_id).order_by(model.id).limit(10001)).all()
        if len(items) > 10000:
            raise HTTPException(413, "Workspace exceeds interactive export size; request a managed export")
        data[model.__tablename__] = [asdict(item) for item in items]
    record(db, ctx, "workspace.export", "businesses", ctx.business_id)
    db.commit()
    return {"business_id": ctx.business_id, "exported_at": datetime.now(timezone.utc),
            "schema_version": 1, "records": data}
