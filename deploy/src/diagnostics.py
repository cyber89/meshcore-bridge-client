"""
MeshCore Bridge - Central Diagnostics and Real-time Log Hub
Módulo central para captura de logs estructurados, inspección de salud de subsistemas,
depuración interactiva y exportación de diagnósticos.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
import logging
import platform
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any


@dataclasses.dataclass(slots=True, frozen=True)
class SystemLogRecord:
    """Registro estructurado de log del sistema con información contextual."""

    timestamp: float
    iso_time: str
    level: str
    logger_name: str
    module: str
    func_name: str
    line_no: int
    message: str
    exception: str | None = None
    source: str = "core"

    def to_dict(self) -> dict[str, Any]:
        """Serializa el registro a un diccionario plano para JSON/WebSocket."""
        return {
            "timestamp": self.timestamp,
            "iso_time": self.iso_time,
            "level": self.level,
            "logger": self.logger_name,
            "module": self.module,
            "func": self.func_name,
            "line": self.line_no,
            "message": self.message,
            "exception": self.exception,
            "source": self.source,
        }


class SystemLogHandler(logging.Handler):
    """
    Handler de logging personalizado que intercepta todos los registros de Python,
    los almacena en un búfer circular en memoria y los transmite en tiempo real vía callback.
    """

    def __init__(
        self,
        max_records: int = 500,
        broadcast_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self.buffer: collections.deque[SystemLogRecord] = collections.deque(maxlen=max_records)
        self.broadcast_callback = broadcast_callback
        self.error_count = 0
        self.warn_count = 0
        self.info_count = 0
        self.debug_count = 0
        self.last_error_time: float | None = None
        self.last_error_msg: str | None = None
        self._is_emitting = False

    def emit(self, record: logging.LogRecord) -> None:
        """Procesa y almacena un registro de logging estándar de Python."""
        try:
            msg = self.format(record) if self.formatter else record.getMessage()

            exc_text = None
            if record.exc_info:
                exc_text = "".join(traceback.format_exception(*record.exc_info)).strip()

            log_entry = SystemLogRecord(
                timestamp=record.created,
                iso_time=datetime.datetime.fromtimestamp(
                    record.created, tz=datetime.timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                level=record.levelname.upper(),
                logger_name=record.name,
                module=record.module,
                func_name=record.funcName,
                line_no=record.lineno,
                message=msg,
                exception=exc_text,
                source=record.name.split(".")[-1] if "." in record.name else record.name,
            )

            # Actualizar contadores por severidad
            if record.levelno >= logging.ERROR:
                self.error_count += 1
                self.last_error_time = record.created
                self.last_error_msg = msg
            elif record.levelno >= logging.WARNING:
                self.warn_count += 1
            elif record.levelno >= logging.INFO:
                self.info_count += 1
            else:
                self.debug_count += 1

            self.buffer.append(log_entry)

            # Notificar callback en vivo (WebSocket) de forma segura sin reentrancia
            if self.broadcast_callback and not self._is_emitting:
                self._is_emitting = True
                try:
                    payload = {
                        "event_type": "system_log",
                        "data": log_entry.to_dict(),
                    }
                    self.broadcast_callback(payload)
                finally:
                    self._is_emitting = False

        except Exception:
            self.handleError(record)

    def get_logs(
        self,
        level: str | None = None,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Filtra y devuelve registros de logs acumulados."""
        records = list(self.buffer)
        if level:
            target_lvl = level.strip().upper()
            records = [r for r in records if r.level == target_lvl]
        if search:
            search_low = search.strip().lower()
            records = [
                r
                for r in records
                if search_low in r.message.lower()
                or search_low in r.module.lower()
                or search_low in (r.exception or "").lower()
            ]

        selected = records[-limit:] if limit > 0 else records
        return [r.to_dict() for r in selected]

    def clear(self) -> None:
        """Limpia el búfer en memoria y reinicia contadores."""
        self.buffer.clear()
        self.error_count = 0
        self.warn_count = 0
        self.info_count = 0
        self.debug_count = 0


