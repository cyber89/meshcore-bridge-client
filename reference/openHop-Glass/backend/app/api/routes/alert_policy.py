import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AlertPolicyAssignment,
    AlertPolicyTemplate,
    NodeGroup,
    NodeGroupMembership,
    Repeater,
    User,
)
from app.db.session import get_db_session
from app.schemas.alert_policy import (
    AlertPolicyAssignmentCreateRequest,
    AlertPolicyAssignmentResponse,
    AlertPolicyAssignmentUpdateRequest,
    AlertPolicyEvaluationRequest,
    AlertPolicyEvaluationResponse,
    AlertPolicyTemplateCreateRequest,
    AlertPolicyTemplateResponse,
    AlertPolicyTemplateUpdateRequest,
    EffectivePolicyItemResponse,
    EffectivePolicyResponse,
    NodeGroupCreateRequest,
    NodeGroupDetailResponse,
    NodeGroupMemberAddRequest,
    NodeGroupMemberResponse,
    NodeGroupResponse,
    NodeGroupUpdateRequest,
)
from app.security.deps import require_roles
from app.services.alert_policy import (
    evaluate_policies_for_fleet,
    list_effective_policies_for_repeater,
    serialize_policy_template_config,
)
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/alert-policies")
groups_router = APIRouter(prefix="/api/node-groups")


def _to_template_response(template: AlertPolicyTemplate) -> AlertPolicyTemplateResponse:
    return AlertPolicyTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        rule_type=template.rule_type,
        severity=template.severity,
        enabled=template.enabled == 1,
        threshold_value=template.threshold_value,
        window_minutes=template.window_minutes,
        offline_grace_seconds=template.offline_grace_seconds,
        cooldown_seconds=template.cooldown_seconds,
        auto_resolve=template.auto_resolve == 1,
        config=serialize_policy_template_config(template),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _to_group_response(group: NodeGroup, member_count: int) -> NodeGroupResponse:
    return NodeGroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=member_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


def _resolve_scope_name(
    db: Session,
    *,
    scope_type: str,
    scope_id: str | None,
) -> str | None:
    if scope_type == "global":
        return "Global"
    if scope_type == "group" and scope_id:
        group = db.scalar(select(NodeGroup).where(NodeGroup.id == scope_id))
        return group.name if group else scope_id
    if scope_type == "node" and scope_id:
        repeater = db.scalar(select(Repeater).where(Repeater.id == scope_id))
        return repeater.node_name if repeater else scope_id
    return scope_id


