"""Preparatory wire DTOs for the optional ASGI adapter.

Known request fields intentionally use ``Any``. The current controllers own
defaults, coercion, validation order and domain checks; a stricter model here
would change existing 400/422 responses before those controllers run. Unknown
fields, explicit nulls and query lists must also reach them unchanged.

These declarations describe observed field names, not complete validation or
certified transport parity. Only JSON-decoded mappings are supported at this
boundary. The optional web dependencies are required to import this module.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict


class CompatibilityBodyDTO(BaseModel):
    """Preserve a decoded request mapping until the legacy controller handles it."""

    model_config = ConfigDict(extra="allow", hide_input_in_errors=True)

    def to_legacy_body(self) -> dict[str, Any]:
        """Retain explicit null/default values and extras; omit absent fields.

        Do not use ``exclude_none``/``exclude_defaults``, JSON mode or a typed
        nested DTO: these would erase nulls or alter controller inputs. This
        method does not reproduce the router's separate query-merging rules.
        """
        return self.model_dump(mode="python", exclude_unset=True)

    def __repr__(self) -> str:
        """Keep both known credentials and arbitrary extra values out of repr."""
        return f"{type(self).__name__}()"

    def __str__(self) -> str:
        """Avoid exposing request values through implicit string formatting."""
        return type(self).__name__

    def __repr_args__(self) -> Iterable[tuple[str | None, Any]]:
        """Also suppress values in Pydantic's inherited rich representation."""
        return ()


class SendTxBodyDTO(CompatibilityBodyDTO):
    """TX checks target aliases, roles and channel coercion in controller order.

    In particular, present ``to`` wins over ``target`` even when null. Text and
    destination must not be stripped here, and UTF-8 limits remain in the SDK.
    """

    text: Any = None
    to: Any = None
    target: Any = None
    channel_index: Any = None
    channel_idx: Any = None
    request_id: Any = None


class TxBodyDTO(SendTxBodyDTO):
    """TX family; recent-message reads ignore request fields."""


class ContactWriteBodyDTO(CompatibilityBodyDTO):
    """Contact mutations retain key aliases and coordinates without conversion."""

    public_key: Any = None
    key: Any = None
    name: Any = None
    alias: Any = None
    role: Any = None
    is_favorite: Any = None
    latitude: Any = None
    longitude: Any = None
    lat: Any = None
    lon: Any = None
    adv_lat: Any = None
    adv_lon: Any = None


class ContactTransferBodyDTO(ContactWriteBodyDTO):
    """Import/export/share accept different alias precedence in each handler."""

    pubkey: Any = None
    data: Any = None
    payload: Any = None
    uri: Any = None
    contacts: Any = None


class ContactsBodyDTO(ContactTransferBodyDTO):
    """Contact family, including discovered-contact acceptance."""

    target_node: Any = None


class ChannelIndexBodyDTO(CompatibilityBodyDTO):
    """Export/delete and writes intentionally have different index coercion."""

    index: Any = None


class ChannelWriteBodyDTO(ChannelIndexBodyDTO):
    """Channel capacity and firmware name/PSK checks remain in the controller."""

    name: Any = None
    psk: Any = None
    overwrite: Any = None


class ChannelsBodyDTO(ChannelWriteBodyDTO):
    """Channel family; synchronization and reads have no consumed body fields."""


class CustomVarsBodyDTO(CompatibilityBodyDTO):
    """Custom variables preserve presence-based single/batch precedence."""

    key: Any = None
    value: Any = None
    val: Any = None
    vars: Any = None


class PathHashBodyDTO(CompatibilityBodyDTO):
    """Path hash writes retain their two aliases without applying a global int."""

    mode: Any = None
    path_hash_mode: Any = None


class AutoAddBodyDTO(CompatibilityBodyDTO):
    """Autoadd flags and max_hops use the operation's existing validation."""

    flags: Any = None
    config: Any = None
    autoadd: Any = None
    max_hops: Any = None


class FloodScopeBodyDTO(CompatibilityBodyDTO):
    """Flood scope aliases retain explicit null and empty-string meaning."""

    scope: Any = None
    scope_name: Any = None


class SyncClockBodyDTO(CompatibilityBodyDTO):
    """Clock synchronization defaults to current time only in the handler."""

    epoch: Any = None
    timestamp: Any = None


