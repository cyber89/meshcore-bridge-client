from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from app.db.models import ConfigSnapshot
from app.db.session import get_session_factory


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


def _inform_payload(node_name: str) -> dict:
    return {
        "type": "inform",
        "version": 1,
        "node_name": node_name,
        "pubkey": "0x" + "AB" * 32,
        "software_version": "1.2.3",
        "uptime_seconds": 12345,
        "config_hash": "sha256:" + "c" * 64,
        "system": {
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 30.0,
            "temperature_c": 45.0,
            "load_avg_1m": 0.11,
        },
        "radio": {
            "frequency": 869618000,
            "spreading_factor": 8,
            "bandwidth": 62500,
            "tx_power": 14,
            "noise_floor_dbm": -110.2,
            "mode": "forward",
        },
        "counters": {
            "rx_total": 10,
            "tx_total": 12,
            "forwarded": 9,
            "dropped": 1,
            "duplicates": 2,
            "airtime_percent": 4.5,
        },
        "command_results": [],
    }


def test_inform_persists_location_and_settings_for_detail(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    payload = _inform_payload("mesh-repeater-settings")
    payload["state"] = "forward"
    payload["location"] = "51.5074,-0.1278"
    payload["settings"] = {
        "repeater": {"location": "51.5074,-0.1278", "mode": "forward"},
        "radio": {"frequency": 869618000},
    }

    first_inform = client.post("/inform", json=payload)
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()) == 1
    repeater_id = pending.json()[0]["id"]
    assert pending.json()[0]["location"] == "51.507400,-0.127800"

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["location"] == "51.507400,-0.127800"
    assert detail.json()["settings"]["repeater"]["mode"] == "forward"
    assert detail.json()["state"] == "forward"


def test_inform_extracts_location_from_repeater_latitude_longitude(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    payload = _inform_payload("mesh-repeater-latlon")
    payload["settings"] = {
        "repeater": {
            "latitude": -33.9180,
            "longitude": 18.4233,
        }
    }

    first_inform = client.post("/inform", json=payload)
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()) == 1
    assert pending.json()[0]["node_name"] == "mesh-repeater-latlon"
    assert pending.json()[0]["location"] == "-33.918000,18.423300"


def test_repeater_detail_exposes_uptime_snapshot_history(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-uptime"
    first_payload = _inform_payload(node_name)
    first_payload["uptime_seconds"] = 120
    first_inform = client.post("/inform", json=first_payload)
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    second_payload = _inform_payload(node_name)
    second_payload["uptime_seconds"] = 240
    second_inform = client.post("/inform", json=second_payload)
    assert second_inform.status_code == 200
    assert second_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    repeater_id = pending.json()[0]["id"]

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    snapshots = detail.json()["snapshots"]
    assert len(snapshots) >= 2
    assert snapshots[-2]["uptime_seconds"] == 120
    assert snapshots[-1]["uptime_seconds"] == 240


def test_repeater_detail_handles_naive_last_inform_datetime(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-naive-datetime",
            "pubkey": "0x" + "AC" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created.status_code == 201
    repeater_id = created.json()["id"]

    naive_stale = (datetime.now(UTC) - timedelta(minutes=20)).replace(tzinfo=None).isoformat()
    updated = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"last_inform_at": naive_stale, "status": "connected"},
        headers=headers,
    )
    assert updated.status_code == 200

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == repeater_id
    assert any(
        entry["source"] == "inform_health_check"
        for entry in detail.json().get("cert_diagnostics", [])
    )


