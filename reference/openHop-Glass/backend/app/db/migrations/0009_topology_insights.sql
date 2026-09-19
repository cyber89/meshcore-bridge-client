CREATE TABLE IF NOT EXISTS topology_nodes (
    id TEXT PRIMARY KEY,
    pubkey TEXT NOT NULL UNIQUE,
    node_name TEXT NULL,
    is_repeater INTEGER NULL,
    contact_type TEXT NULL,
    latitude REAL NULL,
    longitude REAL NULL,
    first_seen_at TIMESTAMP NULL,
    last_seen_at TIMESTAMP NOT NULL,
    last_observed_by_repeater_id TEXT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY(last_observed_by_repeater_id) REFERENCES repeaters(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_topology_nodes_pubkey ON topology_nodes(pubkey);
CREATE INDEX IF NOT EXISTS ix_topology_nodes_last_seen_at ON topology_nodes(last_seen_at);
CREATE INDEX IF NOT EXISTS ix_topology_nodes_contact_type ON topology_nodes(contact_type);
CREATE INDEX IF NOT EXISTS ix_topology_nodes_last_observed_by_repeater_id ON topology_nodes(last_observed_by_repeater_id);

CREATE TABLE IF NOT EXISTS topology_observations (
    id TEXT PRIMARY KEY,
    observer_repeater_id TEXT NOT NULL,
    observed_node_id TEXT NOT NULL,
    contact_type TEXT NULL,
    route_type INTEGER NULL,
    zero_hop INTEGER NULL,
    latitude REAL NULL,
    longitude REAL NULL,
    rssi REAL NULL,
    snr REAL NULL,
    first_seen_at TIMESTAMP NULL,
    last_seen_at TIMESTAMP NOT NULL,
    advert_count INTEGER NULL,
    last_event_timestamp TIMESTAMP NOT NULL,
    last_ingested_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(observer_repeater_id, observed_node_id),
    FOREIGN KEY(observer_repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE,
    FOREIGN KEY(observed_node_id) REFERENCES topology_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_topology_observations_observer_repeater_id ON topology_observations(observer_repeater_id);
CREATE INDEX IF NOT EXISTS ix_topology_observations_observed_node_id ON topology_observations(observed_node_id);
CREATE INDEX IF NOT EXISTS ix_topology_observations_last_seen_at ON topology_observations(last_seen_at);
CREATE INDEX IF NOT EXISTS ix_topology_observations_contact_type ON topology_observations(contact_type);
CREATE INDEX IF NOT EXISTS ix_topology_observations_route_type ON topology_observations(route_type);
CREATE INDEX IF NOT EXISTS ix_topology_observations_zero_hop ON topology_observations(zero_hop);

CREATE TABLE IF NOT EXISTS topology_rollups_hourly (
    id TEXT PRIMARY KEY,
    bucket_start TIMESTAMP NOT NULL,
    observer_repeater_id TEXT NOT NULL,
    observed_nodes INTEGER NOT NULL,
    zero_hop_nodes INTEGER NOT NULL,
    avg_rssi REAL NULL,
    avg_snr REAL NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(bucket_start, observer_repeater_id),
    FOREIGN KEY(observer_repeater_id) REFERENCES repeaters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_topology_rollups_hourly_bucket_start ON topology_rollups_hourly(bucket_start);
CREATE INDEX IF NOT EXISTS ix_topology_rollups_hourly_observer_repeater_id ON topology_rollups_hourly(observer_repeater_id);