class DiagnosticManager:
    """
    Gestor de diagnósticos de subsistemas, captura de salud de componentes
    y generación de reportes de resolución de incidencias.
    """

    def __init__(self, bridge: Any, log_handler: SystemLogHandler | None = None) -> None:
        self.bridge = bridge
        self.log_handler = log_handler or SystemLogHandler()

    def get_current_log_level(self) -> str:
        """Devuelve el nombre del nivel de logging actual del root logger."""
        return logging.getLevelName(logging.getLogger().level)

    def set_log_level(self, level_name: str) -> str:
        """Cambia dinámicamente en caliente el nivel de log global de la aplicación."""
        lvl = level_name.strip().upper()
        if hasattr(logging, lvl):
            level_val = getattr(logging, lvl)
            if isinstance(level_val, int):
                logging.getLogger().setLevel(level_val)
                logging.info(f"Nivel global de logging cambiado dinámicamente a: {lvl}")
                return lvl
        raise ValueError(f"Nivel de log inválido: {level_name}")

    def collect_health_snapshot(self) -> dict[str, Any]:
        """Recolecta un resumen de salud y rendimiento de todos los subsistemas."""
        serial_adapter = getattr(self.bridge, "serial_adapter", None)
        mqtt_client = getattr(self.bridge, "mqtt", None)
        rate_limiter = getattr(self.bridge, "rate_limiter", None)
        node_registry = getattr(self.bridge, "node_registry", None)

        serial_status = {
            "connected": getattr(serial_adapter, "is_connected", False) if serial_adapter else False,
            "port": getattr(serial_adapter, "port", "desconocido") if serial_adapter else "none",
            "baudrate": getattr(serial_adapter, "baud_rate", 115200) if serial_adapter else 0,
            "last_heartbeat": getattr(serial_adapter, "last_heartbeat_time", 0) if serial_adapter else 0,
        }

        mqtt_status = {
            "connected": getattr(mqtt_client, "is_connected", False) if mqtt_client else False,
            "broker": getattr(mqtt_client, "broker", "desconocido") if mqtt_client else "none",
            "port": getattr(mqtt_client, "port", 1883) if mqtt_client else 0,
            "reconnect_count": getattr(mqtt_client, "reconnect_count", 0) if mqtt_client else 0,
        }

        return {
            "status": "healthy" if serial_status["connected"] and mqtt_status["connected"] else "degraded",
            "timestamp": time.time(),
            "uptime_seconds": int(time.time() - getattr(self.bridge, "start_time", time.time())),
            "subsystems": {
                "serial_companion": serial_status,
                "mqtt_broker": mqtt_status,
                "rate_limiter": {
                    "queue_depth": rate_limiter.get_queue_depth() if rate_limiter else 0,
                },
                "mesh_nodes": {
                    "known_count": node_registry.get_count() if node_registry else 0,
                },
            },
            "counters": {
                "rx_packets": getattr(self.bridge, "rx_count", 0),
                "tx_packets": getattr(self.bridge, "tx_count", 0),
                "tx_errors": getattr(self.bridge, "tx_error_count", 0),
                "log_errors": self.log_handler.error_count,
                "log_warnings": self.log_handler.warn_count,
            },
            "last_error": {
                "timestamp": self.log_handler.last_error_time,
                "message": self.log_handler.last_error_msg,
            }
            if self.log_handler.last_error_time
            else None,
        }

    def generate_full_diagnostic_bundle(self) -> dict[str, Any]:
        """Genera un paquete de diagnóstico integral listo para exportar en JSON."""
        health = self.collect_health_snapshot()

        preflight_results = None
        preflight_checker = getattr(self.bridge, "preflight", None)
        if preflight_checker and hasattr(preflight_checker, "run_all"):
            import config

            try:
                preflight_results = preflight_checker.run_all(
                    mqtt_host=config.MQTT_BROKER,
                    mqtt_port=config.MQTT_PORT,
                    serial_port=getattr(
                        self.bridge.serial_adapter, "port", config.SERIAL_PORT
                    ),
                )
            except Exception as e:
                preflight_results = {"status": "ERROR", "error": str(e)}

        return {
            "app_name": "MeshCore Bridge",
            "version": "3.0.0",
            "report_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "environment": {
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "python_version": sys.version,
            },
            "health_snapshot": health,
            "preflight_checks": preflight_results,
            "recent_logs": self.log_handler.get_logs(limit=200),
        }

    def generate_markdown_report(self) -> str:
        """
        Genera un informe diagnóstico completo formateado en Markdown, optimizado
        para copiar y pegar directamente a un asistente de IA o equipo de soporte.
        """
        bundle = self.generate_full_diagnostic_bundle()
        health = bundle.get("health_snapshot", {})
        sub = health.get("subsystems", {})
        counters = health.get("counters", {})
        env = bundle.get("environment", {})
        preflight = bundle.get("preflight_checks") or {}

        status_emoji = "🟢 SALUDABLE" if health.get("status") == "healthy" else "🟡 DEGRADADO / CON INCIDENCIAS"

        lines: list[str] = []
        lines.append(f"# 📡 Reporte de Diagnóstico - MeshCore Bridge v{bundle.get('version', '3.0.0')}")
        lines.append(f"**Fecha y Hora (UTC):** `{bundle.get('report_timestamp')}`")
        lines.append(f"**Estado General:** {status_emoji}")
        lines.append(f"**Tiempo Activo (Uptime):** `{health.get('uptime_seconds', 0)} segundos`\n")

        lines.append("## 💻 1. Entorno de Ejecución")
        lines.append(f"- **Sistema Operativo:** {env.get('os')} ({env.get('architecture')}) {env.get('os_release')}")
        lines.append(f"- **Python:** `{sys.version.splitlines()[0]}`\n")

        lines.append("## 🔌 2. Matriz de Subsistemas y Conectividad")
        ser = sub.get("serial_companion", {})
        mqtt = sub.get("mqtt_broker", {})
        rl = sub.get("rate_limiter", {})
        nodes = sub.get("mesh_nodes", {})

        ser_icon = "✅" if ser.get("connected") else "❌"
        mqtt_icon = "✅" if mqtt.get("connected") else "❌"

        lines.append("| Subsistema | Estado | Detalles |")
        lines.append("|---|---|---|")
        lines.append(f"| **Radio Serial Companion** | {ser_icon} `{'Conectado' if ser.get('connected') else 'Desconectado'}` | Puerto: `{ser.get('port')}` @ `{ser.get('baudrate')}` bps |")
        lines.append(f"| **Broker MQTT** | {mqtt_icon} `{'Online' if mqtt.get('connected') else 'Offline'}` | Host: `{mqtt.get('broker')}:{mqtt.get('port')}` (Reconexiones: {mqtt.get('reconnect_count', 0)}) |")
        lines.append("| **Persistencia Local JSON** | 💽 `Operativo` | Canales y nodos en almacenamiento atómico |")
        lines.append(f"| **Rate Limiter (Cola TX)** | ⏱️ `Activo` | Profundidad de cola: `{rl.get('queue_depth', 0)}` paquetes |")
        lines.append(f"| **Directorio de Nodos LoRa** | 📡 `Activo` | `{nodes.get('known_count', 0)}` nodos descubiertos en malla |\n")

        lines.append("## 📊 3. Métricas y Contadores de Tráfico")
        lines.append(f"- **Paquetes RX (LoRa -> Bridge):** `{counters.get('rx_packets', 0)}`")
        lines.append(f"- **Paquetes TX (Bridge -> LoRa):** `{counters.get('tx_packets', 0)}`")
        lines.append(f"- **Errores de Transmisión TX:** `{counters.get('tx_errors', 0)}`")
        lines.append(f"- **Errores Registrados en Logs:** `{counters.get('log_errors', 0)}`")
        lines.append(f"- **Advertencias en Logs:** `{counters.get('log_warnings', 0)}`\n")

        if preflight and isinstance(preflight, dict) and "checks" in preflight:
            lines.append("## 🔍 4. Diagnóstico Preflight de Subsistemas")
            lines.append(f"**Estado General Preflight:** `{preflight.get('status')}`")
            lines.append("| Comprobación | Estado | Mensaje |")
            lines.append("|---|---|---|")
            for chk in preflight.get("checks", []):
                chk_icon = "✅" if chk.get("status") == "PASS" else "⚠️" if chk.get("status") == "WARN" else "❌"
                lines.append(f"| `{chk.get('name')}` | {chk_icon} `{chk.get('status')}` | {chk.get('message')} |")
            lines.append("")

        # Sección de Errores y Excepciones Recientes
        error_logs = [log for log in bundle.get("recent_logs", []) if log.get("level") in ("ERROR", "CRITICAL")]
        lines.append("## 🚨 5. Excepciones y Errores Recientes")
        if error_logs:
            for err in error_logs[-5:]:
                lines.append(f"### ❌ [{err.get('iso_time')}] `{err.get('logger')}` - {err.get('message')}")
                if err.get("exception"):
                    lines.append("```text")
                    lines.append(err["exception"])
                    lines.append("```")
        else:
            lines.append("✨ *No se registran excepciones ni errores críticos recientes en el búfer.*")
        lines.append("")

        # Últimas líneas de logs
        lines.append("## 📜 6. Últimos Registros de Log del Sistema")
        lines.append("```log")
        tail_records = bundle.get("recent_logs", [])[-30:]
        if tail_records:
            for r in tail_records:
                lines.append(f"[{r.get('iso_time')}] [{r.get('level')}] [{r.get('module')}] {r.get('message')}")
        else:
            lines.append("Búfer de logs vacío.")
        lines.append("```")

        return "\n".join(lines)

    def get_raw_log_tail(self, lines: int = 100) -> str:
        """Lee y retorna las últimas N líneas del archivo de log principal en disco."""
        import config

        log_path = getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log")
        p = Path(log_path)
        if not p.exists() or not p.is_file():
            # Fallback a búfer en memoria formateado
            mem_logs = self.log_handler.get_logs(limit=lines)
            return "\n".join(f"[{r.get('iso_time')}] [{r.get('level')}] {r.get('message')}" for r in mem_logs)

        try:
            from collections import deque
            with open(p, encoding="utf-8", errors="ignore") as f:
                tail = deque(f, maxlen=lines)
                return "".join(tail)
        except Exception as e:
            return f"Error leyendo archivo de logs: {e}"

    def get_raw_log_path(self) -> str | None:
        """Devuelve la ruta absoluta al archivo de log si existe."""
        import config

        log_path = getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log")
        p = Path(log_path).resolve()
        return str(p) if p.exists() else None


