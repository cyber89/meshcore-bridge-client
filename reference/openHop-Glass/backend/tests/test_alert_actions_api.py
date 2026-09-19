import json
from datetime import UTC, datetime
from urllib import parse as urllib_parse

import pytest
from sqlalchemy import select

from app.db.models import (
    Alert,
    AlertActionIntegration,
    AlertActionTemplate,
    AlertPolicyActionBinding,
    AlertPolicyTemplate,
    NotificationEvent,
    Repeater,
)
from app.db.session import get_session_factory
from app.services.alert_actions import (
    get_notification_provider_registry,
    parse_action_template_default_events,
    parse_binding_event_types,
    parse_integration_settings,
    serialize_action_events,
    validate_action_integration_settings,
)
from app.services.alerts import queue_notification_event
from app.services.notification_providers.base import NotificationSendRequest

def _bootstrap_admin(client) -> None:
    status = client.get("/api/bootstrap/status")
    assert status.status_code == 200
    if status.json()["needs_bootstrap"]:
        created = client.post(
            "/api/bootstrap/admin",
            json={
                "email": "admin@example.com",
                "password": "verysecurepassword123",
                "display_name": "Admin",
            },
        )
        assert created.status_code == 200


def _login(client, *, email: str = "admin@example.com", password: str = "verysecurepassword123") -> str:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_alert_action_models_and_notification_metadata(client) -> None:
    _ = client
    session = get_session_factory()()
    try:
        repeater = Repeater(
            node_name="mesh-actions-01",
            pubkey="0x" + "AB" * 32,
            status="connected",
            firmware_version="1.0.0",
            last_inform_at=datetime.now(UTC),
        )
        session.add(repeater)
        session.flush()

        policy_template = AlertPolicyTemplate(
            name="Action Policy Template",
            rule_type="offline_repeater",
            severity="critical",
            enabled=1,
            offline_grace_seconds=120,
            auto_resolve=1,
            config_json="{}",
        )
        session.add(policy_template)
        session.flush()

        integration = AlertActionIntegration(
            name="Primary Webhook",
            provider_type="webhook",
            enabled=1,
            settings_json=json.dumps(
                {
                    "url": "https://example.com/alerts",
                    "method": "POST",
                    "headers": {"X-Test": "true"},
                    "timeout_seconds": 10,
                    "verify_tls": True,
                    "max_body_bytes": 5000,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            secrets_json=json.dumps({"token": "redacted"}, separators=(",", ":"), sort_keys=True),
        )
        session.add(integration)
        session.flush()

        action_template = AlertActionTemplate(
            name="Default Webhook Payload",
            provider_type="webhook",
            payload_template_json=json.dumps({"message": "{{ alert.message }}"}),
            default_event_types_json=json.dumps(["alert_activated", "alert_resolved"]),
            enabled=1,
        )
        session.add(action_template)
        session.flush()

        binding = AlertPolicyActionBinding(
            policy_template_id=policy_template.id,
            integration_id=integration.id,
            action_template_id=action_template.id,
            event_types_json=json.dumps(["alert_activated"]),
            enabled=1,
            sort_order=50,
            cooldown_seconds=30,
        )
        session.add(binding)
        session.flush()

        alert = Alert(
            repeater_id=repeater.id,
            alert_type="repeater_offline",
            severity="critical",
            message="Test alert for action scaffolding",
            state="active",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            fingerprint=f"{repeater.id}:offline",
        )
        session.add(alert)
        session.flush()

        queue_notification_event(
            session,
            alert_id=alert.id,
            channel="webhook",
            event_type="alert_activated",
            payload={"alert_id": alert.id},
            integration_id=integration.id,
            action_template_id=action_template.id,
            binding_id=binding.id,
            provider_type="webhook",
            idempotency_key=f"{alert.id}:{binding.id}:alert_activated:1",
            rendered_payload={"message": alert.message, "severity": alert.severity},
        )
        session.commit()

        created_event = session.scalar(
            select(NotificationEvent).where(NotificationEvent.integration_id == integration.id)
        )
        assert created_event is not None
        assert created_event.provider_type == "webhook"
        assert created_event.binding_id == binding.id
        assert created_event.idempotency_key is not None
        assert created_event.rendered_payload_json is not None
        assert json.loads(created_event.rendered_payload_json)["severity"] == "critical"

        assert parse_integration_settings(integration)["method"] == "POST"
        assert parse_action_template_default_events(action_template) == [
            "alert_activated",
            "alert_resolved",
        ]
        assert parse_binding_event_types(binding) == ["alert_activated"]
    finally:
        session.close()


def test_provider_registry_webhook_baseline(client, monkeypatch) -> None:
    _ = client
    registry = get_notification_provider_registry()
    provider_types = registry.list_provider_types()
    assert provider_types == ["apprise", "pushover", "webhook"]

    validated = validate_action_integration_settings(
        provider_type="webhook",
        settings={
            "url": "https://example.com/webhook",
            "method": "post",
            "headers": {"X-Env": "test"},
            "timeout_seconds": 5,
            "verify_tls": False,
            "max_body_bytes": 4096,
        },
        registry=registry,
    )
    assert validated["method"] == "POST"
    assert validated["verify_tls"] is False
    validated_apprise = validate_action_integration_settings(
        provider_type="apprise",
        settings={
            "api_url": "https://apprise.example.com/notify",
            "urls": "mailto://alerts@example.com",
            "notify_type": "warning",
            "format": "markdown",
            "timeout_seconds": 12,
            "verify_tls": False,
            "headers": {"X-Source": "pyMC_Glass"},
        },
        registry=registry,
    )
    assert validated_apprise["notify_type"] == "warning"
    assert validated_apprise["format"] == "markdown"
    assert validated_apprise["verify_tls"] is False
    assert validated_apprise["urls"] == ["mailto://alerts@example.com"]

    webhook_provider = registry.get_provider("webhook")
    payload = webhook_provider.build_payload(
        NotificationSendRequest(
            event_type="alert_activated",
            payload={"a": 1},
            rendered_payload={"custom": True},
        )
    )
    assert payload == {"custom": True}
    captured_request: dict[str, str | int] = {}

    class _FakeProviderResponse:
        def __init__(self, *, status_code: int, body: str):
            self._status_code = status_code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def getcode(self) -> int:
            return self._status_code

        def read(self, _max_bytes: int = -1) -> bytes:
            return self._body.encode("utf-8")

    def _fake_urlopen(request_obj, timeout):  # noqa: ANN001
        captured_request["url"] = request_obj.full_url
        captured_request["timeout"] = timeout
        captured_request["body"] = request_obj.data.decode("utf-8")
        return _FakeProviderResponse(status_code=200, body='{"status":1,"request":"req-123"}')

    monkeypatch.setattr(
        "app.services.notification_providers.pushover.urllib_request.urlopen",
        _fake_urlopen,
    )

    pushover_provider = registry.get_provider("pushover")
    pushover_result = pushover_provider.send(
        settings={
            "app_token": "token",
            "user_key": "user",
            "device": "ops-phone",
            "priority": 1,
            "sound": "pushover",
        },
        request=NotificationSendRequest(
            event_type="alert_activated",
            payload={"a": 1},
            rendered_payload={"title": "Alert title", "body": "Alert body"},
        ),
    )
    assert pushover_result.status == "sent"
    assert pushover_result.status_code == 200
    assert pushover_result.provider_message_id == "req-123"
    assert captured_request["url"] == "https://api.pushover.net/1/messages.json"
    assert captured_request["timeout"] == 15
    parsed_body = urllib_parse.parse_qs(str(captured_request["body"]))
    assert parsed_body["token"] == ["token"]
    assert parsed_body["user"] == ["user"]
    assert parsed_body["title"] == ["Alert title"]
    assert parsed_body["message"] == ["[alert_activated] Alert body"]
    assert parsed_body["device"] == ["ops-phone"]
    assert parsed_body["priority"] == ["1"]
    assert parsed_body["sound"] == ["pushover"]
    captured_apprise_request: dict[str, str | int | bool] = {}

    def _fake_apprise_urlopen(request_obj, timeout, context=None):  # noqa: ANN001
        captured_apprise_request["url"] = request_obj.full_url
        captured_apprise_request["timeout"] = timeout
        captured_apprise_request["has_context"] = context is not None
        captured_apprise_request["body"] = request_obj.data.decode("utf-8")
        return _FakeProviderResponse(status_code=200, body='{"status":"success"}')

    monkeypatch.setattr(
        "app.services.notification_providers.apprise.urllib_request.urlopen",
        _fake_apprise_urlopen,
    )
    apprise_provider = registry.get_provider("apprise")
    apprise_result = apprise_provider.send(
        settings={
            "api_url": "https://apprise.example.com/notify",
            "urls": ["mailto://alerts@example.com"],
            "tag": "ops",
            "notify_type": "warning",
            "format": "markdown",
            "timeout_seconds": 12,
            "verify_tls": False,
            "headers": {"X-Test": "true"},
        },
        request=NotificationSendRequest(
            event_type="alert_activated",
            payload={"a": 1},
            rendered_payload={
                "title": "Alert title",
                "body": "Alert body",
                "tag": "critical",
                "type": "failure",
            },
        ),
    )
    assert apprise_result.status == "sent"
    assert apprise_result.status_code == 200
    assert captured_apprise_request["url"] == "https://apprise.example.com/notify"
    assert captured_apprise_request["timeout"] == 12
    assert captured_apprise_request["has_context"] is True
    parsed_apprise_body = json.loads(str(captured_apprise_request["body"]))
    assert parsed_apprise_body["title"] == "Alert title"
    assert parsed_apprise_body["body"] == "[alert_activated] Alert body"
    assert parsed_apprise_body["type"] == "failure"
    assert parsed_apprise_body["tag"] == "critical"
    assert parsed_apprise_body["format"] == "markdown"
    assert parsed_apprise_body["urls"] == ["mailto://alerts@example.com"]


def test_alert_action_validation_errors(client) -> None:
    _ = client
    with pytest.raises(ValueError):
        validate_action_integration_settings(
            provider_type="webhook",
            settings={"url": "not-a-valid-url"},
        )

    assert serialize_action_events(["invalid", "alert_resolved", "alert_resolved"]) == (
        "[\"alert_resolved\"]"
    )


def test_alert_action_integrations_api_crud(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/alert-actions/integrations",
        json={
            "name": "Ops Webhook",
            "provider_type": "webhook",
            "description": "Primary operations webhook",
            "enabled": True,
            "settings": {
                "url": "https://example.com/hooks/ops",
                "method": "post",
                "headers": {"X-Source": "pymc-glass"},
                "timeout_seconds": 7,
                "verify_tls": True,
                "max_body_bytes": 8192,
            },
            "secrets": {"authorization_token": "redacted"},
        },
        headers=headers,
    )
    assert created.status_code == 201
    created_body = created.json()
    integration_id = created_body["id"]
    assert created_body["provider_type"] == "webhook"
    assert created_body["settings"]["method"] == "POST"
    assert created_body["has_secrets"] is True

    listed = client.get("/api/alert-actions/integrations", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == integration_id for item in listed.json())

    updated = client.patch(
        f"/api/alert-actions/integrations/{integration_id}",
        json={
            "enabled": False,
            "settings": {
                "url": "https://example.com/hooks/ops-v2",
                "method": "put",
                "headers": {"X-Source": "pymc-glass-v2"},
                "timeout_seconds": 5,
                "verify_tls": False,
                "max_body_bytes": 4096,
            },
            "secrets": {},
        },
        headers=headers,
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["enabled"] is False
    assert updated_body["settings"]["method"] == "PUT"
    assert updated_body["settings"]["verify_tls"] is False
    assert updated_body["has_secrets"] is False

    deleted = client.delete(f"/api/alert-actions/integrations/{integration_id}", headers=headers)
    assert deleted.status_code == 204
    after_delete = client.get(f"/api/alert-actions/integrations/{integration_id}", headers=headers)
    assert after_delete.status_code == 404

def test_alert_action_integration_test_send_apprise(client, monkeypatch) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    captured_request: dict[str, str | int | bool] = {}

    class _FakeAppriseResponse:
        def __init__(self, *, status_code: int, body: str):
            self._status_code = status_code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def getcode(self) -> int:
            return self._status_code

        def read(self, _max_bytes: int = -1) -> bytes:
            return self._body.encode("utf-8")

    def _fake_apprise_urlopen(request_obj, timeout, context=None):  # noqa: ANN001
        captured_request["url"] = request_obj.full_url
        captured_request["timeout"] = timeout
        captured_request["has_context"] = context is not None
        captured_request["body"] = request_obj.data.decode("utf-8")
        return _FakeAppriseResponse(status_code=200, body='{"status":"success"}')

    monkeypatch.setattr(
        "app.services.notification_providers.apprise.urllib_request.urlopen",
        _fake_apprise_urlopen,
    )

    create_integration = client.post(
        "/api/alert-actions/integrations",
        json={
            "name": "Ops Apprise",
            "provider_type": "apprise",
            "description": "Apprise test route",
            "enabled": True,
            "settings": {
                "api_url": "https://apprise.example.com/notify",
                "urls": ["mailto://alerts@example.com"],
                "tag": "ops",
                "notify_type": "warning",
                "format": "markdown",
                "timeout_seconds": 12,
                "verify_tls": False,
                "headers": {"X-Source": "pyMC_Glass"},
            },
        },
        headers=headers,
    )
    assert create_integration.status_code == 201
    integration_id = create_integration.json()["id"]

    test_send = client.post(
        f"/api/alert-actions/integrations/{integration_id}/test",
        json={
            "event_type": "alert_activated",
            "payload": {"source": "test"},
            "rendered_payload": {
                "title": "Alert title",
                "body": "Alert body",
                "type": "failure",
            },
        },
        headers=headers,
    )
    assert test_send.status_code == 200
    result = test_send.json()
    assert result["status"] == "sent"
    assert result["status_code"] == 200
    assert captured_request["url"] == "https://apprise.example.com/notify"
    assert captured_request["timeout"] == 12
    assert captured_request["has_context"] is True

    apprise_payload = json.loads(str(captured_request["body"]))
    assert apprise_payload["title"] == "Alert title"
    assert apprise_payload["body"] == "[alert_activated] Alert body"
    assert apprise_payload["type"] == "failure"
    assert apprise_payload["format"] == "markdown"
    assert apprise_payload["tag"] == "ops"
    assert apprise_payload["urls"] == ["mailto://alerts@example.com"]

    deleted = client.delete(f"/api/alert-actions/integrations/{integration_id}", headers=headers)
    assert deleted.status_code == 204


def test_alert_action_templates_api_crud(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/alert-actions/templates",
        json={
            "name": "Default Webhook Alert Template",
            "provider_type": "webhook",
            "description": "Template used for baseline webhook alerts",
            "title_template": "Alert: {{ alert.alert_type }}",
            "body_template": "{{ alert.message }}",
            "payload_template": {"message": "{{ alert.message }}", "severity": "{{ alert.severity }}"},
            "default_event_types": ["alert_resolved", "alert_activated"],
            "enabled": True,
        },
        headers=headers,
    )
    assert created.status_code == 201
    created_body = created.json()
    template_id = created_body["id"]
    assert created_body["provider_type"] == "webhook"
    assert created_body["default_event_types"] == ["alert_activated", "alert_resolved"]
    assert created_body["payload_template"] == {
        "message": "{{ alert.message }}",
        "severity": "{{ alert.severity }}",
    }

    updated = client.patch(
        f"/api/alert-actions/templates/{template_id}",
        json={
            "provider_type": None,
            "default_event_types": ["alert_acknowledged"],
            "payload_template": {"message": "ack: {{ alert.message }}"},
            "enabled": False,
        },
        headers=headers,
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["provider_type"] is None
    assert updated_body["default_event_types"] == ["alert_acknowledged"]
    assert updated_body["enabled"] is False

    listed = client.get("/api/alert-actions/templates", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == template_id for item in listed.json())

    deleted = client.delete(f"/api/alert-actions/templates/{template_id}", headers=headers)
    assert deleted.status_code == 204
    after_delete = client.get(f"/api/alert-actions/templates/{template_id}", headers=headers)
    assert after_delete.status_code == 404

def test_alert_policy_action_bindings_api_crud(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_policy_template = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Bindings Policy Template",
            "rule_type": "offline_repeater",
            "severity": "critical",
            "enabled": True,
            "offline_grace_seconds": 120,
            "auto_resolve": True,
            "config": {},
        },
        headers=headers,
    )
    assert created_policy_template.status_code == 201
    policy_template_id = created_policy_template.json()["id"]

    created_integration = client.post(
        "/api/alert-actions/integrations",
        json={
            "name": "Bindings Webhook Integration",
            "provider_type": "webhook",
            "settings": {"url": "https://example.com/bindings", "method": "POST"},
        },
        headers=headers,
    )
    assert created_integration.status_code == 201
    integration_id = created_integration.json()["id"]

    created_action_template = client.post(
        "/api/alert-actions/templates",
        json={
            "name": "Bindings Action Template",
            "provider_type": "webhook",
            "default_event_types": ["alert_activated", "alert_resolved"],
            "payload_template": {"message": "{{ alert.message }}"},
            "enabled": True,
        },
        headers=headers,
    )
    assert created_action_template.status_code == 201
    action_template_id = created_action_template.json()["id"]

    created_binding = client.post(
        "/api/alert-actions/bindings",
        json={
            "policy_template_id": policy_template_id,
            "integration_id": integration_id,
            "action_template_id": action_template_id,
            "event_types": [],
            "min_severity": "warning",
            "enabled": True,
            "sort_order": 40,
            "cooldown_seconds": 30,
        },
        headers=headers,
    )
    assert created_binding.status_code == 201
    created_binding_body = created_binding.json()
    binding_id = created_binding_body["id"]
    assert created_binding_body["event_types"] == ["alert_activated", "alert_resolved"]
    assert created_binding_body["min_severity"] == "warning"
    assert created_binding_body["sort_order"] == 40

    listed_bindings = client.get("/api/alert-actions/bindings", headers=headers)
    assert listed_bindings.status_code == 200
    assert any(item["id"] == binding_id for item in listed_bindings.json())

    updated_binding = client.patch(
        f"/api/alert-actions/bindings/{binding_id}",
        json={
            "event_types": ["alert_acknowledged"],
            "enabled": False,
            "sort_order": 60,
            "cooldown_seconds": 45,
        },
        headers=headers,
    )
    assert updated_binding.status_code == 200
    updated_binding_body = updated_binding.json()
    assert updated_binding_body["event_types"] == ["alert_acknowledged"]
    assert updated_binding_body["enabled"] is False
    assert updated_binding_body["sort_order"] == 60
    assert updated_binding_body["cooldown_seconds"] == 45

    get_binding = client.get(f"/api/alert-actions/bindings/{binding_id}", headers=headers)
    assert get_binding.status_code == 200
    assert get_binding.json()["id"] == binding_id

    deleted_binding = client.delete(f"/api/alert-actions/bindings/{binding_id}", headers=headers)
    assert deleted_binding.status_code == 204
    get_deleted_binding = client.get(f"/api/alert-actions/bindings/{binding_id}", headers=headers)
    assert get_deleted_binding.status_code == 404


def test_alert_policy_action_binding_provider_mismatch_denied(client) -> None:
    _bootstrap_admin(client)
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created_policy_template = client.post(
        "/api/alert-policies/templates",
        json={
            "name": "Mismatch Policy Template",
            "rule_type": "offline_repeater",
            "severity": "critical",
            "enabled": True,
            "offline_grace_seconds": 120,
            "auto_resolve": True,
            "config": {},
        },
        headers=headers,
    )
    assert created_policy_template.status_code == 201
    policy_template_id = created_policy_template.json()["id"]

    created_integration = client.post(
        "/api/alert-actions/integrations",
        json={
            "name": "Mismatch Integration",
            "provider_type": "webhook",
            "settings": {"url": "https://example.com/mismatch", "method": "POST"},
        },
        headers=headers,
    )
    assert created_integration.status_code == 201
    integration_id = created_integration.json()["id"]

    created_action_template = client.post(
        "/api/alert-actions/templates",
        json={
            "name": "Mismatch Action Template",
            "provider_type": "pushover",
            "default_event_types": ["alert_activated"],
            "enabled": True,
        },
        headers=headers,
    )
    assert created_action_template.status_code == 201
    action_template_id = created_action_template.json()["id"]

    denied_binding = client.post(
        "/api/alert-actions/bindings",
        json={
            "policy_template_id": policy_template_id,
            "integration_id": integration_id,
            "action_template_id": action_template_id,
            "event_types": ["alert_activated"],
        },
        headers=headers,
    )
    assert denied_binding.status_code == 422
    assert "provider_type" in denied_binding.json()["detail"].lower()


def test_alert_actions_viewer_read_only(client) -> None:
    _bootstrap_admin(client)
    admin_token = _login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_viewer = client.post(
        "/api/users",
        json={
            "email": "viewer-actions@example.com",
            "password": "verysecurepassword123",
            "role": "viewer",
            "display_name": "Viewer Actions",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert create_viewer.status_code == 201

    viewer_token = _login(client, email="viewer-actions@example.com")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    list_providers = client.get("/api/alert-actions/providers", headers=viewer_headers)
    assert list_providers.status_code == 200
    list_integrations = client.get("/api/alert-actions/integrations", headers=viewer_headers)
    assert list_integrations.status_code == 200
    list_templates = client.get("/api/alert-actions/templates", headers=viewer_headers)
    assert list_templates.status_code == 200
    list_bindings = client.get("/api/alert-actions/bindings", headers=viewer_headers)
    assert list_bindings.status_code == 200

    denied_create_integration = client.post(
        "/api/alert-actions/integrations",
        json={
            "name": "Denied Integration",
            "provider_type": "webhook",
            "settings": {"url": "https://example.com/denied", "method": "POST"},
        },
        headers=viewer_headers,
    )
    assert denied_create_integration.status_code == 403

    denied_create_template = client.post(
        "/api/alert-actions/templates",
        json={
            "name": "Denied Template",
            "default_event_types": ["alert_activated"],
        },
        headers=viewer_headers,
    )
    assert denied_create_template.status_code == 403

    denied_create_binding = client.post(
        "/api/alert-actions/bindings",
        json={
            "policy_template_id": "missing",
            "integration_id": "missing",
            "action_template_id": "missing",
            "event_types": ["alert_activated"],
        },
        headers=viewer_headers,
    )
    assert denied_create_binding.status_code == 403
