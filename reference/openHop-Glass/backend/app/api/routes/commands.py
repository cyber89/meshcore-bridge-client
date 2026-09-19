import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.v1.command import QueueCommandRequestV1, QueueCommandResponseV1
from app.db.models import CommandQueueItem, Repeater, User
from app.db.session import get_db_session
from app.schemas.commands import CommandQueueItemResponse
from app.security.deps import require_roles
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/commands")


def _to_response(item: CommandQueueItem, node_name: str) -> CommandQueueItemResponse:
    return CommandQueueItemResponse(
        command_id=item.id,
        repeater_id=item.repeater_id,
        node_name=node_name,
        action=item.command,
        status=item.status,
        params=json.loads(item.params_json or "{}"),
        result=json.loads(item.result_json) if item.result_json else None,
        requested_by=item.requested_by,
        created_at=item.created_at,
        completed_at=item.completed_at,
    )


@router.post("", response_model=QueueCommandResponseV1, status_code=status.HTTP_201_CREATED)
def queue_command(
    payload: QueueCommandRequestV1,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> QueueCommandResponseV1:
    repeater = db.scalar(select(Repeater).where(Repeater.node_name == payload.node_name))
    if repeater is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")

    item = CommandQueueItem(
        repeater_id=repeater.id,
        command=payload.action.value,
        params_json=json.dumps(payload.params),
        status="queued",
        requested_by=payload.requested_by,
    )
    db.add(item)
    db.flush()

    write_audit_log(
        db,
        action="command_queued",
        target_type="command",
        target_id=item.id,
        user_id=current_user.id,
        details={
            "node_name": repeater.node_name,
            "action": payload.action.value,
            "reason": payload.reason,
        },
    )
    db.commit()
    return QueueCommandResponseV1(
        command_id=item.id,
        node_name=repeater.node_name,
        action=payload.action,
        status=item.status,
        queued_at=item.created_at,
    )


@router.get("", response_model=list[CommandQueueItemResponse])
def list_commands(
    status_filter: str | None = Query(default=None, alias="status"),
    node_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[CommandQueueItemResponse]:
    query = (
        select(CommandQueueItem, Repeater.node_name)
        .join(Repeater, Repeater.id == CommandQueueItem.repeater_id)
        .order_by(CommandQueueItem.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(CommandQueueItem.status == status_filter)
    if node_name:
        query = query.where(Repeater.node_name == node_name)

    rows = db.execute(query).all()
    return [_to_response(item, repeater_node_name) for item, repeater_node_name in rows]


@router.get("/{command_id}", response_model=CommandQueueItemResponse)
def get_command(
    command_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> CommandQueueItemResponse:
    row = db.execute(
        select(CommandQueueItem, Repeater.node_name)
        .join(Repeater, Repeater.id == CommandQueueItem.repeater_id)
        .where(CommandQueueItem.id == command_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Command not found")

    item, repeater_node_name = row
    return _to_response(item, repeater_node_name)

