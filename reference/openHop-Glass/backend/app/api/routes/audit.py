import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.session import get_db_session
from app.schemas.audit import AuditRecordResponse
from app.security.deps import require_roles

router = APIRouter(prefix="/api/audit")


@router.get("", response_model=list[AuditRecordResponse])
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AuditRecordResponse]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).all()
    return [
        AuditRecordResponse(
            id=row.id,
            user_id=row.user_id,
            timestamp=row.timestamp,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            details=json.loads(row.details_json or "{}"),
        )
        for row in rows
    ]

