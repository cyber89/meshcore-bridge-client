import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import User
from app.security.passwords import hash_password
from app.services.audit import write_audit_log

logger = logging.getLogger(__name__)


def seed_default_admin_if_needed(
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> None:
    if not settings.bootstrap_seed_admin_enabled:
        return

    email = settings.bootstrap_seed_admin_email.strip().lower()
    password = settings.bootstrap_seed_admin_password
    display_name = settings.bootstrap_seed_admin_display_name.strip() or None

    if not email:
        raise RuntimeError(
            "BOOTSTRAP_SEED_ADMIN_EMAIL must be set when BOOTSTRAP_SEED_ADMIN_ENABLED is true"
        )
    if not password:
        raise RuntimeError(
            "BOOTSTRAP_SEED_ADMIN_PASSWORD must be set when BOOTSTRAP_SEED_ADMIN_ENABLED is true"
        )
    if len(password) < settings.auth_password_min_length:
        raise RuntimeError(
            "BOOTSTRAP_SEED_ADMIN_PASSWORD is shorter than AUTH_PASSWORD_MIN_LENGTH"
        )

    with session_factory() as db:
        total_users = db.scalar(select(func.count()).select_from(User)) or 0
        if total_users > 0:
            return

        user = User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            display_name=display_name,
            is_active=1,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("Skipping bootstrap admin seed; user already exists")
            return

        write_audit_log(
            db,
            action="bootstrap_admin_seeded",
            target_type="user",
            target_id=user.id,
            user_id=user.id,
            details={"email": user.email},
        )
        db.commit()
        logger.info("Seeded default admin user for startup bootstrap")
