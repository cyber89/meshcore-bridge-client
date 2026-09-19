from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )

    tokens: Mapped[list["AuthToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="tokens")


class Repeater(Base):
    __tablename__ = "repeaters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    node_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    pubkey: Mapped[str] = mapped_column(String(130), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_inform_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    inform_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    config_hash: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    cert_serial: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cert_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    system_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    radio_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )

class TopologyObservationSample(Base):
    __tablename__ = "topology_observation_samples"
    __table_args__ = (
        UniqueConstraint(
            "observer_repeater_id",
            "observed_node_id",
            "observed_at",
            name="uq_topology_observation_samples_observer_node_time",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    observer_repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    observed_node_id: Mapped[str] = mapped_column(
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    route_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zero_hop: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contact_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rssi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)

class TransportKeyGroup(Base):
    __tablename__ = "transport_key_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    parent_group_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("transport_key_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    flood_policy: Mapped[str] = mapped_column(String(16), default="allow")
    transport_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class TransportKey(Base):
    __tablename__ = "transport_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    group_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("transport_key_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    flood_policy: Mapped[str] = mapped_column(String(16), default="allow")
    transport_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class TransportKeySyncStatus(Base):
    __tablename__ = "transport_key_sync_status"

    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    command_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("command_queue.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="idle", index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    queued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )

class NodeGroup(Base):
    __tablename__ = "node_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class NodeGroupMembership(Base):
    __tablename__ = "node_group_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("node_groups.id", ondelete="CASCADE"),
        index=True,
    )
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)


class InformSnapshot(Base):
    __tablename__ = "inform_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    noise_floor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rx_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tx_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    forwarded: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dropped: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    airtime_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Packet(Base):
    __tablename__ = "packets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    packet_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    route: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rssi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    src_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    dst_hash: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    packet_hash: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)

class MqttIngestEvent(Base):
    __tablename__ = "mqtt_ingest_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(16), index=True)
    event_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    topic: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[str] = mapped_column(Text)
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
class TopologyNode(Base):
    __tablename__ = "topology_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    pubkey: Mapped[str] = mapped_column(String(130), unique=True, index=True)
    node_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_repeater: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contact_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_observed_by_repeater_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("repeaters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class TopologyObservation(Base):
    __tablename__ = "topology_observations"
    __table_args__ = (
        UniqueConstraint(
            "observer_repeater_id",
            "observed_node_id",
            name="uq_topology_observation_observer_node",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    observer_repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    observed_node_id: Mapped[str] = mapped_column(
        ForeignKey("topology_nodes.id", ondelete="CASCADE"),
        index=True,
    )
    contact_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    route_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    zero_hop: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rssi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    advert_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class TopologyRollupHourly(Base):
    __tablename__ = "topology_rollups_hourly"
    __table_args__ = (
        UniqueConstraint(
            "bucket_start",
            "observer_repeater_id",
            name="uq_topology_rollups_hourly_bucket_observer",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    observer_repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    observed_nodes: Mapped[int] = mapped_column(Integer, default=0)
    zero_hop_nodes: Mapped[int] = mapped_column(Integer, default=0)
    avg_rssi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_snr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class CommandQueueItem(Base):
    __tablename__ = "command_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    command: Mapped[str] = mapped_column(String(64))
    params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

class ConfigSnapshot(Base):
    __tablename__ = "config_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    command_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("command_queue.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    encryption_key_id: Mapped[str] = mapped_column(String(64), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64), index=True)
    payload_size_bytes: Mapped[int] = mapped_column(Integer)


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[str] = mapped_column(
        ForeignKey("repeaters.id", ondelete="CASCADE"),
        index=True,
    )
    serial: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    cn: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pem_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    repeater_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("repeaters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        index=True,
    )
    alert_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    message: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class AlertPolicyTemplate(Base):
    __tablename__ = "alert_policy_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    window_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    offline_grace_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=0)
    auto_resolve: Mapped[int] = mapped_column(Integer, default=1)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class AlertPolicyAssignment(Base):
    __tablename__ = "alert_policy_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("alert_policy_templates.id", ondelete="CASCADE"),
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(16), index=True)
    scope_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )

class AlertActionIntegration(Base):
    __tablename__ = "alert_action_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    secrets_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class AlertActionTemplate(Base):
    __tablename__ = "alert_action_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_template_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_event_types_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class AlertPolicyActionBinding(Base):
    __tablename__ = "alert_policy_action_bindings"
    __table_args__ = (
        UniqueConstraint(
            "policy_template_id",
            "integration_id",
            "action_template_id",
            name="ux_alert_policy_action_bindings_unique_binding",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    policy_template_id: Mapped[str] = mapped_column(
        ForeignKey("alert_policy_templates.id", ondelete="CASCADE"),
        index=True,
    )
    integration_id: Mapped[str] = mapped_column(
        ForeignKey("alert_action_integrations.id", ondelete="CASCADE"),
        index=True,
    )
    action_template_id: Mapped[str] = mapped_column(
        ForeignKey("alert_action_templates.id", ondelete="CASCADE"),
        index=True,
    )
    event_types_json: Mapped[str] = mapped_column(Text, default="[]")
    min_severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"),
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    integration_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    action_template_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    binding_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    provider_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    rendered_payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now_utc,
        onupdate=_now_utc,
    )