@groups_router.get("", response_model=list[NodeGroupResponse])
def list_node_groups(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[NodeGroupResponse]:
    rows = db.execute(
        select(NodeGroup, func.count(NodeGroupMembership.id))
        .outerjoin(NodeGroupMembership, NodeGroupMembership.group_id == NodeGroup.id)
        .group_by(NodeGroup.id)
        .order_by(NodeGroup.name.asc())
    ).all()
    return [_to_group_response(group, int(member_count)) for group, member_count in rows]


@groups_router.post("", response_model=NodeGroupResponse, status_code=status.HTTP_201_CREATED)
def create_node_group(
    payload: NodeGroupCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> NodeGroupResponse:
    group = NodeGroup(name=payload.name.strip(), description=payload.description)
    db.add(group)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node group already exists",
        ) from exc
    write_audit_log(
        db,
        action="node_group_created",
        target_type="node_group",
        target_id=group.id,
        user_id=current_user.id,
        details={"name": group.name},
    )
    db.commit()
    db.refresh(group)
    return _to_group_response(group, member_count=0)


@groups_router.get("/{group_id}", response_model=NodeGroupDetailResponse)
def get_node_group(
    group_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> NodeGroupDetailResponse:
    group = db.scalar(select(NodeGroup).where(NodeGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    member_rows = db.execute(
        select(NodeGroupMembership, Repeater)
        .join(Repeater, Repeater.id == NodeGroupMembership.repeater_id)
        .where(NodeGroupMembership.group_id == group.id)
        .order_by(Repeater.node_name.asc())
    ).all()
    members = [
        NodeGroupMemberResponse(
            repeater_id=repeater.id,
            node_name=repeater.node_name,
            status=repeater.status,
            last_inform_at=repeater.last_inform_at,
        )
        for _, repeater in member_rows
    ]
    return NodeGroupDetailResponse(
        **_to_group_response(group, member_count=len(members)).model_dump(),
        members=members,
    )


@groups_router.patch("/{group_id}", response_model=NodeGroupResponse)
def update_node_group(
    group_id: str,
    payload: NodeGroupUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> NodeGroupResponse:
    group = db.scalar(select(NodeGroup).where(NodeGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        group.name = str(changes["name"]).strip()
    if "description" in changes:
        group.description = changes["description"]
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node group already exists",
        ) from exc
    member_count = db.scalar(
        select(func.count(NodeGroupMembership.id)).where(NodeGroupMembership.group_id == group.id)
    ) or 0
    write_audit_log(
        db,
        action="node_group_updated",
        target_type="node_group",
        target_id=group.id,
        user_id=current_user.id,
        details={"changes": changes},
    )
    db.commit()
    db.refresh(group)
    return _to_group_response(group, member_count=int(member_count))


@groups_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node_group(
    group_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    group = db.scalar(select(NodeGroup).where(NodeGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    group_name = group.name
    db.delete(group)
    write_audit_log(
        db,
        action="node_group_deleted",
        target_type="node_group",
        target_id=group_id,
        user_id=current_user.id,
        details={"name": group_name},
    )
    db.commit()


@groups_router.post("/{group_id}/members", response_model=NodeGroupDetailResponse)
def add_node_group_member(
    group_id: str,
    payload: NodeGroupMemberAddRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> NodeGroupDetailResponse:
    group = db.scalar(select(NodeGroup).where(NodeGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    repeater = db.scalar(select(Repeater).where(Repeater.id == payload.repeater_id))
    if repeater is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")
    existing = db.scalar(
        select(NodeGroupMembership).where(
            NodeGroupMembership.group_id == group.id,
            NodeGroupMembership.repeater_id == repeater.id,
        )
    )
    if existing is None:
        db.add(NodeGroupMembership(group_id=group.id, repeater_id=repeater.id))
        write_audit_log(
            db,
            action="node_group_member_added",
            target_type="node_group",
            target_id=group.id,
            user_id=current_user.id,
            details={"repeater_id": repeater.id, "node_name": repeater.node_name},
        )
        db.commit()
    return get_node_group(group_id, db, current_user)


@groups_router.delete("/{group_id}/members/{repeater_id}", response_model=NodeGroupDetailResponse)
def remove_node_group_member(
    group_id: str,
    repeater_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> NodeGroupDetailResponse:
    group = db.scalar(select(NodeGroup).where(NodeGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    membership = db.scalar(
        select(NodeGroupMembership).where(
            NodeGroupMembership.group_id == group.id,
            NodeGroupMembership.repeater_id == repeater_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    db.delete(membership)
    write_audit_log(
        db,
        action="node_group_member_removed",
        target_type="node_group",
        target_id=group.id,
        user_id=current_user.id,
        details={"repeater_id": repeater_id},
    )
    db.commit()
    return get_node_group(group_id, db, current_user)


@router.get("/templates", response_model=list[AlertPolicyTemplateResponse])
def list_policy_templates(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertPolicyTemplateResponse]:
    templates = db.scalars(select(AlertPolicyTemplate).order_by(AlertPolicyTemplate.name.asc())).all()
    return [_to_template_response(item) for item in templates]


@router.post("/templates", response_model=AlertPolicyTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_policy_template(
    payload: AlertPolicyTemplateCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyTemplateResponse:
    template = AlertPolicyTemplate(
        name=payload.name.strip(),
        description=payload.description,
        rule_type=payload.rule_type,
        severity=payload.severity.strip(),
        enabled=1 if payload.enabled else 0,
        threshold_value=payload.threshold_value,
        window_minutes=payload.window_minutes,
        offline_grace_seconds=payload.offline_grace_seconds,
        cooldown_seconds=payload.cooldown_seconds,
        auto_resolve=1 if payload.auto_resolve else 0,
        config_json=json.dumps(payload.config, separators=(",", ":"), sort_keys=True),
    )
    db.add(template)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert policy template already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_policy_template_created",
        target_type="alert_policy_template",
        target_id=template.id,
        user_id=current_user.id,
        details={"name": template.name, "rule_type": template.rule_type},
    )
    db.commit()
    db.refresh(template)
    return _to_template_response(template)


@router.patch("/templates/{template_id}", response_model=AlertPolicyTemplateResponse)
def update_policy_template(
    template_id: str,
    payload: AlertPolicyTemplateUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyTemplateResponse:
    template = db.scalar(select(AlertPolicyTemplate).where(AlertPolicyTemplate.id == template_id))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert policy template not found")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        template.name = str(changes.pop("name")).strip()
    if "description" in changes:
        template.description = changes.pop("description")
    if "severity" in changes and changes["severity"] is not None:
        template.severity = str(changes.pop("severity")).strip()
    if "enabled" in changes and changes["enabled"] is not None:
        template.enabled = 1 if changes.pop("enabled") else 0
    if "auto_resolve" in changes and changes["auto_resolve"] is not None:
        template.auto_resolve = 1 if changes.pop("auto_resolve") else 0
    if "config" in changes:
        config_payload = changes.pop("config")
        template.config_json = json.dumps(
            config_payload if isinstance(config_payload, dict) else {},
            separators=(",", ":"),
            sort_keys=True,
        )
    for key, value in changes.items():
        setattr(template, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert policy template already exists",
        ) from exc
    write_audit_log(
        db,
        action="alert_policy_template_updated",
        target_type="alert_policy_template",
        target_id=template.id,
        user_id=current_user.id,
        details={"changes": payload.model_dump(exclude_none=True)},
    )
    db.commit()
    db.refresh(template)
    return _to_template_response(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy_template(
    template_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    template = db.scalar(select(AlertPolicyTemplate).where(AlertPolicyTemplate.id == template_id))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert policy template not found")
    template_name = template.name
    db.delete(template)
    write_audit_log(
        db,
        action="alert_policy_template_deleted",
        target_type="alert_policy_template",
        target_id=template_id,
        user_id=current_user.id,
        details={"name": template_name},
    )
    db.commit()


@router.get("/assignments", response_model=list[AlertPolicyAssignmentResponse])
def list_policy_assignments(
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> list[AlertPolicyAssignmentResponse]:
    rows = db.execute(
        select(AlertPolicyAssignment, AlertPolicyTemplate)
        .join(AlertPolicyTemplate, AlertPolicyTemplate.id == AlertPolicyAssignment.template_id)
        .order_by(
            AlertPolicyAssignment.scope_type.asc(),
            AlertPolicyAssignment.scope_id.asc(),
            AlertPolicyAssignment.priority.desc(),
        )
    ).all()
    return [
        AlertPolicyAssignmentResponse(
            id=assignment.id,
            template_id=template.id,
            template_name=template.name,
            rule_type=template.rule_type,
            scope_type=assignment.scope_type,
            scope_id=assignment.scope_id,
            scope_name=_resolve_scope_name(
                db,
                scope_type=assignment.scope_type,
                scope_id=assignment.scope_id,
            ),
            priority=assignment.priority,
            enabled=assignment.enabled == 1,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
        )
        for assignment, template in rows
    ]


@router.post("/assignments", response_model=AlertPolicyAssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_policy_assignment(
    payload: AlertPolicyAssignmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyAssignmentResponse:
    template = db.scalar(select(AlertPolicyTemplate).where(AlertPolicyTemplate.id == payload.template_id))
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert policy template not found")
    if payload.scope_type == "global":
        scope_id = None
    else:
        if not payload.scope_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="scope_id is required for non-global assignment",
            )
        scope_id = payload.scope_id
    if payload.scope_type == "group":
        group = db.scalar(select(NodeGroup).where(NodeGroup.id == scope_id))
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node group not found")
    if payload.scope_type == "node":
        repeater = db.scalar(select(Repeater).where(Repeater.id == scope_id))
        if repeater is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")

    assignment = AlertPolicyAssignment(
        template_id=template.id,
        scope_type=payload.scope_type,
        scope_id=scope_id,
        priority=payload.priority,
        enabled=1 if payload.enabled else 0,
    )
    db.add(assignment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alert policy assignment already exists for this template and scope",
        ) from exc
    write_audit_log(
        db,
        action="alert_policy_assignment_created",
        target_type="alert_policy_assignment",
        target_id=assignment.id,
        user_id=current_user.id,
        details={
            "template_id": template.id,
            "scope_type": assignment.scope_type,
            "scope_id": assignment.scope_id,
            "priority": assignment.priority,
        },
    )
    db.commit()
    db.refresh(assignment)
    return AlertPolicyAssignmentResponse(
        id=assignment.id,
        template_id=template.id,
        template_name=template.name,
        rule_type=template.rule_type,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
        scope_name=_resolve_scope_name(
            db,
            scope_type=assignment.scope_type,
            scope_id=assignment.scope_id,
        ),
        priority=assignment.priority,
        enabled=assignment.enabled == 1,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.patch("/assignments/{assignment_id}", response_model=AlertPolicyAssignmentResponse)
def update_policy_assignment(
    assignment_id: str,
    payload: AlertPolicyAssignmentUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyAssignmentResponse:
    row = db.execute(
        select(AlertPolicyAssignment, AlertPolicyTemplate)
        .join(AlertPolicyTemplate, AlertPolicyTemplate.id == AlertPolicyAssignment.template_id)
        .where(AlertPolicyAssignment.id == assignment_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert policy assignment not found")
    assignment, template = row
    changes = payload.model_dump(exclude_unset=True)
    if "priority" in changes and changes["priority"] is not None:
        assignment.priority = changes["priority"]
    if "enabled" in changes and changes["enabled"] is not None:
        assignment.enabled = 1 if changes["enabled"] else 0
    write_audit_log(
        db,
        action="alert_policy_assignment_updated",
        target_type="alert_policy_assignment",
        target_id=assignment.id,
        user_id=current_user.id,
        details={"changes": changes},
    )
    db.commit()
    db.refresh(assignment)
    return AlertPolicyAssignmentResponse(
        id=assignment.id,
        template_id=template.id,
        template_name=template.name,
        rule_type=template.rule_type,
        scope_type=assignment.scope_type,
        scope_id=assignment.scope_id,
        scope_name=_resolve_scope_name(
            db,
            scope_type=assignment.scope_type,
            scope_id=assignment.scope_id,
        ),
        priority=assignment.priority,
        enabled=assignment.enabled == 1,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy_assignment(
    assignment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> None:
    assignment = db.scalar(select(AlertPolicyAssignment).where(AlertPolicyAssignment.id == assignment_id))
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert policy assignment not found")
    db.delete(assignment)
    write_audit_log(
        db,
        action="alert_policy_assignment_deleted",
        target_type="alert_policy_assignment",
        target_id=assignment_id,
        user_id=current_user.id,
        details={"template_id": assignment.template_id},
    )
    db.commit()


@router.get("/effective/{repeater_id}", response_model=EffectivePolicyResponse)
def get_effective_policy(
    repeater_id: str,
    db: Session = Depends(get_db_session),
    _: User = Depends(require_roles("admin", "operator", "viewer")),
) -> EffectivePolicyResponse:
    repeater = db.scalar(select(Repeater).where(Repeater.id == repeater_id))
    if repeater is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repeater not found")
    policies = list_effective_policies_for_repeater(db, repeater)
    return EffectivePolicyResponse(
        repeater_id=repeater.id,
        node_name=repeater.node_name,
        policies=[
            EffectivePolicyItemResponse(
                rule_type=item.template.rule_type,
                template_id=item.template.id,
                template_name=item.template.name,
                severity=item.template.severity,
                threshold_value=item.template.threshold_value,
                window_minutes=item.template.window_minutes,
                offline_grace_seconds=item.template.offline_grace_seconds,
                cooldown_seconds=item.template.cooldown_seconds,
                auto_resolve=item.template.auto_resolve == 1,
                config=serialize_policy_template_config(item.template),
                source_scope_type=item.assignment.scope_type,
                source_scope_id=item.assignment.scope_id,
                source_scope_name=item.scope_name,
                priority=item.assignment.priority,
            )
            for item in policies
        ],
    )


@router.post("/evaluate", response_model=AlertPolicyEvaluationResponse)
def evaluate_policy_rules(
    payload: AlertPolicyEvaluationRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> AlertPolicyEvaluationResponse:
    summary = evaluate_policies_for_fleet(db, repeater_id=payload.repeater_id)
    write_audit_log(
        db,
        action="alert_policy_evaluation_run",
        target_type="alert_policy",
        target_id=payload.repeater_id,
        user_id=current_user.id,
        details={
            "repeater_id": payload.repeater_id,
            "evaluated_repeaters": summary.evaluated_repeaters,
            "alerts_activated": summary.alerts_activated,
            "alerts_resolved": summary.alerts_resolved,
        },
    )
    db.commit()
    return AlertPolicyEvaluationResponse(
        evaluated_repeaters=summary.evaluated_repeaters,
        alerts_activated=summary.alerts_activated,
        alerts_resolved=summary.alerts_resolved,
    )


@router.post("/bootstrap-defaults", response_model=list[AlertPolicyTemplateResponse])
def bootstrap_default_policy_templates(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_roles("admin", "operator")),
) -> list[AlertPolicyTemplateResponse]:
    existing = db.scalars(select(AlertPolicyTemplate)).all()
    by_rule_type = {template.rule_type: template for template in existing}
    created: list[AlertPolicyTemplate] = []
    default_specs = [
        {
            "name": "Default Offline Repeater",
            "description": "Triggers when repeater inform heartbeat exceeds the grace window.",
            "rule_type": "offline_repeater",
            "severity": "critical",
            "enabled": 1,
            "offline_grace_seconds": 180,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default TLS Telemetry Stale",
            "description": "Triggers when inform and MQTT telemetry are stale while MQTT TLS is enabled.",
            "rule_type": "tls_telemetry_stale",
            "severity": "warning",
            "enabled": 1,
            "offline_grace_seconds": 600,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Noise Floor",
            "description": "Triggers when noise floor average exceeds threshold in the window.",
            "rule_type": "high_noise_floor",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": -95.0,
            "window_minutes": 10,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High CPU",
            "description": "Triggers when average CPU usage exceeds threshold in the window.",
            "rule_type": "high_cpu_percent",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": 90.0,
            "window_minutes": 10,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Memory",
            "description": "Triggers when average memory usage exceeds threshold in the window.",
            "rule_type": "high_memory_percent",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": 90.0,
            "window_minutes": 10,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Disk",
            "description": "Triggers when average disk usage exceeds threshold in the window.",
            "rule_type": "high_disk_percent",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": 90.0,
            "window_minutes": 30,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Temperature",
            "description": "Triggers when current repeater temperature exceeds threshold.",
            "rule_type": "high_temperature_c",
            "severity": "critical",
            "enabled": 1,
            "threshold_value": 80.0,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Airtime",
            "description": "Triggers when average airtime usage exceeds threshold in the window.",
            "rule_type": "high_airtime_percent",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": 80.0,
            "window_minutes": 10,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default High Drop Rate",
            "description": "Triggers when packet drop rate exceeds threshold in the evaluation window.",
            "rule_type": "high_drop_rate",
            "severity": "warning",
            "enabled": 1,
            "threshold_value": 0.05,
            "window_minutes": 15,
            "auto_resolve": 1,
            "config_json": "{}",
        },
        {
            "name": "Default New Zero-Hop Node Detected",
            "description": "Triggers when a newly discovered node is observed via zero-hop advert in the policy window.",
            "rule_type": "new_zero_hop_node_detected",
            "severity": "info",
            "enabled": 1,
            "window_minutes": 60,
            "auto_resolve": 1,
            "config_json": "{}",
        },
    ]
    for spec in default_specs:
        if spec["rule_type"] in by_rule_type:
            continue
        template = AlertPolicyTemplate(**spec)
        db.add(template)
        db.flush()
        created.append(template)
        by_rule_type[template.rule_type] = template

    for rule_type in by_rule_type:
        template = by_rule_type.get(rule_type)
        if template is None:
            continue
        existing_assignment = db.scalar(
            select(AlertPolicyAssignment).where(
                AlertPolicyAssignment.template_id == template.id,
                AlertPolicyAssignment.scope_type == "global",
                AlertPolicyAssignment.scope_id.is_(None),
            )
        )
        if existing_assignment is None:
            db.add(
                AlertPolicyAssignment(
                    template_id=template.id,
                    scope_type="global",
                    scope_id=None,
                    priority=100,
                    enabled=1,
                )
            )

    if created:
        write_audit_log(
            db,
            action="alert_policy_templates_bootstrapped",
            target_type="alert_policy_template",
            target_id=None,
            user_id=current_user.id,
            details={"created_template_ids": [template.id for template in created]},
        )
    db.commit()
    return [_to_template_response(template) for template in by_rule_type.values()]
