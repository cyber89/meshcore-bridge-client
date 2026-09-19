CREATE TABLE IF NOT EXISTS node_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_node_groups_name ON node_groups(name);

CREATE TABLE IF NOT EXISTS node_group_memberships (
    id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    repeater_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY(group_id) REFERENCES node_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_node_group_memberships_group_id ON node_group_memberships(group_id);
CREATE INDEX IF NOT EXISTS ix_node_group_memberships_repeater_id ON node_group_memberships(repeater_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_node_group_memberships_group_repeater
ON node_group_memberships(group_id, repeater_id);

CREATE TABLE IF NOT EXISTS alert_policy_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    rule_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    threshold_value REAL NULL,
    window_minutes INTEGER NULL,
    offline_grace_seconds INTEGER NULL,
    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
    auto_resolve INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_alert_policy_templates_name ON alert_policy_templates(name);
CREATE INDEX IF NOT EXISTS ix_alert_policy_templates_rule_type ON alert_policy_templates(rule_type);
CREATE INDEX IF NOT EXISTS ix_alert_policy_templates_severity ON alert_policy_templates(severity);
CREATE INDEX IF NOT EXISTS ix_alert_policy_templates_enabled ON alert_policy_templates(enabled);

CREATE TABLE IF NOT EXISTS alert_policy_assignments (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(template_id) REFERENCES alert_policy_templates(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_alert_policy_assignments_template_id ON alert_policy_assignments(template_id);
CREATE INDEX IF NOT EXISTS ix_alert_policy_assignments_scope_type ON alert_policy_assignments(scope_type);
CREATE INDEX IF NOT EXISTS ix_alert_policy_assignments_scope_id ON alert_policy_assignments(scope_id);
CREATE INDEX IF NOT EXISTS ix_alert_policy_assignments_enabled ON alert_policy_assignments(enabled);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_policy_assignments_template_scope
ON alert_policy_assignments(template_id, scope_type, scope_id);
