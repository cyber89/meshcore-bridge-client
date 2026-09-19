from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Repeater, User
from app.db.session import get_db_session
from app.schemas.adoption import AdoptionActionRequest, AdoptionActionResponse
from app.schemas.repeater import RepeaterResponse
from app.security.deps import require_roles
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/adoption")


def _to_repeater_response(repeater: Repeater) -> RepeaterResponse:
    return RepeaterResponse(
        id=repeater.id,
        node_name=repeater.node_name,
        pubkey=repeater.pubkey,
        status=repeater.status,
        firmware_version=repeater.firmware_version,
        location=repeater.location,
        config_hash=repeater.config_hash,
        last_inform_at=repeater.last_inform_at,
        created_at=repeater.created_at,
        updated_at=repeater.updated_at,
    )


@router.get("/pending", response_model=list[RepeaterResponse])
def list_pending_adoptions(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[RepeaterResponse]:
    pending = db.scalars(
        select(Repeater)
        .where(Repeater.status == "pending_adoption")
        .order_by(Repeater.created_at.asc())
    ).all()
    return [_to_repeater_response(item) for item in pending]


@router.post("/{repeater_id}/adopt", response_model=AdoptionActionResponse)
def adopt_repeater(
    repeater_id: str,
    payload: AdoptionActionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AdoptionActionResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")

    repeater.status = "adopted"
    write_audit_log(
        db,
        action="adoption_approved",
        target_type="repeater",
        target_id=repeater.id,
        user_id=current_user.id,
        details={"note": payload.note},
    )
    db.commit()
    return AdoptionActionResponse(
        repeater_id=repeater.id,
        node_name=repeater.node_name,
        status=repeater.status,
    )


@router.post("/{repeater_id}/reject", response_model=AdoptionActionResponse)
def reject_repeater(
    repeater_id: str,
    payload: AdoptionActionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AdoptionActionResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")

    repeater.status = "rejected"
    write_audit_log(
        db,
        action="adoption_rejected",
        target_type="repeater",
        target_id=repeater.id,
        user_id=current_user.id,
        details={"note": payload.note},
    )
    db.commit()
    return AdoptionActionResponse(
        repeater_id=repeater.id,
        node_name=repeater.node_name,
        status=repeater.status,
    )

