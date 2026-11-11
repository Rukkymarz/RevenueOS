"""Persistent quota reservations to prevent unaccounted provider spend."""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from ..config import settings
from ..models import AIRun
from ..security import Context


def reserve(db: Session, ctx: Context, role: str) -> AIRun:
    if db.bind.dialect.name == "postgresql":
        # Serialize counts + reservations per authenticated tenant/subject.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                   {"scope": f"ai:{ctx.business_id}:{ctx.subject}"})
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(AIRun).where(AIRun.business_id == ctx.business_id,
                      AIRun.subject == ctx.subject, AIRun.created_at >= today)) or 0
    if count >= settings.ai_daily_run_limit:
        raise HTTPException(status_code=429, detail="Daily AI run limit reached")
    entry = AIRun(business_id=ctx.business_id, subject=ctx.subject, role=role,
                  provider="pending", model="pending", status="reserved")
    db.add(entry)
    db.commit()
    return entry


def _scope(db: Session, entry: AIRun) -> None:
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.business_id', :business_id, true)"),
                   {"business_id": entry.business_id})


def complete(db: Session, entry: AIRun, answer) -> None:
    _scope(db, entry)
    entry.status = "completed"
    entry.provider = answer.provider
    entry.model = answer.model
    entry.input_tokens = answer.input_tokens
    entry.output_tokens = answer.output_tokens
    db.commit()


def fail(db: Session, entry: AIRun) -> None:
    _scope(db, entry)
    entry.status = "failed"
    entry.error = "Provider unavailable or failed"
    db.commit()
