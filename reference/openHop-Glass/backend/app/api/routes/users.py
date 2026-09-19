from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db_session
from app.schemas.users import UserCreateRequest, UserManagementResponse, UserUpdateRequest
from app.security.deps import require_roles
from app.security.passwords import hash_password
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/users")


def _to_response(user: User) -> UserManagementResponse:
    return UserManagementResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active == 1,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=list[UserManagementResponse])
def list_users(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin")),
) -> list[UserManagementResponse]:
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return [_to_response(user) for user in users]


@router.post("", response_model=UserManagementResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin")),
) -> UserManagementResponse:
    settings = get_settings()
    if len(payload.password) < settings.auth_password_min_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {settings.auth_password_min_length} characters",
        )

    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role=payload.role.strip(),
        display_name=payload.display_name,
        is_active=1 if payload.is_active else 0,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        ) from exc

    write_audit_log(
        db,
        action="user_created",
        target_type="user",
        target_id=user.id,
        user_id=current_user.id,
        details={"email": user.email, "role": user.role, "is_active": user.is_active == 1},
    )
    db.commit()
    db.refresh(user)
    return _to_response(user)


@router.patch("/{user_id}", response_model=UserManagementResponse)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin")),
) -> UserManagementResponse:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.is_active is False and user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable your own account",
        )

    changes: dict[str, object] = {}
    if payload.role is not None:
        user.role = payload.role.strip()
        changes["role"] = user.role
    if payload.display_name is not None:
        user.display_name = payload.display_name
        changes["display_name"] = user.display_name
    if payload.is_active is not None:
        user.is_active = 1 if payload.is_active else 0
        changes["is_active"] = user.is_active == 1
    if payload.password is not None:
        settings = get_settings()
        if len(payload.password) < settings.auth_password_min_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password must be at least {settings.auth_password_min_length} characters",
            )
        user.password_hash = hash_password(payload.password)
        changes["password_reset"] = True

    write_audit_log(
        db,
        action="user_updated",
        target_type="user",
        target_id=user.id,
        user_id=current_user.id,
        details={"changes": changes},
    )
    db.commit()
    db.refresh(user)
    return _to_response(user)
