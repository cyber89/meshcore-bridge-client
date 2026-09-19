import json
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    record = AuditLog(
        action=action,
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        details_json=json.dumps(details or {}),
    )
    db.add(record)
    return record

