"""
Preflight Diagnostics Engine for MeshCore Bridge.
Inspirado en ammb/preflight.py para validar conectividad con Mosquitto,
acceso al puerto serial/TCP y estado de red antes del arranque.
"""

from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PreflightCheckResult:
    name: str
    passed: bool
    message: str
    is_critical: bool = True
    details: dict[str, Any] = field(default_factory=dict)


class PreflightChecker:
    """Motor de diagnósticos previos al arranque para MeshCore Bridge."""

    def __init__(self) -> None:
        self.results: list[PreflightCheckResult] = []

    def check_mqtt_broker(self, host: str, port: int, timeout: float = 2.0) -> PreflightCheckResult:
        """Comprueba la disponibilidad del broker MQTT mediante socket TCP directo."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            return PreflightCheckResult(
                name="Broker MQTT",
                passed=True,
                message=f"Broker alcanzable en {host}:{port}",
                is_critical=True,
            )
        except Exception as e:
            return PreflightCheckResult(
                name="Broker MQTT",
                passed=False,
                message=f"No se pudo conectar a {host}:{port} ({e})",
                is_critical=True,
            )

    def check_serial_port(self, port: str) -> PreflightCheckResult:
        """Comprueba la existencia o validez del puerto serial o dirección TCP."""
        if port.upper() == "AUTO":
            return PreflightCheckResult(
                name="Puerto Serial MeshCore",
                passed=True,
                message="Modo AUTO configurado (detección en tiempo de ejecución)",
                is_critical=False,
            )

        if port.startswith("tcp://"):
            addr = port.replace("tcp://", "")
            if ":" in addr:
                host, port_str = addr.split(":", 1)
                try:
                    p = int(port_str)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2.0)
                    sock.connect((host, p))
                    sock.close()
                    return PreflightCheckResult(
                        name="Puerto Serial Remoto TCP",
                        passed=True,
                        message=f"Transceptor TCP remoto conectado en {host}:{p}",
                        is_critical=False,
                    )
                except Exception as e:
                    return PreflightCheckResult(
                        name="Puerto Serial Remoto TCP",
                        passed=False,
                        message=f"Aviso: Transceptor TCP remoto en {addr} no responde aún ({e})",
                        is_critical=False,
                    )

        if os.path.exists(port) or port.upper().startswith("COM"):
            return PreflightCheckResult(
                name="Puerto Serial MeshCore",
                passed=True,
                message=f"Dispositivo encontrado en {port}",
                is_critical=False,
            )

        return PreflightCheckResult(
            name="Puerto Serial MeshCore",
            passed=False,
            message=f"Aviso: Dispositivo no detectado en '{port}'. El watchdog intentará reconectar.",
            is_critical=False,
        )

    def check_tcp_companion_port(self, host: str, port: int, enabled: bool) -> PreflightCheckResult:
        """Comprueba si el puerto del Servidor TCP Companion está disponible para enlazar."""
        if not enabled:
            return PreflightCheckResult(
                name="Servidor TCP Companion (Puerto 5000)",
                passed=True,
                message="Servidor TCP Companion deshabilitado por configuración",
                is_critical=False,
            )
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Intentar bind para asegurar que el puerto no esté tomado por otro proceso
            test_host = "127.0.0.1" if host in ("0.0.0.0", "") else host  # nosec B104
            sock.bind((test_host, port))
            sock.close()
            return PreflightCheckResult(
                name="Servidor TCP Companion (Puerto 5000)",
                passed=True,
                message=f"Puerto {port} disponible para App Móvil y CLI ({host}:{port})",
                is_critical=False,
            )
        except Exception as e:
            return PreflightCheckResult(
                name="Servidor TCP Companion (Puerto 5000)",
                passed=False,
                message=f"Aviso: Puerto {port} ocupado o no disponible ({e})",
                is_critical=False,
            )

    def run_all(
        self,
        mqtt_host: str,
        mqtt_port: int,
        serial_port: str,
        tcp_server_port: int = 5000,
        tcp_server_enabled: bool = True,
        tcp_server_host: str = "0.0.0.0",  # nosec B104
    ) -> dict[str, Any]:
        """Ejecuta toda la matriz de comprobaciones y devuelve el informe consolidado."""
        self.results = [
            self.check_mqtt_broker(mqtt_host, mqtt_port),
            self.check_serial_port(serial_port),
            self.check_tcp_companion_port(tcp_server_host, tcp_server_port, tcp_server_enabled),
        ]

        critical_failures = [r for r in self.results if not r.passed and r.is_critical]
        warnings = [r for r in self.results if not r.passed and not r.is_critical]

        overall_status = "OK"
        if critical_failures:
            overall_status = "ERROR"
        elif warnings:
            overall_status = "WARNING"

        return {
            "status": overall_status,
            "checks": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "is_critical": r.is_critical,
                }
                for r in self.results
            ],
            "critical_count": len(critical_failures),
            "warning_count": len(warnings),
        }


def run_preflight_checks(
    mqtt_host: str | None = None,
    mqtt_port: int | None = None,
    serial_port: str | None = None,
    tcp_server_port: int = 5000,
    tcp_server_enabled: bool = True,
    tcp_server_host: str = "0.0.0.0",  # nosec B104
) -> dict[str, Any]:
    """Función de conveniencia para ejecutar todas las comprobaciones preflight."""
    import config
    host = mqtt_host or config.MQTT_HOST
    port = mqtt_port or config.MQTT_PORT
    s_port = serial_port or config.SERIAL_PORT
    checker = PreflightChecker()
    return checker.run_all(
        mqtt_host=host,
        mqtt_port=port,
        serial_port=s_port,
        tcp_server_port=tcp_server_port,
        tcp_server_enabled=tcp_server_enabled,
        tcp_server_host=tcp_server_host,
    )


__all__ = [
    "PreflightCheckResult",
    "PreflightChecker",
    "run_preflight_checks",
]
