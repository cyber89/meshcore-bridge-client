import json

from app.db.models import MqttIngestEvent, Packet
from app.db.session import get_session_factory
from app.services.mqtt_ingest import MqttIngestProcessor
from app.services.telemetry_stream import get_mqtt_telemetry_broadcaster
from sqlalchemy import select


def _bootstrap_admin(client) -> None:
    created = client.post(
        "/api/bootstrap/admin",
        json={
            "email": "admin@example.com",
            "password": "verysecurepassword123",
            "display_name": "Admin",
        },
    )
    assert created.status_code == 200


def _login(client) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "verysecurepassword123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _create_repeater(client, *, node_name: str, pubkey_suffix: str) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    response = client.post(
        "/api/repeaters",
        json={
            "node_name": node_name,
            "pubkey": "0x" + pubkey_suffix * 64,
            "status": "connected",
            "firmware_version": "1.2.3",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


def test_mqtt_packet_ingest_and_dedup(client) -> None:
    node_name = "mesh-repeater-01"
    _create_repeater(client, node_name=node_name, pubkey_suffix="a")

    processor = MqttIngestProcessor(get_session_factory())
    topic = f"glass/{node_name}/packet"
    envelope = {
        "version": 1,
        "type": "packet",
        "topic": topic,
        "node_name": node_name,
        "timestamp": "2026-04-15T12:30:45Z",
        "payload": {
            "type": 2,
            "route": 0,
            "rssi": -81.5,
            "snr": 8.5,
            "src_hash": "AA",
            "dst_hash": "BB",
            "payload": "abcd",
            "packet_hash": "ABCDEF1234567890",
        },
    }

    first = processor.process_message(topic, json.dumps(envelope).encode("utf-8"))
    second = processor.process_message(topic, json.dumps(envelope).encode("utf-8"))

    assert first == "ingested"
    assert second == "duplicate"

    with get_session_factory()() as db:
        events = db.scalars(select(MqttIngestEvent)).all()
        packets = db.scalars(select(Packet)).all()

    assert len(events) == 1
    assert len(packets) == 1
    assert packets[0].packet_hash == "ABCDEF1234567890"


def test_mqtt_legacy_event_ingest_and_unknown_repeater_skip(client) -> None:
    node_name = "mesh-repeater-02"
    _create_repeater(client, node_name=node_name, pubkey_suffix="b")
    processor = MqttIngestProcessor(get_session_factory())

    ingested = processor.process_message(
        f"glass/{node_name}/noise_floor",
        json.dumps({"timestamp": 1760000000, "noise_floor_dbm": -111.2}).encode("utf-8"),
    )
    skipped = processor.process_message(
        "glass/missing-node/noise_floor",
        json.dumps({"timestamp": 1760000001, "noise_floor_dbm": -109.7}).encode("utf-8"),
    )

    assert ingested == "ingested"
    assert skipped == "unknown_repeater"

    with get_session_factory()() as db:
        events = db.scalars(select(MqttIngestEvent).order_by(MqttIngestEvent.timestamp.asc())).all()
        packets = db.scalars(select(Packet)).all()

    assert len(events) == 1
    assert events[0].event_type == "event"
    assert events[0].event_name == "noise_floor"
    assert len(packets) == 0


def test_telemetry_stream_requires_auth(client) -> None:
    response = client.get("/api/telemetry/stream")
    assert response.status_code == 401


def test_telemetry_stream_emits_backlog_event(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    broadcaster = get_mqtt_telemetry_broadcaster()
    broadcaster.reset()
    broadcaster.publish(
        {
            "event_id": "evt-1",
            "repeater_id": "rep-1",
            "node_name": "mesh-repeater-01",
            "timestamp": "2026-04-15T12:30:45Z",
            "event_type": "event",
            "event_name": "noise_floor",
            "topic": "glass/mesh-repeater-01/event/noise_floor",
            "payload": {"noise_floor_dbm": -111.2},
            "ingested_at": "2026-04-15T12:30:46Z",
        }
    )

    response = client.get(f"/api/telemetry/stream?token={token}&max_events=1")
    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line]
    assert "event: ready" in lines
    payload_lines = [line for line in lines if line.startswith("data: ")]
    assert payload_lines
    payloads = [json.loads(line.removeprefix("data: ")) for line in payload_lines]
    assert any(payload.get("event_id") == "evt-1" for payload in payloads)

    broadcaster.reset()
