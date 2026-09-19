CREATE TABLE IF NOT EXISTS config_snapshots (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    command_id TEXT NULL UNIQUE,
    captured_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    encryption_key_id TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_size_bytes INTEGER NOT NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE,
    FOREIGN KEY(command_id) REFERENCES command_queue(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_config_snapshots_repeater_id ON config_snapshots(repeater_id);
CREATE INDEX IF NOT EXISTS ix_config_snapshots_captured_at ON config_snapshots(captured_at);
CREATE INDEX IF NOT EXISTS ix_config_snapshots_encryption_key_id ON config_snapshots(encryption_key_id);
CREATE INDEX IF NOT EXISTS ix_config_snapshots_payload_sha256 ON config_snapshots(payload_sha256);
