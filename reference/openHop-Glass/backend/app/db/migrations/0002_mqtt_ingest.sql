CREATE TABLE IF NOT EXISTS mqtt_ingest_events (
    id TEXT PRIMARY KEY,
    repeater_id TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL,
    event_name TEXT NULL,
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    dedup_key TEXT NOT NULL UNIQUE,
    ingested_at TIMESTAMP NOT NULL,
    FOREIGN KEY(repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_mqtt_ingest_events_repeater_id ON mqtt_ingest_events(repeater_id);
CREATE INDEX IF NOT EXISTS ix_mqtt_ingest_events_timestamp ON mqtt_ingest_events(timestamp);
CREATE INDEX IF NOT EXISTS ix_mqtt_ingest_events_event_type ON mqtt_ingest_events(event_type);
CREATE INDEX IF NOT EXISTS ix_mqtt_ingest_events_dedup_key ON mqtt_ingest_events(dedup_key);
