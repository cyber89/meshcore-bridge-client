"""message_retry_scheduler.py: Planificador y máquina de estados de reintentos LoRa.

Gestiona reintentos automáticos acotados con backoff exponencial y jitter, reenvío manual
y cancelación, respetando las invariantes de dominio y el presupuesto de airtime de LoRa.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import Any

from src.station_database import StationDatabase

logger = logging.getLogger(__name__)


class MessageRetryScheduler:
    """Coordina el ciclo de vida, persistencia y despacho de reintentos de mensajería."""

    def __init__(
        self,
        database_provider: Callable[[], StationDatabase | None],
        tx_coordinator_provider: Callable[[], Any],
        is_cutoff_active_fn: Callable[[], bool] | None = None,
        is_serial_connected_fn: Callable[[], bool] | None = None,
        broadcast_ws_fn: Callable[[dict[str, Any]], None] | None = None,
        *,
        auto_retry_enabled: bool = True,
        max_retries: int = 2,
        ack_timeout_s: float = 30.0,
        backoff_multiplier: float = 1.5,
        jitter_range_s: float = 3.0,
        stale_expiration_s: float = 900.0,  # 15 minutos (acordado en /grill-me)
    ) -> None:
        self.database_provider = database_provider
        self.tx_coordinator_provider = tx_coordinator_provider
        self.is_cutoff_active_fn = is_cutoff_active_fn or (lambda: False)
        self.is_serial_connected_fn = is_serial_connected_fn or (lambda: True)
        self.broadcast_ws_fn = broadcast_ws_fn or (lambda _: None)

        self.auto_retry_enabled = auto_retry_enabled
        self.max_retries = max(1, min(3, int(max_retries)))
        self.ack_timeout_s = max(10.0, float(ack_timeout_s))
        self.backoff_multiplier = max(1.0, float(backoff_multiplier))
        self.jitter_range_s = max(0.5, float(jitter_range_s))
        self.stale_expiration_s = max(60.0, float(stale_expiration_s))

        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._lock = asyncio.Lock()

    def get_config(self) -> dict[str, Any]:
        """Devuelve la configuración activa de reintentos."""
        return {
            "auto_retry_enabled": self.auto_retry_enabled,
            "max_retries": self.max_retries,
            "ack_timeout_s": self.ack_timeout_s,
            "backoff_multiplier": self.backoff_multiplier,
            "jitter_range_s": self.jitter_range_s,
            "stale_expiration_s": self.stale_expiration_s,
        }

    def update_config(
        self,
        auto_retry_enabled: bool | None = None,
        max_retries: int | None = None,
        ack_timeout_s: float | None = None,
    ) -> dict[str, Any]:
        """Actualiza y persiste la configuración activa de reintentos."""
        if auto_retry_enabled is not None:
            self.auto_retry_enabled = bool(auto_retry_enabled)
        if max_retries is not None:
            self.max_retries = max(1, min(3, int(max_retries)))
        if ack_timeout_s is not None:
            self.ack_timeout_s = max(10.0, min(120.0, float(ack_timeout_s)))

        db = self.database_provider()
        if db is not None:
            try:
                db.write_document("messaging_config", self.get_config())
            except Exception as e:
                logger.warning("Error persistiendo messaging_config en base de datos: %s", e)

        return self.get_config()

    def load_config_from_database(self) -> None:
        """Carga la configuración persistida desde la base de datos si existe."""
        db = self.database_provider()
        if db is not None:
            try:
                saved = db.read_document("messaging_config")
                if isinstance(saved, dict):
                    if "auto_retry_enabled" in saved:
                        self.auto_retry_enabled = bool(saved["auto_retry_enabled"])
                    if "max_retries" in saved:
                        self.max_retries = max(1, min(3, int(saved["max_retries"])))
                    if "ack_timeout_s" in saved:
                        self.ack_timeout_s = max(10.0, min(120.0, float(saved["ack_timeout_s"])))
            except Exception as e:
                logger.debug("No se pudo cargar messaging_config: %s", e)

    async def start(self) -> None:
        """Inicia el planificador de reintentos y limpia tareas obsoletas de reinicio previo."""
        if self._running:
            return
        self._running = True
        self.load_config_from_database()

        db = self.database_provider()
        if db is not None:
            # 1. Prune stale: si el bridge estuvo apagado más de 15 min, expira a 'failed'
            expired = db.prune_stale_retries(self.stale_expiration_s)
            if expired:
                logger.info(
                    "Reintentos obsoletos expirados tras reinicio (>%ds): %d mensajes",
                    self.stale_expiration_s,
                    len(expired),
                )
                for mid in expired:
                    self._notify_status_change(mid, "failed", reason="stale_after_restart")

            # 2. Re-escalonar reintentos pendientes legítimos para evitar ráfagas al arrancar
            pending = db.get_all_pending_retries()
            if pending:
                logger.info(
                    "Re-escalonando %d reintentos pendientes tras inicio del bridge", len(pending)
                )
                base_time = time.time() + 5.0
                for idx, item in enumerate(pending):
                    staggered_epoch = base_time + (idx * 10.0)
                    db.save_pending_retry(
                        msg_id=item["msg_id"],
                        target=item["target"],
                        text=item["text"],
                        channel_idx=item.get("channel_idx", 0),
                        attempt_count=item.get("attempt_count", 1),
                        max_attempts=item.get("max_attempts", self.max_retries),
                        next_attempt_epoch=staggered_epoch,
                        created_epoch=item.get("created_epoch", time.time()),
                        status="retrying",
                    )

        self._task = asyncio.create_task(self._run_loop(), name="MessageRetryScheduler")

    async def stop(self) -> None:
        """Detiene de forma limpia el bucle del planificador."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def calculate_next_delay(self, attempt_count: int) -> float:
        """Calcula el tiempo de espera para el intento actual con curva exponencial y jitter."""
        # Intento 1: 30s + jitter; Intento 2: 30 * 1.5 = 45s + jitter
        exp_factor = self.backoff_multiplier ** max(0, attempt_count - 1)
        base = self.ack_timeout_s * exp_factor
        jitter = random.uniform(-self.jitter_range_s, self.jitter_range_s)
        return max(5.0, round(base + jitter, 1))

    def schedule_retry(
        self,
        msg_id: str,
        target: str,
        text: str,
        channel_idx: int = 0,
        attempt_count: int = 1,
    ) -> bool:
        """Programa un reintento para un mensaje saliente que no ha recibido ACK."""
        if not self.auto_retry_enabled:
            return False
        if attempt_count > self.max_retries:
            return False

        delay = self.calculate_next_delay(attempt_count)
        next_epoch = time.time() + delay
        created_epoch = time.time()

        db = self.database_provider()
        if db is not None:
            db.save_pending_retry(
                msg_id=msg_id,
                target=target,
                text=text,
                channel_idx=channel_idx,
                attempt_count=attempt_count,
                max_attempts=self.max_retries,
                next_attempt_epoch=next_epoch,
                created_epoch=created_epoch,
                status="retrying",
            )
            # Actualizar estado del mensaje en la tabla principal
            try:
                db.update_delivery({"msg_id": msg_id, "status": "retrying"})
            except Exception as e:
                logger.debug("Error actualizando status 'retrying' en DB: %s", e)

        self._notify_status_change(
            msg_id=msg_id,
            status="retrying",
            attempt=attempt_count,
            max_attempts=self.max_retries,
            next_attempt_s=round(delay, 1),
            target=target,
        )
        logger.info(
            "Reintento #%d/%d programado para msg_id=%s en %.1fs",
            attempt_count,
            self.max_retries,
            msg_id,
            delay,
        )
        return True

    def cancel_retry(self, msg_id: str) -> bool:
        """Cancela explícitamente cualquier reintento programado para un mensaje."""
        db = self.database_provider()
        if db is not None:
            removed = db.remove_pending_retry(msg_id)
            try:
                db.update_delivery({"msg_id": msg_id, "status": "cancelled"})
            except Exception as e:
                logger.debug("Error actualizando status 'cancelled' en DB: %s", e)
        else:
            removed = False

        self._notify_status_change(msg_id=msg_id, status="cancelled")
        logger.info("Reintento cancelado por el usuario para msg_id=%s", msg_id)
        return removed

    async def resend_message(self, msg_id: str) -> tuple[bool, str, dict[str, Any] | None]:
        """Dispara un reenvío manual solicitado por el usuario para un mensaje fallido o cancelado."""
        db = self.database_provider()
        if db is None:
            return False, "Base de datos no disponible", None

        # Recuperar mensaje de la base de datos
        history_res = db.history(limit=500)
        found_msg: dict[str, Any] | None = None
        for m in history_res.get("messages", []):
            if m.get("msg_id") == msg_id or m.get("id") == msg_id:
                found_msg = m
                break

        if not found_msg:
            return False, f"Mensaje '{msg_id}' no encontrado en historial", None

        # Validar que sea un mensaje saliente
        if not found_msg.get("is_outgoing", False) and found_msg.get("direction") != "outgoing":
            return False, "No se puede reenviar un mensaje entrante", None

        target = str(found_msg.get("dm_target") or found_msg.get("recipient") or found_msg.get("target") or "broadcast")
        text = str(found_msg.get("text") or "")
        channel_idx = int(found_msg.get("channel_idx") or 0)
        is_broadcast = target in ("broadcast", "public", "0xffff", "") or target.startswith("channel")

        # Invariantes de dominio (AGENTS.md §1.1)
        if not is_broadcast:
            tx_coord = self.tx_coordinator_provider()
            if tx_coord is not None:
                err = tx_coord.validate_tx_target(target, text, is_broadcast)
                if err:
                    return False, err, None

        # Cancelar cualquier reintento anterior pendiente
        db.remove_pending_retry(msg_id)

        # Actualizar a 'queued'
        db.update_delivery({"msg_id": msg_id, "status": "queued"})
        self._notify_status_change(msg_id=msg_id, status="queued", target=target)

        # Ejecutar transmisión por radio a través de TxCoordinator
        tx_coord = self.tx_coordinator_provider()
        if not tx_coord:
            return False, "Coordinador de transmisión no disponible", None

        tx_item = {
            "request_id": msg_id,
            "to": target,
            "target": target,
            "channel_idx": channel_idx,
            "text": text,
            "message": text,
        }
        res = await tx_coord.execute_tx(tx_item)

        # Si es un DM y se transmitió con éxito, programar el ciclo de reintentos
        if not is_broadcast and res.get("status") == "sent" and self.auto_retry_enabled:
            self.schedule_retry(
                msg_id=msg_id,
                target=target,
                text=text,
                channel_idx=channel_idx,
                attempt_count=1,
            )

        return True, "Mensaje reenviado", res

    def _notify_status_change(
        self,
        msg_id: str,
        status: str,
        attempt: int = 0,
        max_attempts: int = 0,
        next_attempt_s: float = 0.0,
        target: str = "",
        reason: str = "",
    ) -> None:
        """Emite un evento WebSocket hacia la SPA para actualizar la UI en tiempo real."""
        payload = {
            "type": "message_status",
            "event": "message_status",
            "msg_id": msg_id,
            "status": status,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "next_attempt_s": next_attempt_s,
            "target": target,
            "reason": reason,
            "timestamp": time.time(),
        }
        try:
            self.broadcast_ws_fn(payload)
        except Exception as e:
            logger.debug("Error emitiendo WebSocket message_status: %s", e)

    async def _run_loop(self) -> None:
        """Bucle periódico de evaluación y despacho de reintentos pendientes."""
        while self._running:
            try:
                await asyncio.sleep(2.0)
                if not self._running:
                    break

                # Comprobar condiciones de bloqueo de radio (Airtime Cutoff o caída Serial)
                if self.is_cutoff_active_fn():
                    logger.debug("MessageRetryScheduler pausado: Airtime Cutoff activo")
                    continue
                if not self.is_serial_connected_fn():
                    logger.debug("MessageRetryScheduler pausado: Transceptor no conectado")
                    continue

                db = self.database_provider()
                if db is None:
                    continue

                now = time.time()
                due_items = db.get_due_retries(now, limit=5)
                if not due_items:
                    continue

                tx_coord = self.tx_coordinator_provider()
                if not tx_coord:
                    continue

                for item in due_items:
                    msg_id = item["msg_id"]
                    target = item["target"]
                    text = item["text"]
                    channel_idx = item.get("channel_idx", 0)
                    current_attempt = item.get("attempt_count", 1)
                    max_attempts = item.get("max_attempts", self.max_retries)

                    # Si el mensaje ya fue entregado (recibió ACK en el ínterin)
                    history_res = db.history(limit=50)
                    delivered = False
                    for m in history_res.get("messages", []):
                        if (m.get("msg_id") == msg_id or m.get("id") == msg_id) and m.get("status") == "delivered":
                            delivered = True
                            break

                    if delivered:
                        db.remove_pending_retry(msg_id)
                        continue

                    if current_attempt >= max_attempts:
                        # Se agotaron todos los reintentos permitidos -> declarar 'failed'
                        logger.warning(
                            "Reintentos agotados (%d/%d) para msg_id=%s hacia %s. Declarando 'failed'",
                            current_attempt,
                            max_attempts,
                            msg_id,
                            target,
                        )
                        db.remove_pending_retry(msg_id)
                        try:
                            db.update_delivery({"msg_id": msg_id, "status": "failed"})
                        except Exception as e:
                            logger.debug("Error actualizando status 'failed' en DB: %s", e)
                        self._notify_status_change(
                            msg_id=msg_id,
                            status="failed",
                            attempt=current_attempt,
                            max_attempts=max_attempts,
                            target=target,
                            reason="max_retries_reached",
                        )
                    else:
                        # Disparar siguiente reintento
                        next_attempt = current_attempt + 1
                        logger.info(
                            "Ejecutando reintento #%d/%d para msg_id=%s hacia %s",
                            next_attempt,
                            max_attempts,
                            msg_id,
                            target,
                        )

                        # Despachar por radio vía TxCoordinator
                        tx_item = {
                            "request_id": msg_id,
                            "to": target,
                            "target": target,
                            "channel_idx": channel_idx,
                            "text": text,
                            "message": text,
                        }
                        res = await tx_coord.execute_tx(tx_item)

                        if res.get("status") == "sent":
                            # Programar el siguiente intervalo si aún no es el último
                            self.schedule_retry(
                                msg_id=msg_id,
                                target=target,
                                text=text,
                                channel_idx=channel_idx,
                                attempt_count=next_attempt,
                            )
                        else:
                            # Si la radio falló inmediatamente al enviar
                            logger.warning(
                                "Fallo inmediato al reintentar msg_id=%s: %s",
                                msg_id,
                                res.get("error", "Error de transmisión"),
                            )
                            # Re-programar con backoff adicional
                            self.schedule_retry(
                                msg_id=msg_id,
                                target=target,
                                text=text,
                                channel_idx=channel_idx,
                                attempt_count=next_attempt,
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error en bucle MessageRetryScheduler: %s", e, exc_info=True)
                await asyncio.sleep(5.0)