def setup_file_logging(
    log_file_path: str | Path | None = None,
    error_file_path: str | Path | None = None,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    level: str = "INFO",
) -> tuple[logging.Handler | None, logging.Handler | None]:
    """
    Configura y adjunta manejadores de archivos rotativos (`RotatingFileHandler`) al root logger de Python.
    Garantiza la creación del directorio de logs y soporte para archivo general y archivo de errores.
    """
    import logging.handlers

    root_logger = logging.getLogger()
    lvl = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(lvl)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    general_handler: logging.Handler | None = None
    error_handler: logging.Handler | None = None

    if log_file_path:
        p_main = Path(log_file_path)
        try:
            p_main.parent.mkdir(parents=True, exist_ok=True)
            h_main = logging.handlers.RotatingFileHandler(
                filename=str(p_main),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            h_main.setLevel(lvl)
            h_main.setFormatter(formatter)
            root_logger.addHandler(h_main)
            general_handler = h_main
        except Exception as e:
            print(f"[WARN] No se pudo inicializar archivo de logs principal ({log_file_path}): {e}", file=sys.stderr)

    if error_file_path:
        p_err = Path(error_file_path)
        try:
            p_err.parent.mkdir(parents=True, exist_ok=True)
            h_err = logging.handlers.RotatingFileHandler(
                filename=str(p_err),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            h_err.setLevel(logging.WARNING)
            h_err.setFormatter(formatter)
            root_logger.addHandler(h_err)
            error_handler = h_err
        except Exception as e:
            print(f"[WARN] No se pudo inicializar archivo de logs de errores ({error_file_path}): {e}", file=sys.stderr)

    return general_handler, error_handler

