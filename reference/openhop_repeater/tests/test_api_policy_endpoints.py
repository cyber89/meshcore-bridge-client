from types import SimpleNamespace

import cherrypy
import yaml

from repeater.web.api_endpoints import APIEndpoints


def _make_api(config=None, config_path="/tmp/config.yaml", daemon=None):
    api = APIEndpoints.__new__(APIEndpoints)
    api.config = config or {}
    api.daemon_instance = daemon
    api.send_advert_func = None
    api.event_loop = None
    api.stats_getter = None
    api._config_path = config_path
    api.config_manager = None
    return api


def _set_request(monkeypatch, method="GET", payload=None):
    request = SimpleNamespace(method=method, params={}, json=payload or {})
    response = SimpleNamespace(headers={}, status=200)
    monkeypatch.setattr(cherrypy, "request", request, raising=False)
    monkeypatch.setattr(cherrypy, "response", response, raising=False)
    return request, response


def test_policy_get_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    _set_request(monkeypatch, method="GET")
    result = api.policy()

    assert result["success"] is True
    assert result["data"]["exists"] is False
    assert result["data"]["policy_engine"]["enabled"] is False
    assert result["data"]["policy_file"].endswith("policy.yaml")


def test_policy_post_saves_file_and_applies_runtime(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")

    repeater_handler = SimpleNamespace(policy_engine=None)
    daemon = SimpleNamespace(repeater_handler=repeater_handler)
    api = _make_api(config={}, config_path=str(cfg_path), daemon=daemon)

    payload = {
        "policy_engine": {
            "enabled": True,
            "default_action": "allow",
            "rules": [
                {
                    "id": 10,
                    "enabled": True,
                    "if": {
                        "all": [
                            {
                                "field": "hop_count",
                                "op": "greater_than",
                                "value": 4,
                            }
                        ]
                    },
                    "then": {"action": "drop"},
                }
            ],
        }
    }
    _set_request(monkeypatch, method="POST", payload=payload)

    result = api.policy()

    assert result["success"] is True
    assert result["restart_required"] is False
    assert result["data"]["policy_engine"]["enabled"] is True

    policy_path = tmp_path / "policy.yaml"
    assert policy_path.exists()

    loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert loaded["policy_engine"]["enabled"] is True
    assert len(loaded["policy_engine"]["rules"]) == 1

    assert api.config["policy_engine"]["enabled"] is True
    assert repeater_handler.policy_engine is not None


def test_policy_validate_returns_normalized_payload(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    payload = {
        "enabled": 1,
        "default_action": "allow",
        "rules": [{"id": 1, "enabled": True, "if": {"all": []}, "then": {"action": "drop"}}],
    }
    _set_request(monkeypatch, method="POST", payload=payload)

    result = api.policy_validate()

    assert result["success"] is True
    assert result["data"]["valid"] is True
    assert result["data"]["normalized"]["enabled"] is True
    assert result["data"]["effective"]["rule_count"] == 1


def test_policy_groups_create_and_add_channel_hash_entries(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "channel_hashes",
            "group_id": "ops_channels",
            "friendly_name": "Ops Channels",
            "description": "Operational channel hash group",
        },
    )
    group_create = api.policy_groups()
    assert group_create["success"] is True
    assert group_create["data"]["group"]["friendly_name"] == "Ops Channels"

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "channel_hashes",
            "group_id": "ops_channels",
            "value": "0x9CD8FCF22A47333B591D96A2B848B73F",
            "friendly_name": "Ops Primary",
        },
    )
    entry_create = api.policy_group_entries()
    assert entry_create["success"] is True
    assert entry_create["data"]["entry"]["value"] == "0x9CD8FCF22A47333B591D96A2B848B73F"
    assert entry_create["data"]["entry"]["friendly_name"] == "Ops Primary"

    policy_path = tmp_path / "policy.yaml"
    loaded = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    groups = loaded["groups"]
    assert groups["channel_hashes"][0]["id"] == "ops_channels"
    assert (
        groups["channel_hashes"][0]["entries"][0]["value"] == "0x9CD8FCF22A47333B591D96A2B848B73F"
    )

    projected = loaded["policy_engine"]["objects"]["channel_hash_groups"]
    assert projected["ops_channels"] == ["0x9CD8FCF22A47333B591D96A2B848B73F"]


def test_policy_groups_delete_accepts_query_params(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "channel_hashes",
            "group_id": "ops_channels",
            "friendly_name": "Ops Channels",
        },
    )
    assert api.policy_groups()["success"] is True

    request, _ = _set_request(monkeypatch, method="DELETE", payload={})
    request.params = {"kind": "channel_hashes", "group_id": "ops_channels"}

    result = api.policy_groups()

    assert result["success"] is True
    assert result["data"]["group_id"] == "ops_channels"


def test_policy_groups_create_and_add_pubkey_entries(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "pubkeys",
            "group_id": "trusted_relays",
            "friendly_name": "Trusted Relays",
        },
    )
    group_create = api.policy_groups()
    assert group_create["success"] is True

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "pubkeys",
            "group_id": "trusted_relays",
            "value": "aabbccdd",
            "friendly_name": "Relay Alpha",
        },
    )
    entry_create = api.policy_group_entries()
    assert entry_create["success"] is True
    assert entry_create["data"]["entry"]["value"] == "0xaabbccdd"
    assert entry_create["data"]["entry"]["friendly_name"] == "Relay Alpha"

    _set_request(monkeypatch, method="GET")
    policy_get = api.policy()
    assert policy_get["success"] is True
    pubkey_groups = policy_get["data"]["groups"]["pubkeys"]
    assert len(pubkey_groups) == 1
    assert pubkey_groups[0]["friendly_name"] == "Trusted Relays"
    assert pubkey_groups[0]["entries"][0]["friendly_name"] == "Relay Alpha"


def test_policy_post_preserves_existing_groups(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("repeater: {node_name: test}\n", encoding="utf-8")
    api = _make_api(config={}, config_path=str(cfg_path))

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "kind": "channel_hashes",
            "group_id": "group_one",
            "friendly_name": "Group One",
        },
    )
    create_group = api.policy_groups()
    assert create_group["success"] is True

    _set_request(
        monkeypatch,
        method="POST",
        payload={
            "enabled": True,
            "default_action": "allow",
            "rules": [],
        },
    )
    update_policy = api.policy()
    assert update_policy["success"] is True
    assert update_policy["data"]["policy_engine"]["enabled"] is True
    assert len(update_policy["data"]["groups"]["channel_hashes"]) == 1