def test_inform_to_adoption_and_command_lifecycle(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-42"

    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["type"] == "noop"
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    assert len(pending.json()) == 1
    repeater_id = pending.json()[0]["id"]

    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200
    assert adopt.json()["status"] == "adopted"

    queue = client.post(
        "/api/commands",
        json={
            "node_name": node_name,
            "action": "restart_service",
            "params": {},
            "requested_by": "admin@example.com",
            "reason": "maintenance",
        },
        headers=headers,
    )
    assert queue.status_code == 201
    command_id = queue.json()["command_id"]

    second_inform = client.post("/inform", json=_inform_payload(node_name))
    assert second_inform.status_code == 200
    assert second_inform.json()["type"] == "cert_renewal"
    assert "BEGIN CERTIFICATE" in second_inform.json()["client_cert"]
    assert "BEGIN PRIVATE KEY" in second_inform.json()["client_key"]

    third_inform = client.post("/inform", json=_inform_payload(node_name))
    assert third_inform.status_code == 200
    assert third_inform.json()["type"] == "command"
    assert third_inform.json()["command_id"] == command_id
    assert third_inform.json()["action"] == "restart_service"

    payload = _inform_payload(node_name)
    payload["command_results"] = [
        {
            "command_id": command_id,
            "status": "success",
            "message": "ok",
            "completed_at": "2026-04-15T12:30:45Z",
        }
    ]
    fourth_inform = client.post("/inform", json=payload)
    assert fourth_inform.status_code == 200
    assert fourth_inform.json()["type"] == "command"
    assert fourth_inform.json()["action"] == "config_update"
    system_command_id = fourth_inform.json()["command_id"]

    system_result_payload = _inform_payload(node_name)
    system_result_payload["command_results"] = [
        {
            "command_id": system_command_id,
            "status": "success",
            "message": "managed settings updated",
            "completed_at": "2026-04-15T12:31:00Z",
        }
    ]
    fifth_inform = client.post("/inform", json=system_result_payload)
    assert fifth_inform.status_code == 200
    assert fifth_inform.json()["type"] == "noop"
    assert fifth_inform.json()["status"] == "connected"

    command = client.get(f"/api/commands/{command_id}", headers=headers)
    assert command.status_code == 200
    assert command.json()["status"] == "success"
    assert command.json()["result"]["message"] == "ok"

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    diagnostics = detail.json()["cert_diagnostics"]
    assert len(diagnostics) >= 2
    sources = {entry["source"] for entry in diagnostics}
    assert "certificate_issued" in sources
    assert "command_queue" in sources


def test_inform_renews_when_reported_cert_is_near_expiry(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-renew"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    initial_issue = client.post("/inform", json=_inform_payload(node_name))
    assert initial_issue.status_code == 200
    assert initial_issue.json()["type"] == "cert_renewal"
    first_cert = initial_issue.json()["client_cert"]

    near_expiry_payload = _inform_payload(node_name)
    near_expiry = datetime.now(UTC) + timedelta(days=1)
    near_expiry_payload["cert_expires_at"] = near_expiry.isoformat().replace("+00:00", "Z")

    renewal = client.post("/inform", json=near_expiry_payload)
    assert renewal.status_code == 200
    assert renewal.json()["type"] == "cert_renewal"
    assert renewal.json()["client_cert"] != first_cert


def test_inform_auto_dispatches_glass_managed_mqtt_config(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-managed"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    cert_issue = client.post("/inform", json=_inform_payload(node_name))
    assert cert_issue.status_code == 200
    assert cert_issue.json()["type"] == "cert_renewal"

    config_dispatch = client.post("/inform", json=_inform_payload(node_name))
    assert config_dispatch.status_code == 200
    assert config_dispatch.json()["type"] == "command"
    assert config_dispatch.json()["action"] == "config_update"
    params = config_dispatch.json()["params"]
    assert params["merge_mode"] == "patch"
    assert params["config"]["glass_managed"]["mqtt_enabled"] is True
    assert "mqtt_broker_host" in params["config"]["glass_managed"]


def test_inform_managed_mqtt_dispatch_uses_system_settings_override(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    update = client.put(
        "/api/system-settings/mqtt-managed",
        json={
            "mqtt_enabled": True,
            "mqtt_broker_host": "mqtt.override.example",
            "mqtt_broker_port": 3883,
            "mqtt_base_topic": "glass-override",
            "mqtt_tls_enabled": True,
            "queue_to_repeaters": False,
        },
        headers=headers,
    )
    assert update.status_code == 200

    node_name = "mesh-repeater-override"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    cert_issue = client.post("/inform", json=_inform_payload(node_name))
    assert cert_issue.status_code == 200
    assert cert_issue.json()["type"] == "cert_renewal"

    config_dispatch = client.post("/inform", json=_inform_payload(node_name))
    assert config_dispatch.status_code == 200
    assert config_dispatch.json()["type"] == "command"
    assert config_dispatch.json()["action"] == "config_update"
    managed = config_dispatch.json()["params"]["config"]["glass_managed"]
    assert managed["mqtt_broker_host"] == "mqtt.override.example"
    assert managed["mqtt_broker_port"] == 3883
    assert managed["mqtt_base_topic"] == "glass-override"
    assert managed["mqtt_tls_enabled"] is True


def test_rotate_cert_command_result_forces_cert_renewal(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-rotate-cert"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    initial_cert_issue = client.post("/inform", json=_inform_payload(node_name))
    assert initial_cert_issue.status_code == 200
    assert initial_cert_issue.json()["type"] == "cert_renewal"

    # Drain any queued system commands so rotate_cert can dispatch next.
    for _ in range(6):
        response = client.post("/inform", json=_inform_payload(node_name))
        assert response.status_code == 200
        payload = response.json()
        if payload["type"] == "noop":
            break
        if payload["type"] == "command":
            command_result_payload = _inform_payload(node_name)
            command_result_payload["command_results"] = [
                {
                    "command_id": payload["command_id"],
                    "status": "success",
                    "message": "ok",
                    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            ]
            follow_up = client.post("/inform", json=command_result_payload)
            assert follow_up.status_code == 200
            if follow_up.json()["type"] == "noop":
                break

    rotate_command = client.post(
        "/api/commands",
        json={
            "node_name": node_name,
            "action": "rotate_cert",
            "params": {},
            "requested_by": "admin@example.com",
            "reason": "manual cert renewal from UI",
        },
        headers=headers,
    )
    assert rotate_command.status_code == 201

    rotate_dispatched = False
    for _ in range(6):
        response = client.post("/inform", json=_inform_payload(node_name))
        assert response.status_code == 200
        payload = response.json()
        if payload["type"] != "command":
            continue
        command_result_payload = _inform_payload(node_name)
        command_result_payload["command_results"] = [
            {
                "command_id": payload["command_id"],
                "status": "success",
                "message": "ok",
                "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ]
        follow_up = client.post("/inform", json=command_result_payload)
        assert follow_up.status_code == 200
        if payload["action"] == "rotate_cert":
            rotate_dispatched = True
            assert follow_up.json()["type"] == "cert_renewal"
            assert "BEGIN CERTIFICATE" in follow_up.json()["client_cert"]
            assert "BEGIN PRIVATE KEY" in follow_up.json()["client_key"]
            break

    assert rotate_dispatched is True


def test_config_snapshot_export_ingest_encrypted_and_rotates(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-config-snapshot"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    queued_command_ids: list[str] = []
    for idx in range(3):
        queued = client.post(
            "/api/config-snapshots/export",
            json={"repeater_id": repeater_id, "reason": "scheduled backup"},
            headers=headers,
        )
        assert queued.status_code == 201
        command_id = queued.json()["command_id"]
        queued_command_ids.append(command_id)

        export_payload = _inform_payload(node_name)
        export_payload["command_results"] = [
            {
                "command_id": command_id,
                "status": "success",
                "message": "config exported",
                "completed_at": (
                    datetime.now(UTC) + timedelta(seconds=idx)
                ).isoformat().replace("+00:00", "Z"),
                "details": {
                    "config": {
                        "repeater": {"node_name": node_name},
                        "glass": {"api_token": f"secret-{idx}"},
                    }
                },
            }
        ]
        ingested = client.post("/inform", json=export_payload)
        assert ingested.status_code == 200

    listed = client.get(
        f"/api/config-snapshots?repeater_id={repeater_id}&limit=10",
        headers=headers,
    )
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert len(listed_payload) == 2
    listed_command_ids = [item["command_id"] for item in listed_payload]
    assert queued_command_ids[0] not in listed_command_ids
    assert queued_command_ids[1] in listed_command_ids
    assert queued_command_ids[2] in listed_command_ids

    latest_snapshot = listed_payload[0]
    snapshot_detail = client.get(
        f"/api/config-snapshots/{latest_snapshot['id']}",
        headers=headers,
    )
    assert snapshot_detail.status_code == 200
    assert snapshot_detail.json()["payload"]["glass"]["api_token"] == "secret-2"

    command_lookup = client.get(f"/api/commands/{queued_command_ids[-1]}", headers=headers)
    assert command_lookup.status_code == 200
    command_result = command_lookup.json()["result"] or {}
    assert "details" in command_result
    assert "config" not in command_result["details"]
    assert command_result["details"]["snapshot_id"] == latest_snapshot["id"]

    session = get_session_factory()()
    try:
        stored_snapshot = session.scalar(
            select(ConfigSnapshot).where(ConfigSnapshot.id == latest_snapshot["id"])
        )
        assert stored_snapshot is not None
        assert "secret-2" not in stored_snapshot.ciphertext
    finally:
        session.close()


def test_config_snapshot_request_logs_and_change_control_dedup(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    node_name = "mesh-repeater-config-change-control"
    first_inform = client.post("/inform", json=_inform_payload(node_name))
    assert first_inform.status_code == 200
    assert first_inform.json()["status"] == "pending_adoption"

    pending = client.get("/api/adoption/pending", headers=headers)
    assert pending.status_code == 200
    repeater_id = pending.json()[0]["id"]
    adopt = client.post(
        f"/api/adoption/{repeater_id}/adopt",
        json={"note": "approved"},
        headers=headers,
    )
    assert adopt.status_code == 200

    reason = "change-control backup request"
    first_queue = client.post(
        "/api/config-snapshots/export",
        json={"repeater_id": repeater_id, "reason": reason},
        headers=headers,
    )
    assert first_queue.status_code == 201
    first_command_id = first_queue.json()["command_id"]

    exported_config = {
        "repeater": {"node_name": node_name, "mode": "forward"},
        "glass": {"api_token": "secret-static"},
    }
    first_result_payload = _inform_payload(node_name)
    first_result_payload["command_results"] = [
        {
            "command_id": first_command_id,
            "status": "success",
            "message": "config exported",
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "details": {"config": exported_config},
        }
    ]
    first_ingested = client.post("/inform", json=first_result_payload)
    assert first_ingested.status_code == 200

    second_queue = client.post(
        "/api/config-snapshots/export",
        json={"repeater_id": repeater_id, "reason": reason},
        headers=headers,
    )
    assert second_queue.status_code == 201
    second_command_id = second_queue.json()["command_id"]

    second_result_payload = _inform_payload(node_name)
    second_result_payload["command_results"] = [
        {
            "command_id": second_command_id,
            "status": "success",
            "message": "config exported",
            "completed_at": (datetime.now(UTC) + timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "details": {"config": exported_config},
        }
    ]
    second_ingested = client.post("/inform", json=second_result_payload)
    assert second_ingested.status_code == 200

    listed = client.get(
        f"/api/config-snapshots?repeater_id={repeater_id}&limit=10",
        headers=headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    second_command_lookup = client.get(f"/api/commands/{second_command_id}", headers=headers)
    assert second_command_lookup.status_code == 200
    second_result = second_command_lookup.json().get("result") or {}
    second_details = second_result.get("details") or {}
    assert second_details.get("stored_new_snapshot") is False
    change_control = second_details.get("change_control") or {}
    assert change_control.get("has_changes") is False
    assert change_control.get("is_duplicate_content") is True

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    diagnostics = detail.json().get("cert_diagnostics", [])
    assert any(
        entry.get("source") == "config_snapshot_request"
        and reason in str(entry.get("message", ""))
        for entry in diagnostics
    )
    assert any(
        entry.get("source") == "command_queue"
        and "no config differences" in str(entry.get("message", "")).lower()
        for entry in diagnostics
    )
