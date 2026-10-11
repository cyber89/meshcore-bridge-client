# ADR 0017: SQLite station persistence and browser cache

- **Status**: Accepted
- **Date**: 2026-10-10
- **Supersedes**: [ADR 0005](0005-json-atomic-persistence-over-sqlite.md)

The station must retain chat without an open browser and share history across authorized browsers. The user selected SQLite for messages, delivery and existing JSON state, IndexedDB for downloaded/offline chat, and LocalStorage for interface preferences.

Use standard-library SQLite with WAL, FULL synchronization, versioned schema, indexed chat tables, and transactional state documents. Preserve existing domain data shapes and safety timestamps. Import legacy JSON once without deleting it; explicitly import old browser history without RF replay. Run asynchronous storage work outside the event loop and preserve existing bounded queues and transmission safeguards.

SQLite needs no separate daemon and supports this single-host deployment. Redis is not introduced. WAL requires local filesystem locking; it is not a multi-host writer architecture. FULL synchronization trades disk latency for commit durability, without a claim of measured CPU, memory or throughput. Browser caches can be evicted; SQLite remains authoritative. Secrets in state require protected database files and backups.

ADR 0005 remains historical. Its generic database memory estimates and corruption comparisons were not measurements of this application and do not determine this decision. `.env`, read-only MBTiles, static JSON and wire formats retain their existing roles. MQTT queues and RF transmission admission remain in memory; persistence does not replay queued sends after restart. See [storage operations](../STORAGE.md) and [integration plan](../STORAGE_INTEGRATION_PLAN.md).
