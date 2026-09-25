"""
Serial Watchdog and Auto-Reconnection Monitor for MeshCore Bridge.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from src.serial.serial_base import BaseSerialAdapter


class SerialWatchdog:
    """Supervisa la vivacidad del puerto serial y activa reconexión segura ante bloqueos o caídas de hardware."""

    def __init__(
        self,
        adapter: BaseSerialAdapter,
        timeout_sec: float = 90.0,
        interval_sec: float = 30.0,
        on_timeout_reconnect: Callable[[], Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.timeout_sec = timeout_sec
        self.interval_sec = interval_sec
        self.on_timeout_reconnect = on_timeout_reconnect
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._consecutive_ping_failures = 0
        self._total_reconnect_attempts: int = 0
        self._reconnect_backoff_sec: float = 5.0
        try:
            import config
            self.max_reconnect_attempts = int(getattr(config, "MAX_RECONNECT_ATTEMPTS", os.getenv("MAX_RECONNECT_ATTEMPTS", "0")))
        except Exception:
            self.max_reconnect_attempts = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "0"))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._supervise_loop(), name="SerialWatchdog")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _supervise_loop(self) -> None:
        while self._running:
            try:
                # Comprobación proactiva y rápida de presencia física USB cada 2 segundos (o interval_sec si es menor)
                step_sleep = min(2.0, max(0.005, self.interval_sec))
                steps = max(1, int(self.interval_sec / step_sleep))
                for _ in range(steps):
                    if not self._running:
                        break
                    await asyncio.sleep(step_sleep)
                    if self.adapter.is_connected and hasattr(self.adapter, "is_hardware_alive"):
                        if not self.adapter.is_hardware_alive():
                            logging.warning("Watchdog Serial: Transceptor LoRa desconectado físicamente del puerto USB.")
                            self.adapter.is_connected = False
                            break

                now = time.time()
                idle_sec = now - self.adapter.last_heartbeat_time

                # 1. CASO DESCONECTADO: Reintentar reconexión automática periódica en background
                if not self.adapter.is_connected:
                    if self.max_reconnect_attempts > 0 and self._total_reconnect_attempts >= self.max_reconnect_attempts:
                        logging.warning(
                            f"Watchdog Serial: Se alcanzó el límite máximo de reintentos ({self.max_reconnect_attempts}). "
                            "Entrando en modo dormant (reintentando cada 300s)..."
                        )
                        await asyncio.sleep(300.0)
                    else:
                        reconnect_wait = min(self._reconnect_backoff_sec, max(0.005, self.interval_sec))
                        logging.info(
                            f"Watchdog Serial: Adaptador desconectado. Reintentando conexión con transceptor en {reconnect_wait:.2f}s..."
                        )
                        await asyncio.sleep(reconnect_wait)

                    self._total_reconnect_attempts += 1
                    if self.on_timeout_reconnect:
                        res = self.on_timeout_reconnect()
                        if asyncio.iscoroutine(res):
                            await res
                    if not self.adapter.is_connected:
                        self._reconnect_backoff_sec = min(self._reconnect_backoff_sec * 1.5, 30.0)
                    else:
                        self._reconnect_backoff_sec = 5.0
                        self._consecutive_ping_failures = 0
                        self._total_reconnect_attempts = 0
                    continue

                # 2. CASO CONECTADO: Si no ha habido tráfico RF reciente, verificar vivacidad mediante ping suave
                if idle_sec > self.timeout_sec:
                    logging.debug(f"Watchdog Serial: Sin tráfico RF en {idle_sec:.1f}s. Comprobando respuesta del transceptor...")
                    try:
                        is_alive = await asyncio.wait_for(self.adapter.ping_or_check_alive(), timeout=10.0)
                    except asyncio.TimeoutError:
                        is_alive = False
                        logging.warning("Watchdog ping timeout")
                    if is_alive:
                        # El nodo local responde perfectamente al ping (solo hay silencio de radio en la malla)
                        self._consecutive_ping_failures = 0
                        self.adapter.heartbeat()
                        logging.debug("Watchdog Serial: Transceptor local respondió al ping de vivacidad. Enlace serial saludable.")
                    else:
                        self._consecutive_ping_failures += 1
                        logging.warning(
                            f"Watchdog Serial: Transceptor local no respondió al ping de vivacidad (Fallo {self._consecutive_ping_failures}/2)."
                        )

                        # Solo si falla 2 comprobaciones consecutivas (ej. 1 minuto sin responder pings locales)
                        if self._consecutive_ping_failures >= 2:
                            logging.error(
                                "Watchdog Serial: Puerto serial bloqueado o no responsivo tras 2 pings consecutivos. "
                                "Iniciando ciclo de reconexión segura..."
                            )
                            self._consecutive_ping_failures = 0
                            if self.on_timeout_reconnect:
                                res = self.on_timeout_reconnect()
                                if asyncio.iscoroutine(res):
                                    await res
                            self.adapter.heartbeat()
                else:
                    self._consecutive_ping_failures = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error en bucle de supervisión SerialWatchdog: {e}")
