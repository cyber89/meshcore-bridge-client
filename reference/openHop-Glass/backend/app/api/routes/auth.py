from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuthToken, User
from app.db.session import get_db_session
from app.schemas.auth import LoginRequest, LoginResponse, UserInfoResponse
from app.security.deps import bearer_scheme, get_current_user
from app.security.passwords import verify_password
from app.security.tokens import generate_token, hash_token
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/auth")


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.is_active != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User disabled")

    settings = get_settings()
    raw_token = generate_token(settings.auth_token_bytes)
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.auth_token_ttl_minutes)

    db.add(
        AuthToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    write_audit_log(
        db,
        action="auth_login",
        target_type="user",
        target_id=user.id,
        user_id=user.id,
    )
    db.commit()

    return LoginResponse(
        access_token=raw_token,
        expires_at=expires_at,
        user=UserInfoResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            display_name=user.display_name,
        ),
    )


@router.get("/me", response_model=UserInfoResponse)
def me(current_user: User = Depends(get_current_user)) -> UserInfoResponse:
    return UserInfoResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        display_name=current_user.display_name,
    )


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token_hash = hash_token(credentials.credentials)
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        write_audit_log(
            db,
            action="auth_logout",
            target_type="user",
            target_id=current_user.id,
            user_id=current_user.id,
        )
        db.commit()
    return {"success": True}

