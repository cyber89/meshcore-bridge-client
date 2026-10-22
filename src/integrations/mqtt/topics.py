"""
Unified MQTT Topic Resolver for MeshCore Bridge.
Provides a single source of truth for constructing dynamic and canonical
MQTT topics based on the active topic prefix (ADR 0021 / F1.3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MqttTopics:
    """Resolved dynamic MQTT topics for a specific topic prefix."""

    prefix: str = "meshcore"

    @classmethod
    def from_prefix(cls, prefix: str | None = None) -> MqttTopics:
        """Construct topic set from a configured string prefix."""
        clean_prefix = (prefix or "meshcore").strip().strip("/")
        return cls(prefix=clean_prefix if clean_prefix else "meshcore")

    @property
    def state(self) -> str:
        return f"{self.prefix}/bridge/state"

    @property
    def health(self) -> str:
        return f"{self.prefix}/bridge/health"

    @property
    def alert(self) -> str:
        return f"{self.prefix}/bridge/alert"

    @property
    def tx(self) -> str:
        return f"{self.prefix}/tx"

    @property
    def tx_status(self) -> str:
        return f"{self.prefix}/tx/status"

    @property
    def admin_cmd(self) -> str:
        return f"{self.prefix}/admin/cmd"

    @property
    def admin_status(self) -> str:
        return f"{self.prefix}/admin/status"

    @property
    def admin_repeater(self) -> str:
        return f"{self.prefix}/admin/repeater"

    @property
    def rx_all(self) -> str:
        return f"{self.prefix}/rx/all"

    @property
    def rx_public(self) -> str:
        return f"{self.prefix}/rx/public"

    @property
    def rx_channel(self) -> str:
        return f"{self.prefix}/rx/channel"

    @property
    def rx_direct(self) -> str:
        return f"{self.prefix}/rx/direct"

    @property
    def rx_telemetry(self) -> str:
        return f"{self.prefix}/rx/telemetry"

    @property
    def rx_log(self) -> str:
        return f"{self.prefix}/rx/log"

    @property
    def rx_nodes(self) -> str:
        return f"{self.prefix}/rx/nodes"

    def rx_channel_topic(self, channel_idx: int) -> str:
        """Derive the specific RX channel topic."""
        if channel_idx == 0:
            return self.rx_public
        return f"{self.rx_channel}/ch_{channel_idx}"

    def rx_direct_topic(self, sender: str) -> str:
        """Derive direct message topic for a specific sender."""
        return f"{self.rx_direct}/{sender}"

    def repeater_cmd_topic(self, target: str) -> str:
        """Derive administrative command topic for a specific repeater node."""
        return f"{self.admin_repeater}/{target}/cmd"

    def repeater_status_topic(self, target: str) -> str:
        """Derive administrative status topic for a specific repeater node."""
        return f"{self.admin_repeater}/{target}/status"

    def repeater_sub_topic(self, target: str, subpath: str) -> str:
        """Derive specific sub-topic for a repeater node (e.g. neighbours, acl, ping_zero)."""
        return f"{self.admin_repeater}/{target}/{subpath}"
