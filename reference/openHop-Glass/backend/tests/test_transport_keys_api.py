from datetime import UTC, datetime


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


def _inform_payload(node_name: str, pubkey_hex: str) -> dict:
    return {
        "type": "inform",
        "version": 1,
        "node_name": node_name,
        "pubkey": pubkey_hex,
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


def test_transport_key_crud_queues_sync_commands(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_repeater = client.post(
        "/api/repeaters",
        json={
            "node_name": "mesh-repeater-transport-keys",
            "pubkey": "0x" + "AA" * 32,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created_repeater.status_code == 201

    created_group = client.post(
        "/api/transport-keys/groups",
        json={"name": "#Region A", "flood_policy": "allow", "sort_order": 1},
        headers=headers,
    )
    assert created_group.status_code == 201
    group_id = created_group.json()["id"]

    created_key = client.post(
        "/api/transport-keys/keys",
        json={
            "name": "region-a-key-1",
            "group_id": group_id,
            "flood_policy": "deny",
            "transport_key": "manual-test-key",
            "sort_order": 5,
        },
        headers=headers,
    )
    assert created_key.status_code == 201
    assert created_key.json()["group_id"] == group_id

    tree = client.get("/api/transport-keys/tree", headers=headers)
    assert tree.status_code == 200
    payload = tree.json()
    assert any(node["kind"] == "group" and node["id"] == group_id for node in payload["nodes"])
    assert any(
        node["kind"] == "key" and node["name"] == "region-a-key-1" and node["parent_id"] == group_id
        for node in payload["nodes"]
    )

    commands = client.get("/api/commands?limit=20", headers=headers)
    assert commands.status_code == 200
    assert any(item["action"] == "transport_keys_sync" for item in commands.json())


def test_transport_key_sync_status_transitions_with_inform_results(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    node_name = "mesh-repeater-transport-sync"
    pubkey = "0x" + "AB" * 32

    created_repeater = client.post(
        "/api/repeaters",
        json={
            "node_name": node_name,
            "pubkey": pubkey,
            "status": "connected",
            "firmware_version": "1.0.0",
        },
        headers=headers,
    )
    assert created_repeater.status_code == 201
    repeater_id = created_repeater.json()["id"]

    created_group = client.post(
        "/api/transport-keys/groups",
        json={"name": "#Sync Region", "flood_policy": "allow"},
        headers=headers,
    )
    assert created_group.status_code == 201

    dispatched_command: dict | None = None
    for _ in range(10):
        response = client.post("/inform", json=_inform_payload(node_name, pubkey))
        assert response.status_code == 200
        body = response.json()
        if body.get("type") == "command":
            if body.get("action") == "transport_keys_sync":
                dispatched_command = body
                break
            result_payload = _inform_payload(node_name, pubkey)
            result_payload["command_results"] = [
                {
                    "command_id": body["command_id"],
                    "status": "success",
                    "message": "ok",
                    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            ]
            follow_up = client.post("/inform", json=result_payload)
            assert follow_up.status_code == 200

    assert dispatched_command is not None
    assert dispatched_command["action"] == "transport_keys_sync"
    command_id = dispatched_command["command_id"]

    command_result_payload = _inform_payload(node_name, pubkey)
    command_result_payload["command_results"] = [
        {
            "command_id": command_id,
            "status": "success",
            "message": "transport keys synced",
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "details": {"applied_nodes": 2},
        }
    ]
    completed = client.post("/inform", json=command_result_payload)
    assert completed.status_code == 200

    tree = client.get("/api/transport-keys/tree", headers=headers)
    assert tree.status_code == 200
    sync_rows = tree.json()["sync_status"]
    repeater_sync = next(item for item in sync_rows if item["repeater_id"] == repeater_id)
    assert repeater_sync["status"] == "success"
    assert repeater_sync["command_id"] == command_id
    assert repeater_sync["error_message"] is None


def test_transport_key_group_move_prevents_cycles(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    group_a = client.post(
        "/api/transport-keys/groups",
        json={"name": "#Cycle A"},
        headers=headers,
    )
    assert group_a.status_code == 201
    group_a_id = group_a.json()["id"]

    group_b = client.post(
        "/api/transport-keys/groups",
        json={"name": "#Cycle B", "parent_group_id": group_a_id},
        headers=headers,
    )
    assert group_b.status_code == 201
    group_b_id = group_b.json()["id"]

    invalid_move = client.patch(
        f"/api/transport-keys/groups/{group_a_id}",
        json={"parent_group_id": group_b_id},
        headers=headers,
    )
    assert invalid_move.status_code == 422
    assert "cycle" in invalid_move.json()["detail"].lower()

