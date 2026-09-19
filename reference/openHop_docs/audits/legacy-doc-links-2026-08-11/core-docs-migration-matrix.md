# openHop Core docs migration matrix

Source repository: `/home/yellowcooln/openhop-dev/openhop_core`
Immutable source ref: `0d1dbf2c10c23be07d4a3c529eee05414994b499` (`origin/dev`)
Central docs branch: `docs/legacy-link-migration`

This matrix accounts for every tracked path under `openhop_core/docs/`. Content is
migrated by current topic and source behavior rather than copied byte-for-byte. The
legacy pages include stale lifecycle, pin, owner/URL, and release-process guidance.

| Core source path | Central destination/disposition | Status and notes |
| --- | --- | --- |
| `docs/docs/index.md` | `/projects/openhop-core/`, `/quick-start/`, `/architecture-and-transports/` | Migrated; installation, optional dependency, hardware boundary, lifecycle, help, and acknowledgement topics represented |
| `docs/docs/node.md` | `/node-usage/`, `/direct-sx1262-hardware/`, `/examples/` | Migrated and corrected; old blocking lifecycle and stale Waveshare TXEN prose not copied |
| `docs/docs/examples.md` | `/examples/`, `/direct-sx1262-hardware/`, `/kiss-modem-protocol/` | Migrated by current tracked script inventory; RF/device/network side effects labeled |
| `docs/docs/api/core.md` | `/api-reference/`, `/protocol-api/`, `/node-and-dispatcher-api/` | Migrated as a current API index and focused references |
| `docs/docs/api/node.md` | `/node-and-dispatcher-api/`, `/node-usage/` | Migrated; events and handler families included |
| `docs/docs/api/dispatcher.md` | `/node-and-dispatcher-api/` | Migrated; lifecycle, TX/ACK, routing/filtering, handlers, callbacks, errors, and concurrency included |
| `docs/docs/api/protocol.md` | `/protocol-api/` | Migrated; packets, builders, filters, utilities, crypto, identity, routing/scope, constants, and compatibility workflow included |
| `docs/docs/companion.md` | `/companion-applications/`, `/companion-frame-server/`, `/companion-recipes/`, `/api-reference/#companion-apis` | Migrated across conceptual, transport, use-case, model, callback, store, persistence, and API coverage |
| `docs/docs/contributing.md` | `/projects/openhop-core/development/` | Migrated with current test/pre-commit/build facts; obsolete release process replaced by branch/commit history because Core publishes no GitHub Releases |
| `docs/docs/images/PyMC.png` | Not copied | Retired pyMC branding; central docs already owns current openHop assets |
| `docs/docs/images/PyMC.svg` | Not copied | Retired pyMC branding; central docs already owns current openHop assets |
| `docs/docs/images/openhop_transparent_trim.png` | Not copied | No migrated article requires it; central site uses its own current logo assets |
| `docs/docs/styles/brand.css` | Not copied | MkDocs-specific presentation; central Astro/Starlight site uses `src/styles/brand.css` |
| `docs/mkdocs.yml` | Superseded by central `astro.config.mjs` | Old canonical/repository URLs and MkDocs navigation are intentionally not migrated |
| `docs/requirements.txt` | Not copied | MkDocs build dependency list; central site uses `package.json`/`package-lock.json` |
| `docs/serve-docs.sh` | Not copied | Superseded by central Astro development/preview commands |
| `docs/serve-docs.bat` | Not copied | Superseded by central Astro development/preview commands |

## Central Core article set after migration

- `index.md` — project overview and journey
- `quick-start.md` — installation and safe first lifecycle
- `architecture-and-transports.md` — layered design and transport families
- `node-usage.md` — practical MeshNode lifecycle, sending, handlers, events, stores, and diagnostics
- `companion-applications.md` — class choice and core companion lifecycle
- `examples.md` — complete current example inventory and side-effect classification
- `api-reference.md` — public export/index boundary
- `kiss-modem-protocol.md` — pinned MeshCore KISS compatibility
- `direct-sx1262-hardware.md` — current direct hardware mappings and safety
- `companion-frame-server.md` — TCP frame transport, commands, pushes, persistence, and exposure
- `companion-recipes.md` — chat, gateways, bridges, diagnostics, channels, callbacks, and models
- `node-and-dispatcher-api.md` — node, dispatcher, events, callbacks, and handlers
- `protocol-api.md` — packet/protocol/identity/crypto/routing/scope reference
- `development.md` — contribution workflow and commit-based development history

## Deliberate corrections during migration

- Core and Repeater do not publish GitHub Releases; users are directed to exact branch
  and commit history.
- `MeshNode.start()` is run in a task and stopped from another task; the caller owns
  radio cleanup.
- Current executable board profiles and current source/tests outrank stale MkDocs pin
  prose.
- Hardware examples are not treated as unattended tests.
- Mutable vendor/upstream documentation remains cited, while openHop-specific behavior
  is documented centrally and pinned where protocol compatibility depends on it.
