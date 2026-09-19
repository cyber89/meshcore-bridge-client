ALTER TABLE alerts ADD COLUMN state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE alerts ADD COLUMN first_seen_at TIMESTAMP NULL;
ALTER TABLE alerts ADD COLUMN last_seen_at TIMESTAMP NULL;
ALTER TABLE alerts ADD COLUMN fingerprint TEXT NULL;
ALTER TABLE alerts ADD COLUMN acked_at TIMESTAMP NULL;
ALTER TABLE alerts ADD COLUMN acked_by TEXT NULL;
ALTER TABLE alerts ADD COLUMN note TEXT NULL;

UPDATE alerts
SET
    first_seen_at = COALESCE(first_seen_at, timestamp, CURRENT_TIMESTAMP),
    last_seen_at = COALESCE(last_seen_at, resolved_at, timestamp, CURRENT_TIMESTAMP),
    state = CASE
        WHEN resolved_at IS NOT NULL THEN 'resolved'
        ELSE COALESCE(state, 'active')
    END;

CREATE INDEX IF NOT EXISTS ix_alerts_state ON alerts(state);
CREATE INDEX IF NOT EXISTS ix_alerts_fingerprint ON alerts(fingerprint);
CREATE INDEX IF NOT EXISTS ix_alerts_first_seen_at ON alerts(first_seen_at);
CREATE INDEX IF NOT EXISTS ix_alerts_last_seen_at ON alerts(last_seen_at);

CREATE TABLE IF NOT EXISTS notification_events (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    last_error TEXT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    sent_at TIMESTAMP NULL,
    FOREIGN KEY(alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_notification_events_alert_id ON notification_events(alert_id);
CREATE INDEX IF NOT EXISTS ix_notification_events_status ON notification_events(status);
CREATE INDEX IF NOT EXISTS ix_notification_events_next_attempt_at ON notification_events(next_attempt_at);
