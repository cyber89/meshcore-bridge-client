from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import SystemSetting, User
from app.db.session import get_db_session
from app.schemas.bootstrap import (
    BootstrapAdminRequest,
    BootstrapAdminResponse,
    BootstrapStatusResponse,
)
from app.security.passwords import hash_password
from app.services.audit import write_audit_log
from app.services.system_settings import MANAGED_MQTT_SETTINGS_KEY

router = APIRouter(prefix="/api/bootstrap")


@router.get("/status", response_model=BootstrapStatusResponse)
def bootstrap_status(db: Session = Depends(get_db_session)) -> BootstrapStatusResponse:
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    mqtt_row = db.scalar(
        select(SystemSetting).where(SystemSetting.key == MANAGED_MQTT_SETTINGS_KEY)
    )
    return BootstrapStatusResponse(
        needs_bootstrap=total_users == 0,
        server_setup_complete=mqtt_row is not None,
    )


@router.post("/admin", response_model=BootstrapAdminResponse)
def bootstrap_admin(
    payload: BootstrapAdminRequest,
    db: Session = Depends(get_db_session),
) -> BootstrapAdminResponse:
    settings = get_settings()
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    if total_users > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap already completed",
        )

    if len(payload.password) < settings.auth_password_min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {settings.auth_password_min_length} characters",
        )

    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role="admin",
        display_name=payload.display_name,
        is_active=1,
    )
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        action="bootstrap_admin_created",
        target_type="user",
        target_id=user.id,
        user_id=user.id,
        details={"email": user.email},
    )

    db.commit()
    return BootstrapAdminResponse(user_id=user.id, email=user.email, role=user.role)

