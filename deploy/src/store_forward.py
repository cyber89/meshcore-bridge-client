"""
Store & Forward Persistence and Packet Deduplication Layer for MeshCore Bridge.
Implementa almacenamiento persistente en SQLite con transacciones WAL, TTL configurable
y filtrado inteligente de paquetes duplicados.
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

_T = TypeVar("_T")


@dataclass(slots=True)
class StoredMessage:
    """Objeto de parámetro para enqueue: agrupa tópico, payload y opciones de QoS/TTL."""
    topic: str
    payload: str
    qos: int = 0
    retain: bool = False
    msg_hash: str | None = None
    ttl_seconds: float | None = None


class PacketDeduplicator:
    """Filtro de deduplicación de alta velocidad en memoria RAM con ventana deslizante."""

    def __init__(self, window_seconds: float = 60.0, max_entries: int = 5000) -> None:
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self._cache: collections.OrderedDict[str, float] = collections.OrderedDict()

    async def is_duplicate(self, key: str) -> bool:
        """Verifica si la clave ha sido vista recientemente dentro de la ventana de tiempo."""
        now = time.time()
        self._prune(now)

        if key in self._cache:
            last_seen = self._cache[key]
            if (now - last_seen) < self.window_seconds:
                return True

        self._cache[key] = now
        self._cache.move_to_end(key)

        if len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

        return False

    def _prune(self, now: float) -> None:
        """Elimina entradas expiradas del inicio del OrderedDict."""
        cutoff = now - self.window_seconds
        while self._cache:
            first_key = next(iter(self._cache))
            if self._cache[first_key] < cutoff:
                del self._cache[first_key]
            else:
                break


class SQLiteStoreAndForward:
    """Buffer offline persistente en SQLite con modo WAL, expiración TTL y transacciones seguras."""

    def __init__(
        self,
        db_path: str,
        max_size: int = 1000,
        default_ttl_hours: float = 48.0,
    ) -> None:
        self.db_path = db_path
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_hours * 3600.0
        self._db_lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_conn() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS offline_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        qos INTEGER DEFAULT 0,
                        retain INTEGER DEFAULT 0,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS message_receipts (
                        msg_id TEXT PRIMARY KEY,
                        sender TEXT,
                        recipient TEXT,
                        status TEXT DEFAULT 'pending',
                        sent_at REAL,
                        delivered_at REAL,
                        trip_time_ms REAL DEFAULT 0.0,
                        signature TEXT,
                        expected_ack TEXT
                    );
                """)
                # Migración automática si faltan columnas en bases de datos existentes
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(offline_queue);")
                columns = [row[1] for row in cursor.fetchall()]
                if "msg_hash" not in columns:
                    conn.execute("ALTER TABLE offline_queue ADD COLUMN msg_hash TEXT;")
                if "expires_at" not in columns:
                    conn.execute("ALTER TABLE offline_queue ADD COLUMN expires_at REAL DEFAULT 0;")
                    conn.execute("UPDATE offline_queue SET expires_at = created_at + 172800 WHERE expires_at = 0;")

                cursor.execute("PRAGMA table_info(message_receipts);")
                receipt_columns = [row[1] for row in cursor.fetchall()]
                if "expected_ack" not in receipt_columns:
                    conn.execute("ALTER TABLE message_receipts ADD COLUMN expected_ack TEXT;")

                conn.executescript("""
                    CREATE INDEX IF NOT EXISTS idx_offline_queue_created ON offline_queue(created_at);
                    CREATE INDEX IF NOT EXISTS idx_offline_queue_expires ON offline_queue(expires_at);
                    CREATE INDEX IF NOT EXISTS idx_offline_queue_hash ON offline_queue(msg_hash);
                    CREATE INDEX IF NOT EXISTS idx_receipts_status ON message_receipts(status);
                    CREATE INDEX IF NOT EXISTS idx_receipts_recipient ON message_receipts(recipient);
                    CREATE INDEX IF NOT EXISTS idx_receipts_expected_ack ON message_receipts(expected_ack);
                """)
        except Exception as e:
            logging.error(f"Error inicializando SQLite Store & Forward DB ({self.db_path}): {e}")

    def record_outbound_message(
        self,
        msg_id: str,
        sender: str = "local",
        recipient: str = "",
        expected_ack: str | None = None,
    ) -> bool:
        """Registra un mensaje saliente para monitorear su confirmación de entrega."""
        now = time.time()
        ack_clean = expected_ack.strip().lower() if expected_ack else None
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO message_receipts (msg_id, sender, recipient, status, sent_at, expected_ack)
                    VALUES (?, ?, ?, 'sent', ?, ?);
                    """,
                    (msg_id, sender, recipient, now, ack_clean),
                )
            return True
        except Exception as e:
            logging.error(f"Error registrando mensaje saliente {msg_id}: {e}")
            return False

    def mark_message_delivered(self, msg_id: str, trip_time_ms: float = 0.0, signature: str | None = None) -> bool:
        """Marca un mensaje como entregado con su tiempo de tránsito (trip time) y firma."""
        now = time.time()
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    UPDATE message_receipts
                    SET status = 'delivered', delivered_at = ?, trip_time_ms = ?, signature = ?
                    WHERE msg_id = ?;
                    """,
                    (now, trip_time_ms, signature, msg_id),
                )
            return True
        except Exception as e:
            logging.error(f"Error actualizando estado de entrega para {msg_id}: {e}")
            return False

    def get_msg_id_by_expected_ack(self, expected_ack: str) -> str | None:
        """Busca el msg_id asociado a un código de ACK de radio de 4 bytes (hex)."""
        if not expected_ack:
            return None
        ack_clean = str(expected_ack).strip().lower()
        ack_no_prefix = ack_clean[2:] if ack_clean.startswith("0x") else ack_clean
        ack_with_prefix = f"0x{ack_no_prefix}"
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT msg_id FROM message_receipts WHERE lower(expected_ack) IN (?, ?, ?) ORDER BY sent_at DESC LIMIT 1;",
                    (ack_clean, ack_no_prefix, ack_with_prefix),
                )
                row = cursor.fetchone()
                if row:
                    return str(row[0])
            return None
        except Exception as e:
            logging.error(f"Error buscando mensaje por expected_ack {expected_ack}: {e}")
            return None

    def get_message_status(self, msg_id: str) -> dict[str, Any] | None:
        """Consulta el estado de entrega de un mensaje específico."""
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM message_receipts WHERE msg_id = ?;", (msg_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
            return None
        except Exception as e:
            logging.error(f"Error consultando recibo {msg_id}: {e}")
            return None

    def compute_hash(self, topic: str, payload: str) -> str:
        """Genera un hash SHA-256 corto del tópico y payload para deduplicación."""
        hasher = hashlib.sha256()
        hasher.update(topic.encode("utf-8"))
        hasher.update(b"::")
        hasher.update(payload.encode("utf-8"))
        return hasher.hexdigest()[:16]

    def _execute_sync(self, func: Callable[..., _T], *args: Any) -> _T:
        with self._db_lock:
            return func(*args)

    async def _run_db(self, func: Callable[..., _T], *args: Any) -> _T:
        return await asyncio.to_thread(self._execute_sync, func, *args)

    async def enqueue(self, message: StoredMessage) -> bool:
        return await self._run_db(self._enqueue, message)

    def _enqueue(self, message: StoredMessage) -> bool:
        """Encola un mensaje en SQLite respetando TTL y límites de capacidad."""
        now = time.time()
        ttl = message.ttl_seconds if message.ttl_seconds is not None else self.default_ttl_seconds
        expires_at = now + ttl
        h = message.msg_hash or self.compute_hash(message.topic, message.payload)

        try:
            with self._get_conn() as conn:
                # 1. Purga periódica de mensajes expirados
                conn.execute("DELETE FROM offline_queue WHERE expires_at < ?;", (now,))

                # 2. Insertar nuevo mensaje
                conn.execute(
                    """
                    INSERT INTO offline_queue
                    (topic, payload, qos, retain, msg_hash, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (message.topic, message.payload, message.qos, 1 if message.retain else 0, h, now, expires_at),
                )

                # 3. Mantener tamaño máximo (estrategia circular FIFO)
                conn.execute(
                    """
                    DELETE FROM offline_queue
                    WHERE id NOT IN (
                        SELECT id FROM offline_queue ORDER BY id DESC LIMIT ?
                    );
                    """,
                    (self.max_size,),
                )
                return True
        except Exception as e:
            logging.error(f"Error encolando en SQLite offline buffer: {e}")
            return False

    async def dequeue_batch(self, limit: int = 50) -> list[tuple[int, str, str, int, int]]:
        return await self._run_db(self._dequeue_batch, limit)

    def _dequeue_batch(self, limit: int = 50) -> list[tuple[int, str, str, int, int]]:
        """Obtiene un lote de mensajes pendientes no expirados en orden FIFO."""
        now = time.time()
        try:
            with self._get_conn() as conn:
                # Purgar expirados primero
                conn.execute("DELETE FROM offline_queue WHERE expires_at < ?;", (now,))

                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, topic, payload, qos, retain FROM offline_queue ORDER BY id ASC LIMIT ?;",
                    (limit,),
                )
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error leyendo de SQLite offline buffer: {e}")
            return []

    async def delete_batch(self, msg_id: int) -> None:
        await self._run_db(self._delete_batch, msg_id)

    def _delete_batch(self, msg_id: int) -> None:
        """Elimina un mensaje entregado exitosamente."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM offline_queue WHERE id = ?;", (msg_id,))
        except Exception as e:
            logging.error(f"Error eliminando mensaje {msg_id} de SQLite: {e}")

    async def purge_expired(self) -> int:
        return await self._run_db(self._purge_expired)

    def _purge_expired(self) -> int:
        """Elimina todos los mensajes cuya fecha de expiración haya pasado."""
        now = time.time()
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM offline_queue WHERE expires_at < ?;", (now,))
                return cursor.rowcount
        except Exception as e:
            logging.error(f"Error purgando mensajes expirados: {e}")
            return 0

    async def count(self) -> int:
        return await self._run_db(self._count)

    def _count(self) -> int:
        """Retorna la cantidad actual de mensajes pendientes."""
        now = time.time()
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM offline_queue WHERE expires_at >= ?;", (now,))
                row = cursor.fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            logging.error(f"Error obteniendo tamaño del buffer SQLite: {e}")
            return 0

    async def clear(self) -> None:
        await self._run_db(self._clear)

    def _clear(self) -> None:
        """Vacía por completo la cola persistente."""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM offline_queue;")
        except Exception as e:
            logging.error(f"Error vaciando SQLite offline buffer: {e}")
