CREATE TABLE IF NOT EXISTS transport_key_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_group_id TEXT NULL,
    flood_policy TEXT NOT NULL DEFAULT 'allow',
    transport_key TEXT NULL,
    sort_order INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(parent_group_id) REFERENCES transport_key_groups(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_transport_key_groups_parent_group_id
ON transport_key_groups(parent_group_id);
CREATE INDEX IF NOT EXISTS ix_transport_key_groups_name
ON transport_key_groups(name);
CREATE TABLE IF NOT EXISTS transport_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    group_id TEXT NULL,
    flood_policy TEXT NOT NULL DEFAULT 'allow',
    transport_key TEXT NULL,
    sort_order INTEGER NOT NULL DEFAULT 100,
    last_used_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(group_id) REFERENCES transport_key_groups(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_transport_keys_group_id
ON transport_keys(group_id);
CREATE INDEX IF NOT EXISTS ix_transport_keys_name
ON transport_keys(name);
CREATE TABLE IF NOT EXISTS transport_key_sync_status (
    repeater_id TEXT PRIMARY KEY,
    command_id TEXT NULL,
    payload_hash TEXT NULL,
    status TEXT NOT NULL DEFAULT 'idle',
    error_message TEXT NULL,
    queued_at TIMESTAMP NULL,
    dispatched_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE,
    FOREIGN KEY(command_id) REFERENCES command_queue(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_transport_key_sync_status_status
ON transport_key_sync_status(status);
CREATE INDEX IF NOT EXISTS ix_transport_key_sync_status_payload_hash
ON transport_key_sync_status(payload_hash);
CREATE INDEX IF NOT EXISTS ix_transport_key_sync_status_command_id
ON transport_key_sync_status(command_id);
