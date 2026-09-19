CREATE TABLE IF NOT EXISTS topology_observation_samples (
    id TEXT PRIMARY KEY,
    observer_repeater_id TEXT NOT NULL,
    observed_node_id TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    route_type INTEGER NULL,
    zero_hop INTEGER NULL,
    contact_type TEXT NULL,
    rssi REAL NULL,
    snr REAL NULL,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(observer_repeater_id, observed_node_id, observed_at),
    FOREIGN KEY(observer_repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE,
    FOREIGN KEY(observed_node_id) REFERENCES topology_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_topology_observation_samples_observed_node_id
    ON topology_observation_samples(observed_node_id);
CREATE INDEX IF NOT EXISTS ix_topology_observation_samples_observer_repeater_id
    ON topology_observation_samples(observer_repeater_id);
CREATE INDEX IF NOT EXISTS ix_topology_observation_samples_observed_at
    ON topology_observation_samples(observed_at);
