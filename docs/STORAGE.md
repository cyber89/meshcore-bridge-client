# Station storage and browser cache

> **AI Context & Machine Contract**:
> - **Domain**: Station State & Chat Persistence ([ADR 0017](adr/0017-sqlite-station-browser-cache.md))
> - **Authority Level**: Level 4 (Living SSoT for SQLite Storage)
> - **Core Symbols**: \src/station_database.py\ (\StationDatabase\)
> - **Primary Invariant**: SQLite mutations \MUST\ execute off the asyncio event loop (\syncio.to_thread\). WAL mode enabled.
> - **Database File**: \data/meshcore.sqlite3\ (\DATABASE_PATH\)

SQLite is the authoritative store for station state and chat history. Browser storage improves the interface and does not replace the station database.

| Store | Responsibility |
| --- | --- |
| LocalStorage | Theme, language, panel layout and other interface preferences. |
| IndexedDB | Messages already downloaded, separated by persistent station UUID; quick conversation loading and offline reading. The old browser store remains available for explicit import. |
| SQLite | Received and outgoing chat, conversations, delivery states, node registry, channels and PSKs, services and MQTT presets, airtime history, repeater cooldown timestamps, and MQTT command idempotency ledger (`command_ledger`). |

API credentials and browser sessions use an HttpOnly session cookie (`meshcore_session`) and an in-memory CSRF token (`X-CSRF-Token`). Credentials and session tokens are never stored in client browser storage (`localStorage` or `sessionStorage`). The database may contain channel and service credentials: restrict access to the station account and protect backups as secrets. SQLite files and backups use mode 0600 on POSIX; on Windows this does not configure NTFS ACLs, so restrict the directory and account permissions separately.

## Location and migration

`DATABASE_PATH` selects the database; the default is `DATA_DIR/meshcore.sqlite3`. Keep it on a local filesystem supporting SQLite locking. The standard-library `sqlite3` driver adds no database server dependency. Startup initializes a versioned schema, WAL journaling and `synchronous=FULL`; asynchronous operations use worker threads. Database connections are short-lived and transaction access is serialized within the repository.

When each state domain is first loaded, its existing JSON file is validated and imported transactionally if the database has no document for that domain. Existing `NODE_REGISTRY_STORAGE_PATH`, `CHANNELS_JSON_PATH`, `AIRTIME_HISTORY_FILE`, and the services/cooldown paths select the migration sources. Files are preserved, and later startups use the database rather than overwriting it from stale JSON. Invalid input or storage errors are reported; do not delete the database to hide an error. Missing files retain the domain's existing defaults and environment bootstrap behavior. A migration can complete one domain at a time; it is not a transaction across every domain.

The state documents retain their existing data shapes inside SQLite; messages and conversations use indexed tables. This preserves unknown node metadata, explicit nulls, airtime accounting and cooldown timestamps. `.env` remains deployment configuration, map MBTiles remain independent, and JSON export/import payloads and static assets remain JSON. Existing JSON-only helper calls are retained for compatibility, while the production bridge injects the database into its state owners.

Chat recording runs in the bridge, including when the web server is disabled or no browser is open. Outgoing chat is recorded before transmission and then updated after the radio result. A sent state confirms the local transmission result; delivered requires a correlated mesh ACK. Consuming the correlation and recording delivery use one transaction, and delivery cannot regress after confirmation. The transmission queue itself is not durable: restart does not replay queued history. No new radio polling, retries, MQTT replay or periodic timers are introduced by persistence. Async integrations construct the bridge through `await MeshCoreBridge.create()` to keep startup I/O outside their event loop; the synchronous CLI constructs it before starting its loop.

## Browser history

The interface fetches authoritative history and caches it per station UUID. Older messages load through sequence cursors; the page size is bounded. On network failure it can read downloaded messages for the last validated station. Authorization errors do not trigger offline fallback. Offline reading requires an already loaded interface; the app does not install a service worker or promise a cold offline launch of CDN-dependent maps.

