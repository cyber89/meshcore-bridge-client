CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    display_name TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_auth_tokens_user_id ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_token_hash ON auth_tokens(token_hash);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_expires_at ON auth_tokens(expires_at);

CREATE TABLE IF NOT EXISTS repeaters (
    id TEXT PRIMARY KEY,
    node_name TEXT NOT NULL UNIQUE,
    pubkey TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    location TEXT NULL,
    firmware_version TEXT NULL,
    last_inform_at TIMESTAMP NULL,
    inform_ip TEXT NULL,
    config_hash TEXT NULL,
    cert_serial TEXT NULL,
    cert_expires_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_repeaters_status ON repeaters(status);
CREATE INDEX IF NOT EXISTS ix_repeaters_last_inform_at ON repeaters(last_inform_at);

CREATE TABLE IF NOT EXISTS inform_snapshots (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    cpu REAL NULL,
    memory REAL NULL,
    disk REAL NULL,
    noise_floor REAL NULL,
    rx_total INTEGER NULL,
    tx_total INTEGER NULL,
    forwarded INTEGER NULL,
    dropped INTEGER NULL,
    airtime_percent REAL NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_inform_snapshots_repeater_id ON inform_snapshots(repeater_id);
CREATE INDEX IF NOT EXISTS ix_inform_snapshots_timestamp ON inform_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS packets (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    packet_type TEXT NULL,
    route TEXT NULL,
    rssi REAL NULL,
    snr REAL NULL,
    src_hash TEXT NULL,
    dst_hash TEXT NULL,
    payload TEXT NULL,
    packet_hash TEXT NULL UNIQUE,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_packets_repeater_id ON packets(repeater_id);
CREATE INDEX IF NOT EXISTS ix_packets_timestamp ON packets(timestamp);

CREATE TABLE IF NOT EXISTS command_queue (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NULL,
    command TEXT NOT NULL,
    params_json TEXT NULL,
    status TEXT NOT NULL,
    result_json TEXT NULL,
    requested_by TEXT NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_command_queue_repeater_id ON command_queue(repeater_id);
CREATE INDEX IF NOT EXISTS ix_command_queue_status ON command_queue(status);

CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    serial TEXT NOT NULL UNIQUE,
    cn TEXT NULL,
    issued_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP NULL,
    pem_hash TEXT NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_certificates_repeater_id ON certificates(repeater_id);
CREATE INDEX IF NOT EXISTS ix_certificates_serial ON certificates(serial);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NULL,
    timestamp TIMESTAMP NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    resolved_at TIMESTAMP NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_alerts_repeater_id ON alerts(repeater_id);
CREATE INDEX IF NOT EXISTS ix_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS ix_alerts_severity ON alerts(severity);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NULL,
    timestamp TIMESTAMP NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NULL,
    target_id TEXT NULL,
    details_json TEXT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_log_action ON audit_log(action);
