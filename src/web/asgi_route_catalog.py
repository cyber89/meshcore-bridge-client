"""Canonical JSON operation catalog for the ASGI transport.

The six batches describe transport registration, not new domain ownership.
Existing controllers keep validation, coercion, effects and response envelopes.
DTO choices follow the phase 2 source inventory; these permissive wire models
must not replace the raw-query handling in LogsController. This module does not
read documentary JSON, duplicate ROUTE_ALIASES or register the separate tile API.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.web.request_models import (
    AutoAddBodyDTO,
    ChannelIndexBodyDTO,
    ChannelsBodyDTO,
    ChannelWriteBodyDTO,
    CompatibilityBodyDTO,
    ConfigBodyDTO,
    ContactsBodyDTO,
    ContactTransferBodyDTO,
    ContactWriteBodyDTO,
    CustomVarsBodyDTO,
    FloodScopeBodyDTO,
    MapsBodyDTO,
    MqttConnectionBodyDTO,
    MqttPresetBodyDTO,
    NodesBodyDTO,
    PacketsBodyDTO,
    PathHashBodyDTO,
    RepeaterBodyDTO,
    SendTxBodyDTO,
    ServicesBodyDTO,
    ServicesConfigBodyDTO,
    SyncClockBodyDTO,
    SystemBodyDTO,
    TxBodyDTO,
)


@dataclass(frozen=True, slots=True)
class RouteContract:
    """An observed canonical method/path and its compatibility input model."""

    method: str
    path: str
    model: type[CompatibilityBodyDTO]
    batch: str


ROUTE_BATCHES: tuple[str, ...] = (
    "system",
    "network",
    "contacts_channels",
    "history_maps",
    "services",
    "radio_admin",
)

# Literal declarations intentionally make review independent of generated docs.
# Static resources precede dynamic resources within each batch. The endpoint
# adapter must still let the existing router decide domain-specific 404/405s.
ROUTE_CONTRACTS: tuple[RouteContract, ...] = (
    # System and diagnostics: 11 operations.
    RouteContract("GET", "/api/status", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/health", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/diagnostics", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/preflight", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/diagnostics/report.md", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/diagnostics/report", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/diagnostics/export", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/system/logs", SystemBodyDTO, "system"),
    RouteContract("DELETE", "/api/system/logs", SystemBodyDTO, "system"),
    RouteContract("GET", "/api/system/logs/level", SystemBodyDTO, "system"),
    RouteContract("POST", "/api/system/logs/level", SystemBodyDTO, "system"),
    # Passive network/analytics reads and the existing reset: 8 operations.
    RouteContract("GET", "/api/nodes", NodesBodyDTO, "network"),
    RouteContract("GET", "/api/lqi", NodesBodyDTO, "network"),
    RouteContract("GET", "/api/analytics", NodesBodyDTO, "network"),
    RouteContract("POST", "/api/analytics/reset", NodesBodyDTO, "network"),
    RouteContract("DELETE", "/api/analytics/reset", NodesBodyDTO, "network"),
    RouteContract("GET", "/api/rf/heatmap", NodesBodyDTO, "network"),
    RouteContract("GET", "/api/airtime/stats", NodesBodyDTO, "network"),
    RouteContract("GET", "/api/rf/noise", NodesBodyDTO, "network"),
    # Shared contact/channel state and current mutation locks: 17 operations.
    RouteContract("GET", "/api/contacts", ContactsBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts", ContactWriteBodyDTO, "contacts_channels"),
    RouteContract("DELETE", "/api/contacts", ContactsBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts/sync", ContactsBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts/share", ContactTransferBodyDTO, "contacts_channels"),
    RouteContract("GET", "/api/contacts/export", ContactTransferBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts/export", ContactTransferBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts/import", ContactTransferBodyDTO, "contacts_channels"),
    RouteContract("GET", "/api/contacts/discovered", ContactsBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/contacts/accept", ContactsBodyDTO, "contacts_channels"),
    RouteContract("GET", "/api/channels", ChannelsBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/channels", ChannelWriteBodyDTO, "contacts_channels"),
    RouteContract("DELETE", "/api/channels", ChannelIndexBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/channels/sync", ChannelsBodyDTO, "contacts_channels"),
    RouteContract("GET", "/api/channels/export", ChannelIndexBodyDTO, "contacts_channels"),
    RouteContract("POST", "/api/channels/export", ChannelIndexBodyDTO, "contacts_channels"),
    RouteContract("DELETE", "/api/contacts/{public_key}", ContactsBodyDTO, "contacts_channels"),
    # Existing buffers, raw-query diagnostics and map metadata: 10 operations.
    RouteContract("GET", "/api/messages/recent", TxBodyDTO, "history_maps"),
    RouteContract("GET", "/api/packets", PacketsBodyDTO, "history_maps"),
    RouteContract("DELETE", "/api/packets", PacketsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/packets/export", PacketsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/map/status", MapsBodyDTO, "history_maps"),
    RouteContract("POST", "/api/map/reload", MapsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/messages", MapsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/telemetry", MapsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/logs/download", MapsBodyDTO, "history_maps"),
    RouteContract("GET", "/api/logs/raw", MapsBodyDTO, "history_maps"),
    # Network-service configuration/presets: 6 operations.
    RouteContract("GET", "/api/services/config", ServicesBodyDTO, "services"),
    RouteContract("POST", "/api/services/config", ServicesConfigBodyDTO, "services"),
    RouteContract("GET", "/api/services/presets", ServicesBodyDTO, "services"),
    RouteContract("POST", "/api/services/presets", MqttPresetBodyDTO, "services"),
    RouteContract("POST", "/api/services/mqtt-external/test", MqttConnectionBodyDTO, "services"),
    RouteContract("DELETE", "/api/services/presets/{id:path}", ServicesBodyDTO, "services"),
    # Radio/config/TX retain all existing guards, queues and timeouts: 38 operations.
    RouteContract("POST", "/api/tx", SendTxBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/admin", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/admin/repeater", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/login", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/logout", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/config", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/action", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/neighbours", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/owner", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/regions", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/clock", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/remote/acl", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/node/ping_zero", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/ping_zero", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/traceroute", RepeaterBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/repeater/traceroute", RepeaterBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config", ConfigBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/radio", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/radio", ConfigBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/identity", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/identity", ConfigBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/custom_vars", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/custom_vars", CustomVarsBodyDTO, "radio_admin"),
    RouteContract("DELETE", "/api/config/custom_vars", CustomVarsBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/path_hash_mode", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/path_hash_mode", PathHashBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/autoadd", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/autoadd", AutoAddBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/flood_scope", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/flood_scope", FloodScopeBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/node/advert", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/node/reboot", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/sync-clock", SyncClockBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/clear-stats", ConfigBodyDTO, "radio_admin"),
    RouteContract("GET", "/api/config/refresh", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/refresh", ConfigBodyDTO, "radio_admin"),
    RouteContract("POST", "/api/config/reconnect", ConfigBodyDTO, "radio_admin"),
)
