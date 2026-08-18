"""
AdminCommandHandler: Ejecución de comandos de administración RF y repetidores remotos.
Extraído de MeshCoreBridge (God Class) para separar la responsabilidad de gestión remota.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import config
from src.contact_manager import NodeRegistry
from src.mqtt_client import AsyncBridgeMQTTClient
from src.repeater_manager import RepeaterManager


@dataclass(slots=True)
class AdminContext:
    """Dependencias para ejecutar comandos de administración sobre radio y repetidores."""
    mc_provider: Callable[[], Any]
    node_registry: NodeRegistry
    repeater_manager: RepeaterManager
    mqtt: AsyncBridgeMQTTClient
    execute_tx: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class AdminCommandHandler:
    """Ejecuta comandos de administración sobre la radio o repetidores."""

    def __init__(self, ctx: AdminContext) -> None:
        self._ctx = ctx

    async def handle(self, admin_data: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta comandos de administración sobre la radio o repetidores."""
        action = str(admin_data.get("action", admin_data.get("command", "")))
        req_id = admin_data.get("request_id", admin_data.get("id"))
        target_node = admin_data.get("target_node", admin_data.get("repeater"))
        res: dict[str, Any] = {"status": "ok", "action": action}
        if req_id is not None:
            res["request_id"] = req_id

        mc = self._ctx.mc_provider()
        if action == "get_config":
            res["config"] = getattr(mc, "self_info", {"name": "Heltec_Router_E2E", "radio_freq": 915.0})
        elif action == "list_nodes":
            res["nodes"] = self._ctx.node_registry.list_nodes()

        # Si el comando va dirigido a un repetidor remoto
        if target_node:
            cmd_text = self._ctx.repeater_manager.build_repeater_command_payload(action, admin_data)
            await self._ctx.execute_tx({"to": str(target_node), "text": f"cmd {cmd_text}", "request_id": req_id})
            res["target_node"] = target_node
            res["cmd_dispatched"] = cmd_text
            self._ctx.mqtt.publish_safe(f"{config.TOPIC_ADMIN_REPEATER}/{target_node}/status", json.dumps(res), qos=1)
            return res

        if mc and hasattr(mc, "commands"):
            try:
                if action == "set_tx_power" and hasattr(mc.commands, "set_tx_power"):
                    power = int(admin_data.get("power", 20))
                    await mc.commands.set_tx_power(power)
                elif action == "set_name" and hasattr(mc.commands, "set_name"):
                    name = str(admin_data.get("name", "Node"))
                    await mc.commands.set_name(name)
                elif action == "reboot" and hasattr(mc.commands, "reboot"):
                    await mc.commands.reboot()
                elif action == "req_telemetry" and hasattr(mc.commands, "req_telemetry"):
                    await mc.commands.req_telemetry()
            except Exception as e:
                res["status"] = "error"
                res["error"] = str(e)

        self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
        return res
