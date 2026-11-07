from sqlalchemy.orm import Session
from ..models import AuditEvent
from ..security import Context

def record(db: Session, ctx: Context, action: str, obj_type: str, obj_id: str, details: dict | None = None) -> None:
    db.add(AuditEvent(business_id=ctx.business_id, subject=ctx.subject, action=action,
                      resource_type=obj_type, resource_id=obj_id, details=details or {}))
