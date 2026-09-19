from app.config import get_settings
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.models import Alert, InformSnapshot, Packet, Repeater
from app.db.session import get_session_factory
from cryptography import x509
from sqlalchemy import select


def _bootstrap_admin(client) -> dict:
    status = client.get("/api/bootstrap/status")
    assert status.status_code == 200
    assert status.json()["needs_bootstrap"] is True

    created = client.post(
        "/api/bootstrap/admin",
        json={
            "email": "admin@example.com",
            "password": "verysecurepassword123",
            "display_name": "Admin",
        },
    )
    assert created.status_code == 200
    return created.json()


def _login(client) -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "verysecurepassword123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _seed_packets(*, node_one: str, node_two: str, now: datetime | None = None) -> None:
    timestamp_now = now or datetime.now(UTC)
    session = get_session_factory()()
    try:
        repeaters = session.execute(
            select(Repeater).where(Repeater.node_name.in_([node_one, node_two]))
        ).scalars()
        repeater_map = {item.node_name: item for item in repeaters}
        first = repeater_map[node_one]
        second = repeater_map[node_two]

        session.add_all(
            [
                Packet(
                    repeater_id=first.id,
                    timestamp=timestamp_now - timedelta(hours=1),
                    packet_type="announce",
                    route="broadcast",
                    rssi=-99.5,
                    snr=7.5,
                    src_hash="src001",
                    dst_hash="dst001",
                    payload="alpha",
                    packet_hash="hash-alpha",
                ),
                Packet(
                    repeater_id=first.id,
                    timestamp=timestamp_now - timedelta(hours=2),
                    packet_type="telemetry",
                    route="mesh",
                    rssi=-103.2,
                    snr=5.1,
                    src_hash="src002",
                    dst_hash="dst002",
                    payload="beta",
                    packet_hash="hash-beta",
                ),
                Packet(
                    repeater_id=second.id,
                    timestamp=timestamp_now - timedelta(minutes=30),
                    packet_type=None,
                    route=None,
                    rssi=-90.0,
                    snr=9.0,
                    src_hash="src001",
                    dst_hash="dst003",
                    payload="gamma",
                    packet_hash="hash-gamma",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()


def _seed_alerts(*, node_name: str, now: datetime | None = None) -> tuple[str, str]:
    timestamp_now = now or datetime.now(UTC)
    session = get_session_factory()()
    try:
        repeater = session.scalar(select(Repeater).where(Repeater.node_name == node_name))
        assert repeater is not None

        active_alert = Alert(
            repeater_id=repeater.id,
            timestamp=timestamp_now - timedelta(minutes=15),
            alert_type="repeater_offline",
            severity="critical",
            message="Repeater has missed inform windows",
            state="active",
            first_seen_at=timestamp_now - timedelta(minutes=15),
            last_seen_at=timestamp_now - timedelta(minutes=2),
            fingerprint=f"{repeater.id}:offline",
        )
        resolved_alert = Alert(
            repeater_id=repeater.id,
            timestamp=timestamp_now - timedelta(hours=2),
            alert_type="high_noise_floor",
            severity="warning",
            message="Noise floor exceeded threshold",
            state="resolved",
            first_seen_at=timestamp_now - timedelta(hours=2),
            last_seen_at=timestamp_now - timedelta(hours=1, minutes=30),
            resolved_at=timestamp_now - timedelta(hours=1, minutes=30),
            fingerprint=f"{repeater.id}:noise",
        )
        session.add_all([active_alert, resolved_alert])
        session.commit()
        return active_alert.id, resolved_alert.id
    finally:
        session.close()


def test_bootstrap_login_and_me(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"
    assert me.json()["role"] == "admin"


def test_repeater_registry_and_audit(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-01",
            "pubkey": "0x" + "A1" * 32,
            "status": "pending_adoption",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created.status_code == 201
    repeater_id = created.json()["id"]

    listed = client.get("/api/repeaters", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"status": "connected", "location": "51.5074,-0.1278"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "connected"
    assert updated.json()["location"] == "51.5074,-0.1278"

    detail = client.get(f"/api/repeaters/{repeater_id}/detail", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == repeater_id
    assert detail.json()["snapshots"] == []
    assert any(
        entry["source"] == "inform_health_check"
        for entry in detail.json().get("cert_diagnostics", [])
    )

    deleted = client.delete(f"/api/repeaters/{repeater_id}", headers=headers)
    assert deleted.status_code == 204

    listed_after_delete = client.get("/api/repeaters", headers=headers)
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json() == []

    audit = client.get("/api/audit?limit=20", headers=headers)
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert "repeater_created" in actions
    assert "repeater_updated" in actions
    assert "repeater_deleted" in actions


def test_delete_stale_repeaters_endpoint(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    active = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-active",
            "pubkey": "0x" + "A2" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    stale = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-stale",
            "pubkey": "0x" + "B3" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert active.status_code == 201
    assert stale.status_code == 201

    stale_id = stale.json()["id"]
    stale_ts = (datetime.now(UTC) - timedelta(days=8)).isoformat().replace("+00:00", "Z")
    stale_update = client.patch(
        f"/api/repeaters/{stale_id}",
        json={"last_inform_at": stale_ts},
        headers=headers,
    )
    assert stale_update.status_code == 200

    removed = client.delete("/api/repeaters/stale?inactive_hours=168", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["removed"] == 1

    listed = client.get("/api/repeaters", headers=headers)
    assert listed.status_code == 200
    node_names = {item["node_name"] for item in listed.json()}
    assert node_names == {"mesh-repeater-active"}


def test_db_smoke_endpoint(client) -> None:
    _bootstrap_admin(client)
    response = client.get("/api/smoke/db")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_user_management_admin_only_rbac(client) -> None:
    _bootstrap_admin(client)
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    created = client.post(
        "/api/users",
        json={
            "email": "operator@example.com",
            "password": "verysecurepassword123",
            "role": "operator",
            "display_name": "Ops One",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    created_user = created.json()
    assert created_user["role"] == "operator"
    assert created_user["is_active"] is True
    operator_user_id = created_user["id"]

    listed = client.get("/api/users", headers=admin_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    patch_role = client.patch(
        f"/api/users/{operator_user_id}",
        json={"role": "viewer", "is_active": False},
        headers=admin_headers,
    )
    assert patch_role.status_code == 200
    assert patch_role.json()["role"] == "viewer"
    assert patch_role.json()["is_active"] is False

    disabled_login = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "verysecurepassword123"},
    )
    assert disabled_login.status_code == 401

    reenable = client.patch(
        f"/api/users/{operator_user_id}",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert reenable.status_code == 200
    assert reenable.json()["is_active"] is True

    operator_login = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "verysecurepassword123"},
    )
    assert operator_login.status_code == 200
    operator_token = operator_login.json()["access_token"]
    operator_headers = {"Authorization": f"Bearer {operator_token}"}

    denied = client.get("/api/users", headers=operator_headers)
    assert denied.status_code == 403


def test_user_management_cannot_disable_self(client) -> None:
    _bootstrap_admin(client)
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    me = client.get("/api/auth/me", headers=admin_headers)
    assert me.status_code == 200
    admin_id = me.json()["id"]

    disable_self = client.patch(
        f"/api/users/{admin_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert disable_self.status_code == 400


def test_managed_mqtt_settings_update_and_queue_to_repeaters(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    connected = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-connected",
            "pubkey": "0x" + "C1" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    offline = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-offline",
            "pubkey": "0x" + "C2" * 32,
            "status": "offline",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    pending = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-pending",
            "pubkey": "0x" + "C3" * 32,
            "status": "pending_adoption",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert connected.status_code == 201
    assert offline.status_code == 201
    assert pending.status_code == 201

    update = client.put(
        "/api/system-settings/mqtt-managed",
        json={
            "mqtt_enabled": True,
            "mqtt_broker_host": "mqtt.internal.example",
            "mqtt_broker_port": 2883,
            "mqtt_base_topic": "glass-prod",
            "mqtt_tls_enabled": True,
            "queue_to_repeaters": True,
            "reason": "fix broker host",
        },
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["queued_commands"] == 2
    assert update.json()["settings"]["mqtt_broker_host"] == "mqtt.internal.example"
    assert update.json()["settings"]["mqtt_base_topic"] == "glass-prod"

    loaded = client.get("/api/system-settings/mqtt-managed", headers=headers)
    assert loaded.status_code == 200
    assert loaded.json()["mqtt_broker_host"] == "mqtt.internal.example"
    assert loaded.json()["mqtt_broker_port"] == 2883
    assert loaded.json()["mqtt_tls_enabled"] is True
    assert loaded.json()["source"] == "override"

    settings = get_settings()
    broker_cert_path = Path(settings.pki_state_dir) / "mqtt-broker.crt.pem"
    cert = x509.load_pem_x509_certificate(broker_cert_path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    dns_names = set(san.get_values_for_type(x509.DNSName))
    assert "mqtt.internal.example" in dns_names

    commands = client.get("/api/commands?limit=20", headers=headers)
    assert commands.status_code == 200
    managed_commands = [
        item
        for item in commands.json()
        if item["action"] == "config_update"
        and item["params"].get("config", {}).get("glass_managed", {}).get("mqtt_broker_host")
        == "mqtt.internal.example"
    ]
    assert len(managed_commands) == 2


def test_packets_list_supports_filters(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_one = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-packets-01",
            "pubkey": "0x" + "D1" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    created_two = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-packets-02",
            "pubkey": "0x" + "D2" * 32,
            "status": "adopted",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created_one.status_code == 201
    assert created_two.status_code == 201

    _seed_packets(node_one="mesh-repeater-packets-01", node_two="mesh-repeater-packets-02")

    listed = client.get("/api/packets?limit=20&hours=24", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 3
    assert {row["node_name"] for row in listed.json()} == {
        "mesh-repeater-packets-01",
        "mesh-repeater-packets-02",
    }

    by_node = client.get("/api/packets?node_name=mesh-repeater-packets-01", headers=headers)
    assert by_node.status_code == 200
    assert len(by_node.json()) == 2
    assert all(row["node_name"] == "mesh-repeater-packets-01" for row in by_node.json())

    by_type = client.get("/api/packets?packet_type=announce", headers=headers)
    assert by_type.status_code == 200
    assert len(by_type.json()) == 1
    assert by_type.json()[0]["packet_type"] == "announce"


def test_packets_summary_returns_global_aggregates(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_one = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-summary-01",
            "pubkey": "0x" + "E1" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    created_two = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-summary-02",
            "pubkey": "0x" + "E2" * 32,
            "status": "adopted",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created_one.status_code == 201
    assert created_two.status_code == 201

    _seed_packets(node_one="mesh-repeater-summary-01", node_two="mesh-repeater-summary-02")

    summary = client.get("/api/packets/summary?hours=24", headers=headers)
    assert summary.status_code == 200
    payload = summary.json()

    assert payload["hours"] == 24
    assert payload["total_packets"] == 3
    assert payload["unique_repeaters"] == 2
    assert payload["unique_sources"] == 2
    assert payload["unique_destinations"] == 3
    assert payload["avg_rssi"] is not None
    assert payload["avg_snr"] is not None
    assert payload["by_packet_type"]["announce"] == 1
    assert payload["by_packet_type"]["telemetry"] == 1
    assert payload["by_packet_type"]["unknown"] == 1
    assert payload["by_route"]["broadcast"] == 1
    assert payload["by_route"]["mesh"] == 1
    assert payload["by_route"]["unknown"] == 1
    assert payload["packets_per_repeater"]["mesh-repeater-summary-01"] == 2
    assert payload["packets_per_repeater"]["mesh-repeater-summary-02"] == 1


def test_alerts_list_summary_and_lifecycle(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    repeater = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-alerts-01",
            "pubkey": "0x" + "F1" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert repeater.status_code == 201

    active_alert_id, resolved_alert_id = _seed_alerts(node_name="mesh-repeater-alerts-01")

    listed = client.get("/api/alerts?limit=20", headers=headers)
    assert listed.status_code == 200
    listed_ids = {item["id"] for item in listed.json()}
    assert active_alert_id in listed_ids
    assert resolved_alert_id in listed_ids

    summary = client.get("/api/alerts/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["total"] >= 2
    assert summary.json()["active"] >= 1
    assert summary.json()["resolved"] >= 1

    acknowledged = client.post(
        f"/api/alerts/{active_alert_id}/ack",
        json={"note": "operator acknowledged"},
        headers=headers,
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["state"] == "acknowledged"
    assert acknowledged.json()["acked_by"] == "admin@example.com"
    assert acknowledged.json()["note"] == "operator acknowledged"

    resolved = client.post(
        f"/api/alerts/{active_alert_id}/resolve",
        json={"note": "issue cleared"},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    assert resolved.json()["note"] == "issue cleared"

    suppressed = client.post(
        f"/api/alerts/{active_alert_id}/suppress",
        json={"note": "silenced for maintenance"},
        headers=headers,
    )
    assert suppressed.status_code == 200
    assert suppressed.json()["state"] == "suppressed"
    assert suppressed.json()["note"] == "silenced for maintenance"

    detail = client.get(f"/api/alerts/{active_alert_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["notifications"]) >= 3


def test_alerts_viewer_is_read_only(client) -> None:
    _bootstrap_admin(client)
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_viewer = client.post(
        "/api/users",
        json={
            "email": "viewer@example.com",
            "password": "verysecurepassword123",
            "role": "viewer",
            "display_name": "Viewer",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_viewer.status_code == 201

    repeater = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-alerts-rbac",
            "pubkey": "0x" + "F2" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=admin_headers,
    )
    assert repeater.status_code == 201
    active_alert_id, _ = _seed_alerts(node_name="mesh-repeater-alerts-rbac")

    viewer_login = client.post(
        "/api/auth/login",
        json={"email": "viewer@example.com", "password": "verysecurepassword123"},
    )
    assert viewer_login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}

    listed = client.get("/api/alerts", headers=viewer_headers)
    assert listed.status_code == 200

    denied = client.post(
        f"/api/alerts/{active_alert_id}/ack",
        json={"note": "viewer should not mutate"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403


def test_node_group_policy_templates_and_effective_resolution(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_one = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-policy-01",
            "pubkey": "0x" + "91" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    created_two = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-policy-02",
            "pubkey": "0x" + "92" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created_one.status_code == 201
    assert created_two.status_code == 201
    repeater_one_id = created_one.json()["id"]
    repeater_two_id = created_two.json()["id"]

    group = client.post(
        "/api/node-groups",
        json={"name": "Urban Core", "description": "Downtown nodes"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    group_member = client.post(
        f"/api/node-groups/{group_id}/members",
        json={"repeater_id": repeater_one_id},
        headers=headers,
    )
    assert group_member.status_code == 200
    assert len(group_member.json()["members"]) == 1

    offline_global = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Offline Global",
            "rule_type": "offline_repeater",
            "severity": "critical",
            "offline_grace_seconds": 180,
            "auto_resolve": True,
            "enabled": True,
            "config": {},
        },
        headers=headers,
    )
    offline_node = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Offline Node Override",
            "rule_type": "offline_repeater",
            "severity": "warning",
            "offline_grace_seconds": 420,
            "auto_resolve": True,
            "enabled": True,
            "config": {},
        },
        headers=headers,
    )
    noise_group = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Noise Group Policy",
            "rule_type": "high_noise_floor",
            "severity": "warning",
            "threshold_value": -96.0,
            "window_minutes": 12,
            "auto_resolve": True,
            "enabled": True,
            "config": {},
        },
        headers=headers,
    )
    assert offline_global.status_code == 201
    assert offline_node.status_code == 201
    assert noise_group.status_code == 201

    global_assignment = client.post(
        "/api/alert-policies/assignments",
        json={
            "template_id": offline_global.json()["id"],
            "scope_type": "global",
            "priority": 100,
            "enabled": True,
        },
        headers=headers,
    )
    node_assignment = client.post(
        "/api/alert-policies/assignments",
        json={
            "template_id": offline_node.json()["id"],
            "scope_type": "node",
            "scope_id": repeater_one_id,
            "priority": 220,
            "enabled": True,
        },
        headers=headers,
    )
    noise_assignment = client.post(
        "/api/alert-policies/assignments",
        json={
            "template_id": noise_group.json()["id"],
            "scope_type": "group",
            "scope_id": group_id,
            "priority": 190,
            "enabled": True,
        },
        headers=headers,
    )
    assert global_assignment.status_code == 201
    assert node_assignment.status_code == 201
    assert noise_assignment.status_code == 201

    effective_one = client.get(f"/api/alert-policies/effective/{repeater_one_id}", headers=headers)
    assert effective_one.status_code == 200
    one_map = {item["rule_type"]: item for item in effective_one.json()["policies"]}
    assert one_map["offline_repeater"]["template_name"] == "Offline Node Override"
    assert one_map["offline_repeater"]["source_scope_type"] == "node"
    assert one_map["high_noise_floor"]["template_name"] == "Noise Group Policy"
    assert one_map["high_noise_floor"]["source_scope_type"] == "group"

    effective_two = client.get(f"/api/alert-policies/effective/{repeater_two_id}", headers=headers)
    assert effective_two.status_code == 200
    two_map = {item["rule_type"]: item for item in effective_two.json()["policies"]}
    assert two_map["offline_repeater"]["template_name"] == "Offline Global"
    assert two_map["offline_repeater"]["source_scope_type"] == "global"
    assert "high_noise_floor" not in two_map


def test_alert_policy_evaluation_creates_and_resolves_alerts(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-eval-01",
            "pubkey": "0x" + "93" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created.status_code == 201
    repeater_id = created.json()["id"]

    bootstrap_defaults = client.post("/api/alert-policies/bootstrap-defaults", headers=headers)
    assert bootstrap_defaults.status_code == 200

    stale_ts = (datetime.now(UTC) - timedelta(minutes=8)).isoformat().replace("+00:00", "Z")
    stale_update = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"last_inform_at": stale_ts, "status": "offline"},
        headers=headers,
    )
    assert stale_update.status_code == 200

    evaluate_offline = client.post(
        "/api/alert-policies/evaluate",
        json={"repeater_id": repeater_id},
        headers=headers,
    )
    assert evaluate_offline.status_code == 200
    assert evaluate_offline.json()["alerts_activated"] >= 1

    listed_alerts = client.get(
        f"/api/alerts?repeater_id={repeater_id}&alert_type=repeater_offline",
        headers=headers,
    )
    assert listed_alerts.status_code == 200
    assert listed_alerts.json()
    offline_alert = listed_alerts.json()[0]
    assert offline_alert["state"] in {"active", "acknowledged", "suppressed"}

    now_ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    recover_update = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"last_inform_at": now_ts, "status": "connected"},
        headers=headers,
    )
    assert recover_update.status_code == 200

    evaluate_resolve = client.post(
        "/api/alert-policies/evaluate",
        json={"repeater_id": repeater_id},
        headers=headers,
    )
    assert evaluate_resolve.status_code == 200
    assert evaluate_resolve.json()["alerts_resolved"] >= 1

    listed_after = client.get(
        f"/api/alerts?repeater_id={repeater_id}&alert_type=repeater_offline",
        headers=headers,
    )
    assert listed_after.status_code == 200
    assert listed_after.json()[0]["state"] == "resolved"

    session = get_session_factory()()
    try:
        session.add_all(
            [
                InformSnapshot(
                    repeater_id=repeater_id,
                    timestamp=datetime.now(UTC) - timedelta(minutes=4),
                    noise_floor=-90.0,
                ),
                InformSnapshot(
                    repeater_id=repeater_id,
                    timestamp=datetime.now(UTC) - timedelta(minutes=2),
                    noise_floor=-89.5,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    evaluate_noise = client.post(
        "/api/alert-policies/evaluate",
        json={"repeater_id": repeater_id},
        headers=headers,
    )
    assert evaluate_noise.status_code == 200
    noise_alerts = client.get(
        f"/api/alerts?repeater_id={repeater_id}&alert_type=high_noise_floor",
        headers=headers,
    )
    assert noise_alerts.status_code == 200
    assert noise_alerts.json()
    assert noise_alerts.json()[0]["state"] in {"active", "acknowledged", "suppressed"}


def test_alert_policy_tls_telemetry_stale_creates_and_resolves_alert(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-tls-stale-01",
            "pubkey": "0x" + "94" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created.status_code == 201
    repeater_id = created.json()["id"]

    bootstrap_defaults = client.post("/api/alert-policies/bootstrap-defaults", headers=headers)
    assert bootstrap_defaults.status_code == 200

    session = get_session_factory()()
    try:
        repeater = session.scalar(select(Repeater).where(Repeater.id == repeater_id))
        assert repeater is not None
        repeater.settings_json = json.dumps(
            {"glass_managed": {"mqtt_enabled": True, "mqtt_tls_enabled": True}},
            separators=(",", ":"),
            sort_keys=True,
        )
        session.commit()
    finally:
        session.close()

    stale_ts = (datetime.now(UTC) - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    stale_update = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"last_inform_at": stale_ts, "status": "connected"},
        headers=headers,
    )
    assert stale_update.status_code == 200

    evaluate_stale = client.post(
        "/api/alert-policies/evaluate",
        json={"repeater_id": repeater_id},
        headers=headers,
    )
    assert evaluate_stale.status_code == 200

    tls_alerts = client.get(
        f"/api/alerts?repeater_id={repeater_id}&alert_type=mqtt_tls_health",
        headers=headers,
    )
    assert tls_alerts.status_code == 200
    assert tls_alerts.json()
    assert tls_alerts.json()[0]["state"] in {"active", "acknowledged", "suppressed"}

    fresh_ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    fresh_update = client.patch(
        f"/api/repeaters/{repeater_id}",
        json={"last_inform_at": fresh_ts, "status": "connected"},
        headers=headers,
    )
    assert fresh_update.status_code == 200

    evaluate_recover = client.post(
        "/api/alert-policies/evaluate",
        json={"repeater_id": repeater_id},
        headers=headers,
    )
    assert evaluate_recover.status_code == 200

    tls_alerts_after = client.get(
        f"/api/alerts?repeater_id={repeater_id}&alert_type=mqtt_tls_health",
        headers=headers,
    )
    assert tls_alerts_after.status_code == 200
    assert tls_alerts_after.json()
    assert tls_alerts_after.json()[0]["state"] == "resolved"


def test_alert_policy_viewer_is_read_only(client) -> None:
    _bootstrap_admin(client)
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_viewer = client.post(
        "/api/users",
        json={
            "email": "viewer-policies@example.com",
            "password": "verysecurepassword123",
            "role": "viewer",
            "display_name": "Viewer Policies",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_viewer.status_code == 201

    viewer_login = client.post(
        "/api/auth/login",
        json={"email": "viewer-policies@example.com", "password": "verysecurepassword123"},
    )
    assert viewer_login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}

    list_groups = client.get("/api/node-groups", headers=viewer_headers)
    assert list_groups.status_code == 200
    list_templates = client.get("/api/alert-policies/templates", headers=viewer_headers)
    assert list_templates.status_code == 200

    denied_group_create = client.post(
        "/api/node-groups",
        json={"name": "Denied Group"},
        headers=viewer_headers,
    )
    assert denied_group_create.status_code == 403
    denied_template_create = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Denied Template",
            "rule_type": "offline_repeater",
            "severity": "critical",
        },
        headers=viewer_headers,
    )
    assert denied_template_create.status_code == 403