class ConfigBodyDTO(CompatibilityBodyDTO):
    """Configuration family, including passthrough device-specific parameters.

    Named fields reflect direct reads in the router/controller. Firmware and
    admin parameters not named here remain extras rather than being discarded.
    """

    refresh: Any = None
    flood: Any = None
    epoch: Any = None
    timestamp: Any = None
    key: Any = None
    value: Any = None
    val: Any = None
    vars: Any = None
    mode: Any = None
    path_hash_mode: Any = None
    flags: Any = None
    config: Any = None
    autoadd: Any = None
    max_hops: Any = None
    scope: Any = None
    scope_name: Any = None
    duty_cycle_limit_pct: Any = None
    warn_threshold_pct: Any = None
    airtime_cutoff_enabled: Any = None
    airtime_cutoff_threshold_pct: Any = None
    airtime_cutoff_resume_pct: Any = None
    repeater_pre_send_delay_enabled: Any = None
    repeater_pre_send_delay_s: Any = None


class RepeaterBodyDTO(CompatibilityBodyDTO):
    """Admin/repeater family preserves arbitrary direct-admin command extras.

    Targets and actions have operation-specific aliases. Passwords and params
    remain raw until each existing handler performs its own conversion.
    """

    action: Any = None
    command: Any = None
    target_node: Any = None
    repeater: Any = None
    target: Any = None
    to: Any = None
    params: Any = None
    password: Any = None
    request_id: Any = None
    count: Any = None
    offset: Any = None


class ServicesConfigBodyDTO(CompatibilityBodyDTO):
    """Service objects remain raw; nested coercions belong to existing services."""

    external_mqtt: Any = None
    local_mqtt: Any = None
    tcp_server: Any = None


class MqttConnectionBodyDTO(CompatibilityBodyDTO):
    """External MQTT connection diagnostics retain native truthiness/coercion."""

    host: Any = None
    port: Any = None
    transport: Any = None
    tls_enabled: Any = None
    tls_verify: Any = None
    auth_type: Any = None
    username: Any = None
    password: Any = None
    token: Any = None
    timeout: Any = None


class MqttPresetBodyDTO(MqttConnectionBodyDTO):
    """Preset creation applies its bool/int/string conversions after this DTO."""

    id: Any = None
    name: Any = None
    description: Any = None
    downlink_enabled: Any = None
    location_privacy: Any = None
    topic_mode: Any = None
    topic_prefix: Any = None
    region_iata: Any = None
    payload_format: Any = None
    filter_observer_mode: Any = None
    filter_public: Any = None
    filter_channels: Any = None
    filter_direct: Any = None
    filter_telemetry: Any = None
    filter_nodes: Any = None
    filter_raw: Any = None
    keepalive: Any = None
    qos: Any = None


class ServicesBodyDTO(MqttPresetBodyDTO):
    """Services family, including configuration and preset/connection operations."""

    external_mqtt: Any = None
    local_mqtt: Any = None
    tcp_server: Any = None


class SystemBodyDTO(CompatibilityBodyDTO):
    """System controls; log readers separately parse the original query string."""

    level: Any = None
    limit: Any = None
    offset: Any = None
    search: Any = None


class LogsBodyDTO(CompatibilityBodyDTO):
    """Descriptive only: LogsController consumes raw query, not this mapping."""

    limit: Any = None
    offset: Any = None
    level: Any = None
    search: Any = None


class NodesBodyDTO(CompatibilityBodyDTO):
    """Node pagination/analytics fields retain router-level conversion semantics."""

    limit: Any = None
    offset: Any = None
    range: Any = None


class PacketsBodyDTO(CompatibilityBodyDTO):
    """Packet reads/export retain order validation before pagination conversion."""

    limit: Any = None
    offset: Any = None
    direction: Any = None
    type: Any = None
    order: Any = None
    format: Any = None


class MapsBodyDTO(CompatibilityBodyDTO):
    """Map status/reload do not consume a body; tile coordinates are path data."""


class ProblemDetailsDTO(CompatibilityBodyDTO):
    """Schema for the canonical helper, including arbitrary error extensions.

    This is documentation for future OpenAPI. Do not use it as a response_model
    or to serialize controller responses: not every existing error uses this
    envelope, and partial-command fields must survive without filtering.
    """

    type: str
    title: str
    status: int
    detail: str
    error: str
    message: str
    timestamp: float
