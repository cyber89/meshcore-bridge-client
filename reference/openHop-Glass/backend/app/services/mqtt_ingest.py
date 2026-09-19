from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.contracts.v1.mqtt import (
    MqttAdvertEnvelopeV1,
    MqttEventEnvelopeV1,
    MqttPacketEnvelopeV1,
)
from app.db.models import (
    MqttIngestEvent,
    Packet,
    Repeater,
    TopologyNode,
    TopologyObservation,
    TopologyObservationSample,
    TopologyRollupHourly,
)
from app.services.telemetry_stream import MqttTelemetryBroadcaster

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    mqtt = None

logger = logging.getLogger("mqtt-ingest")


@dataclass(slots=True)
class NormalizedMqttMessage:
    topic: str
    node_name: str
    timestamp: datetime
    event_type: str
    event_name: str | None
    payload: dict[str, Any]
    dedup_key: str


@dataclass(slots=True)
class IngestProcessResult:
    status: str
    telemetry_event: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _to_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return _to_utc(datetime.fromisoformat(normalized))
    return _utc_now()


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _coerce_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return _parse_timestamp(value)
    except (TypeError, ValueError):
        return None


def _normalize_coordinates(latitude: Any, longitude: Any) -> tuple[float | None, float | None]:
    lat = _coerce_optional_float(latitude)
    lng = _coerce_optional_float(longitude)
    if lat is None or lng is None:
        return None, None
    if lat < -90 or lat > 90:
        return None, None
    if lng < -180 or lng > 180:
        return None, None
    return lat, lng


def _min_datetime(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if value is not None]
    if not candidates:
        return None
    return min(candidates)


def _max_datetime(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if value is not None]
    if not candidates:
        return None
    return max(candidates)


