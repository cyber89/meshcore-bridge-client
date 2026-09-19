CREATE TABLE IF NOT EXISTS alert_action_integrations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    provider_type TEXT NOT NULL,
    description TEXT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    settings_json TEXT NOT NULL DEFAULT '{}',
    secrets_json TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_alert_action_integrations_provider_type
ON alert_action_integrations(provider_type);
CREATE INDEX IF NOT EXISTS ix_alert_action_integrations_enabled
ON alert_action_integrations(enabled);
CREATE TABLE IF NOT EXISTS alert_action_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    provider_type TEXT NULL,
    description TEXT NULL,
    title_template TEXT NULL,
    body_template TEXT NULL,
    payload_template_json TEXT NULL,
    default_event_types_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_alert_action_templates_provider_type
ON alert_action_templates(provider_type);
CREATE INDEX IF NOT EXISTS ix_alert_action_templates_enabled
ON alert_action_templates(enabled);
CREATE TABLE IF NOT EXISTS alert_policy_action_bindings (
    id TEXT PRIMARY KEY,
    policy_template_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    action_template_id TEXT NOT NULL,
    event_types_json TEXT NOT NULL DEFAULT '[]',
    min_severity TEXT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(policy_template_id) REFERENCES alert_policy_templates(id) ON DELETE CASCADE,
    FOREIGN KEY(integration_id) REFERENCES alert_action_integrations(id) ON DELETE CASCADE,
    FOREIGN KEY(action_template_id) REFERENCES alert_action_templates(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_alert_policy_action_bindings_policy_template_id
ON alert_policy_action_bindings(policy_template_id);
CREATE INDEX IF NOT EXISTS ix_alert_policy_action_bindings_integration_id
ON alert_policy_action_bindings(integration_id);
CREATE INDEX IF NOT EXISTS ix_alert_policy_action_bindings_action_template_id
ON alert_policy_action_bindings(action_template_id);
CREATE INDEX IF NOT EXISTS ix_alert_policy_action_bindings_enabled
ON alert_policy_action_bindings(enabled);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_policy_action_bindings_unique_binding
ON alert_policy_action_bindings(policy_template_id, integration_id, action_template_id);
ALTER TABLE notification_events ADD COLUMN integration_id TEXT NULL;
ALTER TABLE notification_events ADD COLUMN action_template_id TEXT NULL;
ALTER TABLE notification_events ADD COLUMN binding_id TEXT NULL;
ALTER TABLE notification_events ADD COLUMN provider_type TEXT NULL;
ALTER TABLE notification_events ADD COLUMN idempotency_key TEXT NULL;
ALTER TABLE notification_events ADD COLUMN rendered_payload_json TEXT NULL;
ALTER TABLE notification_events ADD COLUMN response_status_code INTEGER NULL;
ALTER TABLE notification_events ADD COLUMN provider_message_id TEXT NULL;
CREATE INDEX IF NOT EXISTS ix_notification_events_integration_id
ON notification_events(integration_id);
CREATE INDEX IF NOT EXISTS ix_notification_events_action_template_id
ON notification_events(action_template_id);
CREATE INDEX IF NOT EXISTS ix_notification_events_binding_id
ON notification_events(binding_id);
CREATE INDEX IF NOT EXISTS ix_notification_events_provider_type
ON notification_events(provider_type);
CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_events_idempotency_key
ON notification_events(idempotency_key);
