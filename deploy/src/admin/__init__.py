"""
Paquete modular de administración para MeshCore Bridge (src/admin).
Separa la ejecución de comandos en ejecutores de dominio:
- RepeaterAdminExecutor: Comandos remotos, ping 0, autenticación y configuración en repetidores.
- TracerouteExecutor: Trazado de ruta multihop y diagnóstico RF.
- LocalConfigExecutor: Lectura y modificación de parámetros locales de radio y telemetría.
"""

from src.admin.cli_command_executor import CliCommandExecutor
from src.admin.local_config_executor import LocalConfigExecutor
from src.admin.repeater_executor import (
    RemoteRepeaterRequest,
    RepeaterAdminExecutor,
    WaiterRegistry,
)
from src.admin.traceroute_executor import TracerouteExecutor

__all__ = [
    "CliCommandExecutor",
    "LocalConfigExecutor",
    "RemoteRepeaterRequest",
    "RepeaterAdminExecutor",
    "TracerouteExecutor",
    "WaiterRegistry",
]