class MqttIngestProcessor:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def process_message(self, topic: str, payload_bytes: bytes) -> str:
        result = self.process_message_with_event(topic, payload_bytes)
        return result.status

    def process_message_with_event(self, topic: str, payload_bytes: bytes) -> IngestProcessResult:
        normalized = self._normalize_message(topic, payload_bytes)
        if normalized is None:
            return IngestProcessResult(status="invalid")

        with self._session_factory() as db:
            repeater = db.scalar(select(Repeater).where(Repeater.node_name == normalized.node_name))
            if repeater is None:
                return IngestProcessResult(status="unknown_repeater")

            existing_event = db.scalar(
                select(MqttIngestEvent.id).where(MqttIngestEvent.dedup_key == normalized.dedup_key)
            )
            if existing_event is not None:
                return IngestProcessResult(status="duplicate")

            ingested_at = _utc_now()
            event_row = MqttIngestEvent(
                repeater_id=repeater.id,
                timestamp=normalized.timestamp,
                event_type=normalized.event_type,
                event_name=normalized.event_name,
                topic=normalized.topic,
                payload_json=json.dumps(
                    normalized.payload,
                    default=str,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                dedup_key=normalized.dedup_key,
                ingested_at=ingested_at,
            )
            db.add(event_row)
            db.flush()

            if normalized.event_type == "packet":
                self._persist_packet(db, repeater_id=repeater.id, message=normalized)
            elif normalized.event_type == "advert":
                self._persist_advert_topology(
                    db,
                    repeater=repeater,
                    message=normalized,
                    ingested_at=ingested_at,
                )

            db.commit()
            return IngestProcessResult(
                status="ingested",
                telemetry_event={
                    "event_id": event_row.id,
                    "repeater_id": repeater.id,
                    "node_name": normalized.node_name,
                    "timestamp": normalized.timestamp.isoformat().replace("+00:00", "Z"),
                    "event_type": normalized.event_type,
                    "event_name": normalized.event_name,
                    "topic": normalized.topic,
                    "payload": normalized.payload,
                    "ingested_at": ingested_at.isoformat().replace("+00:00", "Z"),
                },
            )

    def _persist_packet(
        self,
        db: Session,
        *,
        repeater_id: str,
        message: NormalizedMqttMessage,
    ) -> None:
        packet_hash = _coerce_optional_str(message.payload.get("packet_hash")) or message.dedup_key
        existing_packet = db.scalar(select(Packet.id).where(Packet.packet_hash == packet_hash))
        if existing_packet is not None:
            return

        payload_value: Any = message.payload.get("payload")
        if isinstance(payload_value, (dict, list)):
            payload_text = json.dumps(
                payload_value,
                default=str,
                separators=(",", ":"),
                sort_keys=True,
            )
        elif payload_value is None:
            payload_text = None
        else:
            payload_text = str(payload_value)

        db.add(
            Packet(
                repeater_id=repeater_id,
                timestamp=message.timestamp,
                packet_type=_coerce_optional_str(message.payload.get("type")),
                route=_coerce_optional_str(message.payload.get("route")),
                rssi=_coerce_optional_float(message.payload.get("rssi")),
                snr=_coerce_optional_float(message.payload.get("snr")),
                src_hash=_coerce_optional_str(message.payload.get("src_hash")),
                dst_hash=_coerce_optional_str(message.payload.get("dst_hash")),
                payload=payload_text,
                packet_hash=packet_hash,
            )
        )

    def _persist_advert_topology(
        self,
        db: Session,
        *,
        repeater: Repeater,
        message: NormalizedMqttMessage,
        ingested_at: datetime,
    ) -> None:
        pubkey = _coerce_optional_str(message.payload.get("pubkey"))
        if not pubkey:
            return

        node_name = _coerce_optional_str(message.payload.get("node_name"))
        is_repeater = _coerce_optional_bool(message.payload.get("is_repeater"))
        contact_type = _coerce_optional_str(message.payload.get("contact_type"))
        route_type = _coerce_optional_int(message.payload.get("route_type"))
        zero_hop = _coerce_optional_bool(message.payload.get("zero_hop"))
        latitude, longitude = _normalize_coordinates(
            message.payload.get("latitude"),
            message.payload.get("longitude"),
        )
        rssi = _coerce_optional_float(message.payload.get("rssi"))
        snr = _coerce_optional_float(message.payload.get("snr"))
        advert_count = _coerce_optional_int(message.payload.get("advert_count"))
        last_seen = _coerce_optional_datetime(message.payload.get("last_seen")) or message.timestamp
        first_seen = _coerce_optional_datetime(message.payload.get("first_seen"))
        if first_seen is None:
            first_seen = last_seen
        if first_seen > last_seen:
            first_seen = last_seen

        normalized_pubkey = pubkey.strip().lower()
        topology_node = db.scalar(select(TopologyNode).where(TopologyNode.pubkey == normalized_pubkey))
        if topology_node is None:
            topology_node = TopologyNode(
                pubkey=normalized_pubkey,
                node_name=node_name,
                is_repeater=int(is_repeater) if is_repeater is not None else None,
                contact_type=contact_type,
                latitude=latitude,
                longitude=longitude,
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                last_observed_by_repeater_id=repeater.id,
            )
            db.add(topology_node)
            db.flush()
        else:
            if node_name is not None:
                topology_node.node_name = node_name
            if is_repeater is not None:
                topology_node.is_repeater = int(is_repeater)
            if contact_type is not None:
                topology_node.contact_type = contact_type
            if latitude is not None and longitude is not None:
                topology_node.latitude = latitude
                topology_node.longitude = longitude
            topology_node.first_seen_at = _min_datetime(topology_node.first_seen_at, first_seen)
            topology_node.last_seen_at = _max_datetime(topology_node.last_seen_at, last_seen) or last_seen
            topology_node.last_observed_by_repeater_id = repeater.id

        observation = db.scalar(
            select(TopologyObservation).where(
                TopologyObservation.observer_repeater_id == repeater.id,
                TopologyObservation.observed_node_id == topology_node.id,
            )
        )
        if observation is None:
            observation = TopologyObservation(
                observer_repeater_id=repeater.id,
                observed_node_id=topology_node.id,
                contact_type=contact_type,
                route_type=route_type,
                zero_hop=int(zero_hop) if zero_hop is not None else None,
                latitude=latitude,
                longitude=longitude,
                rssi=rssi,
                snr=snr,
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                advert_count=advert_count,
                last_event_timestamp=message.timestamp,
                last_ingested_at=ingested_at,
            )
            db.add(observation)
        else:
            if contact_type is not None:
                observation.contact_type = contact_type
            if route_type is not None:
                observation.route_type = route_type
            if zero_hop is not None:
                observation.zero_hop = int(zero_hop)
            if latitude is not None and longitude is not None:
                observation.latitude = latitude
                observation.longitude = longitude
            if rssi is not None:
                observation.rssi = rssi
            if snr is not None:
                observation.snr = snr
            observation.first_seen_at = _min_datetime(observation.first_seen_at, first_seen)
            observation.last_seen_at = _max_datetime(observation.last_seen_at, last_seen) or last_seen
            if advert_count is not None:
                if observation.advert_count is None:
                    observation.advert_count = advert_count
                else:
                    observation.advert_count = max(observation.advert_count, advert_count)
            observation.last_event_timestamp = (
                _max_datetime(observation.last_event_timestamp, message.timestamp) or message.timestamp
            )
            observation.last_ingested_at = ingested_at
        sample = db.scalar(
            select(TopologyObservationSample).where(
                TopologyObservationSample.observer_repeater_id == repeater.id,
                TopologyObservationSample.observed_node_id == topology_node.id,
                TopologyObservationSample.observed_at == last_seen,
            )
        )
        if sample is None:
            db.add(
                TopologyObservationSample(
                    observer_repeater_id=repeater.id,
                    observed_node_id=topology_node.id,
                    observed_at=last_seen,
                    route_type=route_type,
                    zero_hop=int(zero_hop) if zero_hop is not None else None,
                    contact_type=contact_type,
                    rssi=rssi,
                    snr=snr,
                )
            )
        else:
            sample.route_type = route_type
            sample.zero_hop = int(zero_hop) if zero_hop is not None else None
            sample.contact_type = contact_type
            sample.rssi = rssi
            sample.snr = snr

        self._refresh_topology_rollup_hourly(
            db,
            observer_repeater_id=repeater.id,
            reference_time=last_seen,
        )

    def _refresh_topology_rollup_hourly(
        self,
        db: Session,
        *,
        observer_repeater_id: str,
        reference_time: datetime,
    ) -> None:
        bucket_start = reference_time.replace(minute=0, second=0, microsecond=0)
        bucket_end = bucket_start + timedelta(hours=1)
        observed_nodes, zero_hop_nodes, avg_rssi, avg_snr = db.execute(
            select(
                func.count(TopologyObservation.id),
                func.coalesce(func.sum(func.coalesce(TopologyObservation.zero_hop, 0)), 0),
                func.avg(TopologyObservation.rssi),
                func.avg(TopologyObservation.snr),
            )
            .where(TopologyObservation.observer_repeater_id == observer_repeater_id)
            .where(TopologyObservation.last_seen_at >= bucket_start)
            .where(TopologyObservation.last_seen_at < bucket_end)
        ).one()

        rollup_row = db.scalar(
            select(TopologyRollupHourly).where(
                TopologyRollupHourly.bucket_start == bucket_start,
                TopologyRollupHourly.observer_repeater_id == observer_repeater_id,
            )
        )
        if rollup_row is None:
            rollup_row = TopologyRollupHourly(
                bucket_start=bucket_start,
                observer_repeater_id=observer_repeater_id,
                observed_nodes=int(observed_nodes or 0),
                zero_hop_nodes=int(zero_hop_nodes or 0),
                avg_rssi=float(avg_rssi) if avg_rssi is not None else None,
                avg_snr=float(avg_snr) if avg_snr is not None else None,
            )
            db.add(rollup_row)
        else:
            rollup_row.observed_nodes = int(observed_nodes or 0)
            rollup_row.zero_hop_nodes = int(zero_hop_nodes or 0)
            rollup_row.avg_rssi = float(avg_rssi) if avg_rssi is not None else None
            rollup_row.avg_snr = float(avg_snr) if avg_snr is not None else None

    def _normalize_message(self, topic: str, payload_bytes: bytes) -> NormalizedMqttMessage | None:
        try:
            raw = json.loads(payload_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("Ignoring non-JSON MQTT payload on topic %s", topic)
            return None
        if not isinstance(raw, dict):
            return None

        contract_msg = self._normalize_contract_message(raw)
        if contract_msg is not None:
            return contract_msg

        return self._normalize_legacy_message(topic, raw)

    def _normalize_contract_message(self, raw: dict[str, Any]) -> NormalizedMqttMessage | None:
        msg_type = raw.get("type")
        if msg_type not in {"packet", "advert", "event"}:
            return None
        if raw.get("version") != 1:
            return None

        try:
            if msg_type == "packet":
                envelope = MqttPacketEnvelopeV1.model_validate(raw)
                event_name = None
            elif msg_type == "advert":
                envelope = MqttAdvertEnvelopeV1.model_validate(raw)
                event_name = None
            else:
                envelope = MqttEventEnvelopeV1.model_validate(raw)
                event_name = envelope.event_name
        except ValidationError:
            return None

        timestamp = _parse_timestamp(envelope.timestamp)
        dedup_key = self._build_dedup_key(
            event_type=msg_type,
            node_name=envelope.node_name,
            event_name=event_name,
            topic=envelope.topic,
            timestamp=timestamp,
            payload=envelope.payload,
        )
        return NormalizedMqttMessage(
            topic=envelope.topic,
            node_name=envelope.node_name,
            timestamp=timestamp,
            event_type=msg_type,
            event_name=event_name,
            payload=dict(envelope.payload),
            dedup_key=dedup_key,
        )

    def _normalize_legacy_message(
        self,
        topic: str,
        raw: dict[str, Any],
    ) -> NormalizedMqttMessage | None:
        parts = [part for part in topic.split("/") if part]
        if len(parts) < 2:
            return None

        event_name: str | None = None
        if len(parts) >= 3 and parts[-2] == "event":
            node_name = parts[-3]
            event_type = "event"
            event_name = parts[-1]
        else:
            node_name = parts[-2]
            suffix = parts[-1]
            if suffix in {"packet", "advert"}:
                event_type = suffix
            elif suffix == "event":
                event_type = "event"
                event_name = _coerce_optional_str(raw.get("event_name")) or "event"
            else:
                event_type = "event"
                event_name = suffix

        if not node_name:
            return None

        payload = dict(raw)
        timestamp = _parse_timestamp(raw.get("timestamp"))
        normalized_topic = _coerce_optional_str(raw.get("topic")) or topic
        dedup_key = self._build_dedup_key(
            event_type=event_type,
            node_name=node_name,
            event_name=event_name,
            topic=normalized_topic,
            timestamp=timestamp,
            payload=payload,
        )
        return NormalizedMqttMessage(
            topic=normalized_topic,
            node_name=node_name,
            timestamp=timestamp,
            event_type=event_type,
            event_name=event_name,
            payload=payload,
            dedup_key=dedup_key,
        )

    @staticmethod
    def _build_dedup_key(
        *,
        event_type: str,
        node_name: str,
        event_name: str | None,
        topic: str,
        timestamp: datetime,
        payload: dict[str, Any],
    ) -> str:
        packet_hash = _coerce_optional_str(payload.get("packet_hash"))
        if event_type == "packet" and packet_hash:
            return f"packet:{node_name}:{packet_hash.lower()}"

        canonical_payload = json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)
        source = "|".join(
            [
                event_type,
                node_name,
                event_name or "",
                topic,
                timestamp.isoformat(),
                canonical_payload,
            ]
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()


class MqttIngestService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        broadcaster: MqttTelemetryBroadcaster | None = None,
    ):
        self._settings = settings
        self._processor = MqttIngestProcessor(session_factory)
        self._broadcaster = broadcaster
        self._queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue(
            maxsize=settings.mqtt_ingest_queue_maxsize
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: mqtt.Client | None = None if mqtt else None
        self._consumer_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if not self._settings.mqtt_ingest_enabled:
            logger.info("MQTT ingest disabled via configuration")
            return
        if mqtt is None:
            logger.warning("MQTT ingest is enabled but paho-mqtt is not installed")
            return

        self._loop = asyncio.get_running_loop()
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop(), name="mqtt-ingest-consumer")

        client = mqtt.Client()
        if self._settings.mqtt_broker_username:
            client.username_pw_set(
                self._settings.mqtt_broker_username,
                self._settings.mqtt_broker_password,
            )
        if self._settings.mqtt_tls_enabled:
            tls_kwargs: dict[str, Any] = {
                "cert_reqs": ssl.CERT_NONE if self._settings.mqtt_tls_insecure else ssl.CERT_REQUIRED,
                "tls_version": ssl.PROTOCOL_TLS_CLIENT,
            }
            if self._settings.mqtt_tls_ca_cert:
                tls_kwargs["ca_certs"] = self._require_file_path(
                    self._settings.mqtt_tls_ca_cert,
                    "mqtt_tls_ca_cert",
                )
            if self._settings.mqtt_tls_client_cert:
                tls_kwargs["certfile"] = self._require_file_path(
                    self._settings.mqtt_tls_client_cert,
                    "mqtt_tls_client_cert",
                )
            if self._settings.mqtt_tls_client_key:
                tls_kwargs["keyfile"] = self._require_file_path(
                    self._settings.mqtt_tls_client_key,
                    "mqtt_tls_client_key",
                )
            if bool(tls_kwargs.get("certfile")) != bool(tls_kwargs.get("keyfile")):
                raise RuntimeError(
                    "mqtt_tls_client_cert and mqtt_tls_client_key must both be configured when using client certificates"
                )
            client.tls_set(**tls_kwargs)
            if self._settings.mqtt_tls_insecure:
                client.tls_insecure_set(True)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.connect_async(self._settings.mqtt_broker_host, self._settings.mqtt_broker_port, 60)
        client.loop_start()
        self._client = client
        logger.info(
            "MQTT ingest subscriber started (%s:%s, base_topic=%s)",
            self._settings.mqtt_broker_host,
            self._settings.mqtt_broker_port,
            self._settings.mqtt_base_topic,
        )

    async def stop(self) -> None:
        if not self._running and self._consumer_task is None and self._client is None:
            return

        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._enqueue_stop_signal)
        else:
            self._enqueue_stop_signal()

        client = self._client
        self._client = None
        if client is not None:
            client.loop_stop()
            client.disconnect()

        if self._consumer_task is not None:
            await self._consumer_task
            self._consumer_task = None

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties=None) -> None:
        rc = getattr(reason_code, "value", reason_code)
        if rc != 0:
            logger.warning("MQTT ingest connect failed with code %s", rc)
            return

        subscription = f"{self._settings.mqtt_base_topic}/+/#"
        client.subscribe(subscription)
        logger.info("MQTT ingest subscribed to %s", subscription)

    def _on_message(self, _client, _userdata, msg) -> None:
        if not self._running or self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue_message, msg.topic, bytes(msg.payload))
        except RuntimeError:
            return

    def _enqueue_message(self, topic: str, payload: bytes) -> None:
        if not self._running:
            return
        try:
            self._queue.put_nowait((topic, payload))
        except asyncio.QueueFull:
            logger.warning("MQTT ingest queue is full; dropping message from topic %s", topic)

    def _enqueue_stop_signal(self) -> None:
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

    async def _consume_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                break

            topic, payload = item
            try:
                result = self._processor.process_message_with_event(topic, payload)
                if result.status in {"unknown_repeater", "invalid"}:
                    logger.debug("MQTT ingest skipped message (%s) from %s", result.status, topic)
                if result.status == "ingested" and result.telemetry_event and self._broadcaster:
                    self._broadcaster.publish(result.telemetry_event)
            except Exception:
                logger.exception("MQTT ingest failed while processing topic %s", topic)
            finally:
                self._queue.task_done()

    @staticmethod
    def _require_file_path(path_value: str, field_name: str) -> str:
        normalized = str(path_value).strip()
        if not normalized:
            raise RuntimeError(f"{field_name} cannot be empty when MQTT TLS is enabled")
        if not Path(normalized).exists():
            raise RuntimeError(f"Configured {field_name} does not exist: {normalized}")
        return normalized
