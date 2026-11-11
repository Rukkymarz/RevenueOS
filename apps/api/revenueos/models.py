import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    industry: Mapped[str] = mapped_column(String(80), default="services")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    subject: Mapped[str] = mapped_column(String(180), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(24), default="viewer")
    __table_args__ = (UniqueConstraint("business_id", "subject"), CheckConstraint("role IN ('admin','manager','operator','viewer')"),)


class TenantRecord:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Lead(TenantRecord, Base):
    __tablename__ = "leads"
    business_name: Mapped[str] = mapped_column(String(180))
    industry: Mapped[str] = mapped_column(String(100), default="other")
    website: Mapped[str | None] = mapped_column(String(1024))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(48))
    location: Mapped[str | None] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(32), default="new")
    source: Mapped[str] = mapped_column(String(80), default="manual")
    external_id: Mapped[str | None] = mapped_column(String(180))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(12), default="Unscored")
    score_confidence: Mapped[int] = mapped_column(Integer, default=0)
    last_contact: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    lawful_basis: Mapped[str | None] = mapped_column(String(50))
    lawful_basis_note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("business_id", "source", "external_id", name="uq_lead_external"), Index("ix_lead_business_stage", "business_id", "stage"))


class Contact(TenantRecord, Base):
    __tablename__ = "contacts"
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(48))
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)


class Client(TenantRecord, Base):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(180))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    email: Mapped[str | None] = mapped_column(String(254))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    renewal_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Opportunity(TenantRecord, Base):
    __tablename__ = "opportunities"
    name: Mapped[str] = mapped_column(String(180))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    probability: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(32), default="open")
    expected_close: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(TenantRecord, Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="open")
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    assigned_subject: Mapped[str | None] = mapped_column(String(180))


class Campaign(TenantRecord, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(180))
    channel: Mapped[str] = mapped_column(String(50))
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    content: Mapped[dict] = mapped_column(JSON, default=dict)


class Proposal(TenantRecord, Base):
    __tablename__ = "proposals"
    title: Mapped[str] = mapped_column(String(180))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))
    content: Mapped[str] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(24), default="draft")


class WebsiteProject(TenantRecord, Base):
    __tablename__ = "websites"
    company: Mapped[str] = mapped_column(String(180))
    industry: Mapped[str] = mapped_column(String(100))
    tagline: Mapped[str] = mapped_column(String(240))
    contact_email: Mapped[str] = mapped_column(String(254))
    city: Mapped[str] = mapped_column(String(120))
    services: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="generated")


class MediaJob(TenantRecord, Base):
    __tablename__ = "media_jobs"
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(180))
    subtitle: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    output_file: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(String(255))


class Approval(TenantRecord, Base):
    __tablename__ = "approvals"
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(70))
    resource_id: Mapped[str] = mapped_column(String(36))
    requested_by: Mapped[str] = mapped_column(String(180))
    decided_by: Mapped[str | None] = mapped_column(String(180))
    decision: Mapped[str] = mapped_column(String(24), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(240))
    review_hash: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("business_id", "action", "resource_type", "resource_id"),)


class MessageDraft(TenantRecord, Base):
    __tablename__ = "message_drafts"
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    recipient_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    provider_id: Mapped[str | None] = mapped_column(String(160))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(TenantRecord, Base):
    __tablename__ = "audit_events"
    subject: Mapped[str] = mapped_column(String(180))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class IntegrationEvent(TenantRecord, Base):
    __tablename__ = "integration_events"
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(160))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("business_id", "source", "external_id"),)


class Knowledge(TenantRecord, Base):
    __tablename__ = "knowledge"
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    # pgvector embedding is added in the PostgreSQL migration; this ORM omits it to support SQLite unit tests.


class Workflow(TenantRecord, Base):
    __tablename__ = "workflows"
    name: Mapped[str] = mapped_column(String(150))
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentMemory(TenantRecord, Base):
    __tablename__ = "agent_memory"
    role: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(150))
    value: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("business_id", "role", "key"),)


class AIRun(TenantRecord, Base):
    __tablename__ = "ai_runs"
    subject: Mapped[str] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(200))
