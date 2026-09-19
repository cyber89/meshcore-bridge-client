from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Repeater, TransportKey, TransportKeyGroup, TransportKeySyncStatus, User
from app.db.session import get_db_session
from app.schemas.transport_keys import (
    TransportKeyCreateRequest,
    TransportKeyGroupCreateRequest,
    TransportKeyGroupMoveRequest,
    TransportKeyGroupResponse,
    TransportKeyGroupUpdateRequest,
    TransportKeyResponse,
    TransportKeySyncStatusResponse,
    TransportKeySyncTriggerResponse,
    TransportKeyTreeNodeResponse,
    TransportKeyTreeResponse,
    TransportKeyUpdateRequest,
)
from app.security.deps import require_roles
from app.services.audit import write_audit_log
from app.services.transport_keys import queue_transport_key_sync_for_fleet

router = APIRouter(prefix="/api/transport-keys")


def _to_group_response(group: TransportKeyGroup) -> TransportKeyGroupResponse:
    return TransportKeyGroupResponse(
        id=group.id,
        name=group.name,
        parent_group_id=group.parent_group_id,
        flood_policy=group.flood_policy,
        transport_key=group.transport_key,
        sort_order=group.sort_order,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _to_key_response(key: TransportKey) -> TransportKeyResponse:
    return TransportKeyResponse(
        id=key.id,
        name=key.name,
        group_id=key.group_id,
        flood_policy=key.flood_policy,
        transport_key=key.transport_key,
        sort_order=key.sort_order,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


def _name_is_used(
    db: Session,
    *,
    candidate: str,
    group_exclude_id: str | None = None,
    key_exclude_id: str | None = None,
) -> bool:
    normalized = candidate.strip().lower()
    group_query = select(TransportKeyGroup.id).where(
        func.lower(TransportKeyGroup.name) == normalized,
    )
    if group_exclude_id:
        group_query = group_query.where(TransportKeyGroup.id != group_exclude_id)
    group_match = db.scalar(group_query)
    if group_match is not None:
        return True
    key_query = select(TransportKey.id).where(func.lower(TransportKey.name) == normalized)
    if key_exclude_id:
        key_query = key_query.where(TransportKey.id != key_exclude_id)
    key_match = db.scalar(key_query)
    return key_match is not None


def _load_group_or_404(db: Session, group_id: str) -> TransportKeyGroup:
    group = db.scalar(select(TransportKeyGroup).where(TransportKeyGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transport key group not found")
    return group


def _load_key_or_404(db: Session, key_id: str) -> TransportKey:
    key = db.scalar(select(TransportKey).where(TransportKey.id == key_id))
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transport key not found")
    return key


def _validate_group_parent(
    db: Session,
    *,
    group_id: str,
    parent_group_id: str | None,
) -> None:
    if parent_group_id is None:
        return
    if parent_group_id == group_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A group cannot be its own parent",
        )
    current = _load_group_or_404(db, parent_group_id)
    while current.parent_group_id is not None:
        if current.parent_group_id == group_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid parent assignment: cycle detected",
            )
        current = _load_group_or_404(db, current.parent_group_id)


def _descendant_group_ids(db: Session, group_id: str) -> set[str]:
    rows = db.execute(select(TransportKeyGroup.id, TransportKeyGroup.parent_group_id)).all()
    children_by_parent: dict[str, list[str]] = {}
    for child_id, parent_id in rows:
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(child_id)
    descendants: set[str] = set()
    queue = list(children_by_parent.get(group_id, []))
    while queue:
        current = queue.pop(0)
        if current in descendants:
            continue
        descendants.add(current)
        queue.extend(children_by_parent.get(current, []))
    return descendants


def _tree_nodes(db: Session) -> list[TransportKeyTreeNodeResponse]:
    groups = db.scalars(
        select(TransportKeyGroup).order_by(TransportKeyGroup.sort_order.asc(), TransportKeyGroup.name.asc())
    ).all()
    keys = db.scalars(select(TransportKey).order_by(TransportKey.sort_order.asc(), TransportKey.name.asc())).all()
    nodes: list[TransportKeyTreeNodeResponse] = []
    for group in groups:
        nodes.append(
            TransportKeyTreeNodeResponse(
                id=group.id,
                kind="group",
                name=group.name,
                flood_policy=group.flood_policy,
                transport_key=group.transport_key,
                parent_id=group.parent_group_id,
                sort_order=group.sort_order,
                created_at=group.created_at,
                updated_at=group.updated_at,
                last_used_at=None,
            )
        )
    for key in keys:
        nodes.append(
            TransportKeyTreeNodeResponse(
                id=key.id,
                kind="key",
                name=key.name,
                flood_policy=key.flood_policy,
                transport_key=key.transport_key,
                parent_id=key.group_id,
                sort_order=key.sort_order,
                created_at=key.created_at,
                updated_at=key.updated_at,
                last_used_at=key.last_used_at,
            )
        )
    return nodes


def _sync_status_rows(db: Session) -> list[TransportKeySyncStatusResponse]:
    rows = db.execute(
        select(Repeater, TransportKeySyncStatus)
        .outerjoin(TransportKeySyncStatus, TransportKeySyncStatus.repeater_id == Repeater.id)
        .order_by(Repeater.node_name.asc())
    ).all()
    return [
        TransportKeySyncStatusResponse(
            repeater_id=repeater.id,
            node_name=repeater.node_name,
            status=status_row.status if status_row else "idle",
            payload_hash=status_row.payload_hash if status_row else None,
            command_id=status_row.command_id if status_row else None,
            error_message=status_row.error_message if status_row else None,
            queued_at=status_row.queued_at if status_row else None,
            dispatched_at=status_row.dispatched_at if status_row else None,
            completed_at=status_row.completed_at if status_row else None,
            updated_at=status_row.updated_at if status_row else None,
        )
        for repeater, status_row in rows
    ]


def _queue_sync(
    db: Session,
    *,
    requested_by: str,
    action: str,
    target_type: str,
    target_id: str | None,
    user_id: str | None,
    details: dict,
) -> TransportKeySyncTriggerResponse:
    dispatch = queue_transport_key_sync_for_fleet(db, requested_by=requested_by)
    write_audit_log(
        db,
        action=action,
        target_type=target_type,
        target_id=target_id,
        user_id=user_id,
        details={
            **details,
            "payload_hash": dispatch.payload_hash,
            "queued_commands": dispatch.queued_commands,
            "skipped_commands": dispatch.skipped_commands,
        },
    )
    return TransportKeySyncTriggerResponse(
        payload_hash=dispatch.payload_hash,
        queued_commands=dispatch.queued_commands,
        skipped_commands=dispatch.skipped_commands,
    )


@router.get("/tree", response_model=TransportKeyTreeResponse)
def get_transport_key_tree(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> TransportKeyTreeResponse:
    return TransportKeyTreeResponse(nodes=_tree_nodes(db), sync_status=_sync_status_rows(db))


@router.get("/groups", response_model=list[TransportKeyGroupResponse])
def list_transport_key_groups(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[TransportKeyGroupResponse]:
    groups = db.scalars(
        select(TransportKeyGroup).order_by(TransportKeyGroup.sort_order.asc(), TransportKeyGroup.name.asc())
    ).all()
    return [_to_group_response(group) for group in groups]


@router.post("/groups", response_model=TransportKeyGroupResponse, status_code=status.HTTP_201_CREATED)
def create_transport_key_group(
    payload: TransportKeyGroupCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeyGroupResponse:
    name = payload.name.strip()
    if _name_is_used(db, candidate=name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transport key/group name already exists")
    if payload.parent_group_id:
        _load_group_or_404(db, payload.parent_group_id)
    group = TransportKeyGroup(
        name=name,
        parent_group_id=payload.parent_group_id,
        flood_policy=payload.flood_policy,
        transport_key=payload.transport_key,
        sort_order=payload.sort_order,
    )
    db.add(group)
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_group_created",
        target_type="transport_key_group",
        target_id=group.id,
        user_id=current_user.id,
        details={"name": group.name},
    )
    db.commit()
    db.refresh(group)
    return _to_group_response(group)


@router.patch("/groups/{group_id}", response_model=TransportKeyGroupResponse)
def update_transport_key_group(
    group_id: str,
    payload: TransportKeyGroupUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeyGroupResponse:
    group = _load_group_or_404(db, group_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        candidate = str(changes["name"]).strip()
        if _name_is_used(db, candidate=candidate, group_exclude_id=group.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transport key/group name already exists",
            )
        group.name = candidate
    if "parent_group_id" in changes:
        _validate_group_parent(db, group_id=group.id, parent_group_id=changes["parent_group_id"])
        group.parent_group_id = changes["parent_group_id"]
    if "flood_policy" in changes and changes["flood_policy"] is not None:
        group.flood_policy = changes["flood_policy"]
    if "transport_key" in changes:
        group.transport_key = changes["transport_key"]
    if "sort_order" in changes and changes["sort_order"] is not None:
        group.sort_order = int(changes["sort_order"])
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_group_updated",
        target_type="transport_key_group",
        target_id=group.id,
        user_id=current_user.id,
        details={"changes": changes},
    )
    db.commit()
    db.refresh(group)
    return _to_group_response(group)


@router.post("/groups/{group_id}/move", response_model=TransportKeyGroupResponse)
def move_transport_key_group(
    group_id: str,
    payload: TransportKeyGroupMoveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeyGroupResponse:
    group = _load_group_or_404(db, group_id)
    _validate_group_parent(db, group_id=group.id, parent_group_id=payload.parent_group_id)
    group.parent_group_id = payload.parent_group_id
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_group_moved",
        target_type="transport_key_group",
        target_id=group.id,
        user_id=current_user.id,
        details={
            "parent_group_id": payload.parent_group_id,
            "sort_order": payload.sort_order,
        },
    )
    db.commit()
    db.refresh(group)
    return _to_group_response(group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transport_key_group(
    group_id: str,
    reassign_to_group_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    group = _load_group_or_404(db, group_id)
    if reassign_to_group_id is not None:
        if reassign_to_group_id == group.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot reassign a group to itself",
            )
        descendants = _descendant_group_ids(db, group.id)
        if reassign_to_group_id in descendants:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot reassign to a descendant group",
            )
        _load_group_or_404(db, reassign_to_group_id)
        direct_children = db.scalars(
            select(TransportKeyGroup).where(TransportKeyGroup.parent_group_id == group.id)
        ).all()
        for child in direct_children:
            child.parent_group_id = reassign_to_group_id
        direct_keys = db.scalars(select(TransportKey).where(TransportKey.group_id == group.id)).all()
        for key in direct_keys:
            key.group_id = reassign_to_group_id
        db.delete(group)
    else:
        descendants = _descendant_group_ids(db, group.id)
        subtree_ids = descendants | {group.id}
        keys = db.scalars(select(TransportKey).where(TransportKey.group_id.in_(subtree_ids))).all()
        for key in keys:
            db.delete(key)
        groups = db.scalars(select(TransportKeyGroup).where(TransportKeyGroup.id.in_(subtree_ids))).all()
        for child_group in groups:
            db.delete(child_group)

    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_group_deleted",
        target_type="transport_key_group",
        target_id=group_id,
        user_id=current_user.id,
        details={"reassign_to_group_id": reassign_to_group_id},
    )
    db.commit()


@router.get("/keys", response_model=list[TransportKeyResponse])
def list_transport_keys(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[TransportKeyResponse]:
    keys = db.scalars(select(TransportKey).order_by(TransportKey.sort_order.asc(), TransportKey.name.asc())).all()
    return [_to_key_response(key) for key in keys]


@router.post("/keys", response_model=TransportKeyResponse, status_code=status.HTTP_201_CREATED)
def create_transport_key(
    payload: TransportKeyCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeyResponse:
    name = payload.name.strip()
    if _name_is_used(db, candidate=name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transport key/group name already exists")
    if payload.group_id is not None:
        _load_group_or_404(db, payload.group_id)
    key = TransportKey(
        name=name,
        group_id=payload.group_id,
        flood_policy=payload.flood_policy,
        transport_key=payload.transport_key,
        sort_order=payload.sort_order,
    )
    db.add(key)
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_created",
        target_type="transport_key",
        target_id=key.id,
        user_id=current_user.id,
        details={"name": key.name},
    )
    db.commit()
    db.refresh(key)
    return _to_key_response(key)


@router.patch("/keys/{key_id}", response_model=TransportKeyResponse)
def update_transport_key(
    key_id: str,
    payload: TransportKeyUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeyResponse:
    key = _load_key_or_404(db, key_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        candidate = str(changes["name"]).strip()
        if _name_is_used(db, candidate=candidate, key_exclude_id=key.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transport key/group name already exists",
            )
        key.name = candidate
    if "group_id" in changes:
        if changes["group_id"] is not None:
            _load_group_or_404(db, changes["group_id"])
        key.group_id = changes["group_id"]
    if "flood_policy" in changes and changes["flood_policy"] is not None:
        key.flood_policy = changes["flood_policy"]
    if "transport_key" in changes:
        key.transport_key = changes["transport_key"]
    if "sort_order" in changes and changes["sort_order"] is not None:
        key.sort_order = int(changes["sort_order"])
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_updated",
        target_type="transport_key",
        target_id=key.id,
        user_id=current_user.id,
        details={"changes": changes},
    )
    db.commit()
    db.refresh(key)
    return _to_key_response(key)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transport_key(
    key_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    key = _load_key_or_404(db, key_id)
    key_name = key.name
    db.delete(key)
    db.flush()
    _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_deleted",
        target_type="transport_key",
        target_id=key_id,
        user_id=current_user.id,
        details={"name": key_name},
    )
    db.commit()


@router.post("/sync", response_model=TransportKeySyncTriggerResponse)
def trigger_transport_key_sync(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> TransportKeySyncTriggerResponse:
    response = _queue_sync(
        db,
        requested_by=current_user.email,
        action="transport_key_sync_triggered",
        target_type="transport_keys",
        target_id=None,
        user_id=current_user.id,
        details={"source": "manual"},
    )
    db.commit()
    return response

