"""
Home Assistant MQTT Auto-Discovery Module for MeshCore Bridge.
Genera y publica entidades de Home Assistant (sensores, métricas de RF,
batería y telemetría de nodos de la malla) de forma estándar y desacoplada.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class HomeAssistantDiscovery:
    """Gestor de Auto-Discovery MQTT para Home Assistant."""

    def __init__(
        self,
        topic_prefix: str = "meshcore",
        ha_prefix: str = "homeassistant",
        enabled: bool = True,
    ) -> None:
        self.topic_prefix = topic_prefix.strip("/")
        self.ha_prefix = ha_prefix.strip("/")
        self.enabled = enabled
        self._discovered_entities: set[str] = set()

    def generate_node_discovery_configs(
        self, node_info: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Genera las tuplas (tópico_discovery, payload_config) para un nodo de la malla."""
        pubkey = str(node_info.get("public_key") or "unknown_node")
        alias = str(node_info.get("name") or node_info.get("alias") or f"MeshNode {pubkey[:6]}")
        hardware = str(node_info.get("hardware") or "MeshCore LoRa Node")

        device_block = {
            "identifiers": [f"meshcore_node_{pubkey}"],
            "name": alias,
            "model": hardware,
            "manufacturer": "MeshCore Network",
            "sw_version": "MeshCore v1.17+",
        }

        state_topic = f"{self.topic_prefix}/rx/telemetry"
        configs: list[tuple[str, dict[str, Any]]] = []

        # 1. Sensor de Batería (%)
        battery_unique_id = f"meshcore_{pubkey}_battery"
        battery_topic = f"{self.ha_prefix}/sensor/{battery_unique_id}/config"
        configs.append(
            (
                battery_topic,
                {
                    "name": f"{alias} Batería",
                    "unique_id": battery_unique_id,
                    "state_topic": state_topic,
                    "value_template": f"{{% if value_json.sender == '{pubkey}' or value_json.public_key == '{pubkey}' %}}{{{{ value_json.battery | default(value_json.telemetry.battery, true) }}}}{{% endif %}}",
                    "unit_of_measurement": "%",
                    "device_class": "battery",
                    "state_class": "measurement",
                    "device": device_block,
                },
            )
        )

        # 2. Sensor de Voltaje (V)
        voltage_unique_id = f"meshcore_{pubkey}_voltage"
        voltage_topic = f"{self.ha_prefix}/sensor/{voltage_unique_id}/config"
        configs.append(
            (
                voltage_topic,
                {
                    "name": f"{alias} Voltaje",
                    "unique_id": voltage_unique_id,
                    "state_topic": state_topic,
                    "value_template": f"{{% if value_json.sender == '{pubkey}' or value_json.public_key == '{pubkey}' %}}{{{{ value_json.voltage | default(value_json.telemetry.voltage, true) }}}}{{% endif %}}",
                    "unit_of_measurement": "V",
                    "device_class": "voltage",
                    "state_class": "measurement",
                    "device": device_block,
                },
            )
        )

        # 3. Sensor de SNR (dB)
        snr_unique_id = f"meshcore_{pubkey}_snr"
        snr_topic = f"{self.ha_prefix}/sensor/{snr_unique_id}/config"
        configs.append(
            (
                snr_topic,
                {
                    "name": f"{alias} SNR LoRa",
                    "unique_id": snr_unique_id,
                    "state_topic": state_topic,
                    "value_template": f"{{% if value_json.sender == '{pubkey}' or value_json.public_key == '{pubkey}' %}}{{{{ value_json.snr | default(value_json.telemetry.snr, true) }}}}{{% endif %}}",
                    "unit_of_measurement": "dB",
                    "device_class": "signal_strength",
                    "state_class": "measurement",
                    "device": device_block,
                },
            )
        )

        # 4. Sensor de RSSI (dBm)
        rssi_unique_id = f"meshcore_{pubkey}_rssi"
        rssi_topic = f"{self.ha_prefix}/sensor/{rssi_unique_id}/config"
        configs.append(
            (
                rssi_topic,
                {
                    "name": f"{alias} RSSI LoRa",
                    "unique_id": rssi_unique_id,
                    "state_topic": state_topic,
                    "value_template": f"{{% if value_json.sender == '{pubkey}' or value_json.public_key == '{pubkey}' %}}{{{{ value_json.rssi | default(value_json.telemetry.rssi, true) }}}}{{% endif %}}",
                    "unit_of_measurement": "dBm",
                    "device_class": "signal_strength",
                    "state_class": "measurement",
                    "device": device_block,
                },
            )
        )

        return configs

    def generate_bridge_discovery_configs(self) -> list[tuple[str, dict[str, Any]]]:
        """Genera las entidades de Home Assistant para el propio bridge."""
        bridge_device = {
            "identifiers": ["meshcore_bridge_gateway"],
            "name": "MeshCore Bridge Gateway",
            "model": "LoRa-to-MQTT Bridge",
            "manufacturer": "MeshCore Bridge Community",
            "sw_version": "v2.2.0",
        }

        health_topic = f"{self.topic_prefix}/bridge/health"
        state_topic = f"{self.topic_prefix}/bridge/state"
        configs: list[tuple[str, dict[str, Any]]] = []

        # Estado binario de conexión del Bridge
        configs.append(
            (
                f"{self.ha_prefix}/binary_sensor/meshcore_bridge_status/config",
                {
                    "name": "MeshCore Bridge Online",
                    "unique_id": "meshcore_bridge_status",
                    "state_topic": state_topic,
                    "payload_on": "online",
                    "payload_off": "offline",
                    "device_class": "connectivity",
                    "device": bridge_device,
                },
            )
        )

        # Contador de Paquetes RX
        configs.append(
            (
                f"{self.ha_prefix}/sensor/meshcore_bridge_rx_packets/config",
                {
                    "name": "MeshCore Bridge Paquetes RX",
                    "unique_id": "meshcore_bridge_rx_packets",
                    "state_topic": health_topic,
                    "value_template": "{{ value_json.metrics.rx_count }}",
                    "state_class": "total_increasing",
                    "icon": "mdi:radio-tower",
                    "device": bridge_device,
                },
            )
        )

        # Contador de Paquetes TX
        configs.append(
            (
                f"{self.ha_prefix}/sensor/meshcore_bridge_tx_packets/config",
                {
                    "name": "MeshCore Bridge Paquetes TX",
                    "unique_id": "meshcore_bridge_tx_packets",
                    "state_topic": health_topic,
                    "value_template": "{{ value_json.metrics.tx_count }}",
                    "state_class": "total_increasing",
                    "icon": "mdi:send-circle",
                    "device": bridge_device,
                },
            )
        )

        # Cola de buffer offline
        configs.append(
            (
                f"{self.ha_prefix}/sensor/meshcore_bridge_offline_buffer/config",
                {
                    "name": "MeshCore Buffer Offline",
                    "unique_id": "meshcore_bridge_offline_buffer",
                    "state_topic": health_topic,
                    "value_template": "{{ value_json.metrics.offline_buffer_count }}",
                    "state_class": "measurement",
                    "icon": "mdi:database",
                    "device": bridge_device,
                },
            )
        )

        return configs

    def publish_discovery_for_node(
        self,
        node_info: dict[str, Any],
        publish_func: Callable[..., Any],
    ) -> int:
        """Publica los tópicos de autodescubrimiento para un nodo si no se han publicado aún."""
        if not self.enabled:
            return 0

        pubkey = str(node_info.get("public_key") or "")
        if not pubkey or pubkey in self._discovered_entities:
            return 0

        configs = self.generate_node_discovery_configs(node_info)
        count = 0
        for topic, payload in configs:
            try:
                publish_func(topic, json.dumps(payload), 0, True)
                count += 1
            except Exception as e:
                logger.warning(f"Error publicando HA Discovery para {pubkey}: {e}")

        self._discovered_entities.add(pubkey)
        logger.info(f"Home Assistant Discovery publicado para nodo {pubkey} ({count} sensores)")
        return count

    def publish_discovery_for_bridge(
        self,
        publish_func: Callable[..., Any],
    ) -> int:
        """Publica los tópicos de autodescubrimiento para el bridge."""
        if not self.enabled:
            return 0

        configs = self.generate_bridge_discovery_configs()
        count = 0
        for topic, payload in configs:
            try:
                publish_func(topic, json.dumps(payload), 0, True)
                count += 1
            except Exception as e:
                logger.warning(f"Error publicando HA Discovery para Bridge: {e}")

        logger.info(f"Home Assistant Discovery publicado para Gateway Bridge ({count} sensores)")
        return count