Settings provides an explicit import of old browser history in batches. Import is idempotent, requires a stable timestamp, validates messages, removes credential fields and does not transmit them. Imported records carry `source=browser_import`; old delivery claims become unverified sent states and ACK tracking is not activated. Existing server records are never overwritten by an import. Clearing the browser cache removes cached messages only; it does not erase SQLite history. There is no automatic history retention deadline or history deletion endpoint.

History reads, imports and WebSocket access always require an authenticated session or integration credential. The personal account, password hash and session/token digests share the station SQLite database. The app has station-level authorization; the authorized operator can access stored DMs. It does not provide separate private accounts per operator. See [authentication](plans/AUTHENTICATION_PLAN.md). Database backups include authentication state and must be protected; restoring a backup can restore sessions and tokens saved at that time.

## API

| Operation | Behavior |
| --- | --- |
| `GET /api/messages/history?feed_key=ch_0&limit=100&before=123` | Chronological page; optional feed and positive sequence cursor; limit 1–200. Returns `messages`, `station_id`, `next_before`, `has_more` inside `data`. |
| `GET /api/messages/conversations` | Conversation summaries and station UUID. |
| `POST /api/messages/import` | Explicit `{"messages": [...], "station_id": "..."}` batch of 1–200 historical records; returns import counts. Station mismatch returns 409 before writes. No radio transmission. |
| `GET /api/messages/recent` | Compatibility envelope `data` list and `count`, now backed by SQLite in production. |

Feeds use `ch_<channel index>` or `dm_<public key>`. Messages include stable `msg_id`, sequence `seq`, station identity, direction, timestamp, text and delivery state. Invalid history inputs return 422; unavailable storage returns 503; unexpected storage failures return 500 without exposing credentials.

## Command idempotency ledger (`command_ledger`)

To guarantee strict command idempotency for LAN/n8n MQTT commands ([ADR 0021](adr/0021-mqtt-security-idempotency-and-unified-topics.md)), SQLite maintains the `command_ledger` table:
- **Schema**: `(id INTEGER PRIMARY KEY AUTOINCREMENT, station_id TEXT NOT NULL, integration_scope TEXT NOT NULL, command_id TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, result_payload TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE (station_id, integration_scope, command_id))`
- **Index**: `idx_command_ledger_lookup` on `(station_id, integration_scope, command_id)`
- **Capacity Policy**: Strictly bounded to 10 000 rows. Pruning executes inline during insertion (retaining the most recent entries) without requiring background timers.
- **Rollback Note**: Restoring an older SQLite backup also reverts the ledger; incoming requests with previously reserved command IDs during the gap must be reconciled by the integration.

## Backup, restore and rollback

Back up `.env`, maps and logs separately. Use SQLite's online backup API for a running database; `StationDatabase.backup(destination)` exposes it. Do not copy only the main file while a WAL writer is running. Alternatively stop the bridge cleanly and back up the database with any remaining WAL/SHM companions as a consistent set. Keep backups outside version control with restricted permissions.

Restore only while the service is stopped: restore a consistent database backup, preserve ownership, and keep `DATABASE_PATH` pointed to it. A newer unknown schema is rejected rather than silently downgraded. A new empty database generates a new station UUID and therefore a separate browser cache.

Preserved JSON files are a pre-migration snapshot, not a current backup. Rolling back to a JSON-only release loses subsequent changes unless you export the current SQLite documents to the legacy shapes first. History will remain unavailable to that older release. Installation updates preserve `data/`; an external `DATABASE_PATH` needs its own backup policy.

## Validation scope

Regression cases cover state migration, delivery monotonicity, history cursors, import idempotency and authenticated history reads. They are written but are executed only when explicitly requested, in accordance with the repository policy. Static checking and frontend build checks do not establish runtime migration correctness or measured performance.
