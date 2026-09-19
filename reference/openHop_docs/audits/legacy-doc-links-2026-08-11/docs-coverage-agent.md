# Central openHop Docs coverage and route inventory

Audit date: 2026-08-11
Scope: central `openHop_docs` coverage for `openhop_repeater` and `openhop_core`; read-only inspection of source repositories and legacy documentation links.

## Repository integrity baseline

| Repository | Branch | HEAD | Initial status |
| --- | --- | --- | --- |
| `openHop_docs` | `audit/legacy-doc-links-2026-08-11` (tracking `origin/dev`) | `17d0fe7a97aab64303942c8eaaf048af1b1cabf7` | Clean |
| `openhop_repeater` | `feat/authentik-oidc` | `0975c4b63916bf88ee60b6bdc3514ba106136570` | Clean |
| `openhop_core` | `fix/modem-cad-symbol-count` | `0e69673ca549a31e5fdbb762c337d4bb847620d8` | Clean |

The central site declares `https://docs.openhop.dev` as its site URL (`astro.config.mjs:6-8`) and autogenerates the Core and Repeater sidebars from their content directories (`astro.config.mjs:73-84`). The checked-out generated sitemap corroborates lowercase, trailing-slash routes (`dist/sitemap-0.xml:1`). No `slug`, `redirect`, `redirects`, `alias`, or `aliases` declarations were found in tracked Markdown/MDX/config source. Therefore the inventory below is the canonical file-derived route set; the repo supplies no compatibility redirects.

A read-only live HTTP probe was attempted but denied by the execution runtime before any request results were returned. Consequently this report makes no live status-code or redirect-destination claims. The old-host results in the mapping table are likewise intentionally recorded as **not checked**, not guessed.

## Exact central route/title/source inventory

### openHop Repeater

| Canonical article route | Page title | Source evidence | Coverage/IA note |
| --- | --- | --- | --- |
| `/projects/openhop-repeater/` | openHop Repeater Overview | `src/content/docs/projects/openhop-repeater/index.md:1-3` | Canonical project landing page; concise overview. |
| `/projects/openhop-repeater/api-reference/` | API Reference | `src/content/docs/projects/openhop-repeater/API-Reference.mdx:1-3` | 36-line wrapper around the interactive OpenAPI viewer; thin by design, not a prose reference. Filename capitalization normalizes to a lowercase route. |
| `/projects/openhop-repeater/cad-calibration/` | CAD Calibration | `src/content/docs/projects/openhop-repeater/CAD-Calibration.md:1-3` | Substantive operator guide. |
| `/projects/openhop-repeater/development/` | Development | `src/content/docs/projects/openhop-repeater/Development.md:1-3` | Substantive contributor overview; sensor extension detail is delegated upstream at lines 80-88. |
| `/projects/openhop-repeater/first-boot/` | First Boot | `src/content/docs/projects/openhop-repeater/First-Boot.md:1-3` | Substantive first-run checklist. |
| `/projects/openhop-repeater/hardware-setup/` | Hardware Setup | `src/content/docs/projects/openhop-repeater/Hardware-Setup.md:1-3` | Substantive guide. |
| `/projects/openhop-repeater/identity-management/` | Identity Management | `src/content/docs/projects/openhop-repeater/Identity-Management.md:1-3` | Substantive guide. |
| `/projects/openhop-repeater/installation/` | Installation | `src/content/docs/projects/openhop-repeater/Installation.md:1-3` | Main, detailed install/upgrade/deployment guide. |
| `/projects/openhop-repeater/kiss-setup/` | KISS Setup | `src/content/docs/projects/openhop-repeater/KISS-Setup.md:1-3` | Substantive transport guide. |
| `/projects/openhop-repeater/network-planning/` | Network Planning | `src/content/docs/projects/openhop-repeater/Network-Planning.md:1-3` | Focused operational guide. |
| `/projects/openhop-repeater/performance-tuning/` | Performance Tuning | `src/content/docs/projects/openhop-repeater/Performance-Tuning.md:1-3` | Focused operational guide. |
| `/projects/openhop-repeater/transport-keys/` | Transport Keys | `src/content/docs/projects/openhop-repeater/Transport-Keys.md:1-3` | Focused scope/key guide. |
| `/projects/openhop-repeater/troubleshooting/` | Troubleshooting | `src/content/docs/projects/openhop-repeater/Troubleshooting.md:1-3` | Substantive diagnostic guide. |
| `/projects/openhop-repeater/web-dashboard/` | Web Dashboard | `src/content/docs/projects/openhop-repeater/Web-Dashboard.md:1-3` | Dashboard overview, not a complete feature reference. |
| `/projects/openhop-repeater/changelog/` | Changelog | `src/content/docs/projects/openhop-repeater/changelog.md:1-4` | **Placeholder/thin:** only 12 lines, lacks a description, and explicitly calls itself a placeholder (`changelog.md:7-12`). |
| `/projects/openhop-repeater/config-file/` | Configuration Reference | `src/content/docs/projects/openhop-repeater/config-file.md:1-3` | Substantive 851-line reference. Route/title mismatch is understandable but weakens title-derived URL discoverability; preserve as canonical if links already exist. |
| `/projects/openhop-repeater/docker/` | Docker Deployment | `src/content/docs/projects/openhop-repeater/docker.md:1-3` | Substantive deployment guide. |
| `/projects/openhop-repeater/home/` | Documentation Home | `src/content/docs/projects/openhop-repeater/home.md:1-3` | **IA mismatch/duplication:** a second “home” beneath the canonical project index. It repeats start links and feature summaries (`home.md:8-49`) and is ordered last (`home.md:4-5`). |
| `/projects/openhop-repeater/letsmesh-integration/` | MQTT and LetsMesh Integration | `src/content/docs/projects/openhop-repeater/letsmesh-integration.md:1-3` | Route names only LetsMesh although title/content cover MQTT too. Consider retaining the route and adding an alias only if redirect support is introduced. |
| `/projects/openhop-repeater/openhop-usb-and-tcp-setup/` | openHop USB/TCP Setup | `src/content/docs/projects/openhop-repeater/openhop-usb-and-tcp-setup.md:1-3` | Substantive modem transport guide. |
| `/projects/openhop-repeater/security-and-authentication/` | Security and Authentication | `src/content/docs/projects/openhop-repeater/security-and-authentication.md:1-3` | General 71-line security page; currently documents JWT/API tokens but not OIDC/Authentik (`security-and-authentication.md:21-29`). |
| `/projects/openhop-repeater/setup/` | openHop Repeater Setup | `src/content/docs/projects/openhop-repeater/setup.md:1-3` | **Thin/overlapping:** 55-line quick install that immediately points readers to the much fuller Installation page (`setup.md:16-22,48-55`). Distinguish as “quick install” or consolidate. |
| `/projects/openhop-repeater/what-is-openhop-repeater/` | What is openHop Repeater? | `src/content/docs/projects/openhop-repeater/what-is-openhop-repeater.md:1-3` | Substantive first-user overview. |

### openHop Core

| Canonical article route | Page title | Source evidence | Coverage/IA note |
| --- | --- | --- | --- |
| `/projects/openhop-core/` | openHop Core Overview | `src/content/docs/projects/openhop-core/index.md:1-3` | Canonical project landing page; only 34 lines and delegates API/examples upstream (`index.md:17-28`). |
| `/projects/openhop-core/architecture-and-transports/` | Architecture and Transports | `src/content/docs/projects/openhop-core/architecture-and-transports.md:1-3` | Substantive architecture overview, not an API reference. |
| `/projects/openhop-core/companion-applications/` | Companion Applications | `src/content/docs/projects/openhop-core/companion-applications.md:1-3` | Useful high-level guide, but explicitly delegates the evolving full API upstream (`companion-applications.md:85-89`). |
| `/projects/openhop-core/development/` | Core Development | `src/content/docs/projects/openhop-core/development.md:1-3` | Contributor workflow; explicitly says detailed MkDocs API material remains in source (`development.md:63-65`). |
| `/projects/openhop-core/quick-start/` | openHop Core Quick Start | `src/content/docs/projects/openhop-core/quick-start.md:1-3` | Safe install/lifecycle introduction; links examples upstream rather than documenting them (`quick-start.md:98-103`). |

## Placeholder, thin-page, and route/title findings

1. **Only one literal placeholder:** Repeater Changelog. It has no frontmatter description and says it is a placeholder (`src/content/docs/projects/openhop-repeater/changelog.md:1-12`).
2. **Duplicate Repeater entry points:** the actual project index is `/projects/openhop-repeater/`, while a separate page titled “Documentation Home” is published at `/home/` (`index.md:1-3`; `home.md:1-15`). The latter is an information-architecture mismatch rather than missing content.
3. **Setup versus Installation overlap:** `/setup/` is a thin source-install path and links to `/installation/` (`setup.md:16-22,48-55`), while Installation is the comprehensive 207-line guide (`Installation.md:1-8,22-40`).
4. **Filename/route casing is legacy but output is lowercase:** capitalized Repeater filenames such as `API-Reference.mdx`, `First-Boot.md`, and `Web-Dashboard.md` publish at lowercase routes. The checked-out sitemap records lowercase paths (`dist/sitemap-0.xml:1`).
5. **Title-derived route mismatches:** `/config-file/` is titled “Configuration Reference”; `/letsmesh-integration/` is titled “MQTT and LetsMesh Integration”; `/home/` is titled “Documentation Home.” These are not broken routes, but links should use the canonical paths in the inventory.
6. **Core is intentionally shallow:** central Core has five articles and openly delegates detailed API/examples to the source tree (`openhop-core/index.md:17-28`; `openhop-core/development.md:63-65`). This is the largest coverage difference between source and docs.openhop.dev.
7. **No tracked aliases/redirects:** neither the page frontmatter nor `astro.config.mjs` defines compatibility paths; navigation is directory-autogenerated (`astro.config.mjs:73-84`). Any legacy-link migration needs explicit redirect infrastructure or direct source-link updates.

## Legacy documentation URL mapping

These URLs are present in the current `openhop_core` README. No equivalent old documentation-host URLs were found in the current Repeater README; its support section points to repository/community resources instead (`openhop_repeater/README.md:599-626`).

| Legacy/source URL | Evidence | Best current/proposed destination | HTTP result |
| --- | --- | --- | --- |
| `https://pymc-dev.github.io/openhop-core/` | Badge and docs links at `openhop_core/README.md:3,11-18,178-181` | `https://docs.openhop.dev/projects/openhop-core/` | Not checked (runtime denied probe) |
| `https://rightup.github.io/openhop-core/` (visible link text; href actually points to the `pymc-dev` host) | `openhop_core/README.md:13` | `https://docs.openhop.dev/projects/openhop-core/` | Not checked |
| `https://pymc-dev.github.io/openhop-core/node/` | `openhop_core/README.md:15-16` | Proposed `https://docs.openhop.dev/projects/openhop-core/node-usage/` | Not checked |
| `https://pymc-dev.github.io/openhop-core/examples/` | `openhop_core/README.md:17,74` | Proposed `https://docs.openhop.dev/projects/openhop-core/examples/` | Not checked |
| `https://pymc-dev.github.io/openhop-core/api/` | `openhop_core/README.md:18` | Proposed `https://docs.openhop.dev/projects/openhop-core/api-reference/` | Not checked |
| `https://pymc-dev.github.io/openhop-core/contributing/` | `openhop_core/README.md:150-152` | `https://docs.openhop.dev/projects/openhop-core/development/` for Core-specific work; `https://docs.openhop.dev/contributing/` for central-site authoring | Not checked |

Important mapping caution: the old Core pages contain stale or unsafe examples in places (for example, a blocking `await node.start()` followed by unreachable return at `openhop_core/docs/docs/node.md:226-253`, and direct RF examples with region-specific values). Migrate topics after source validation; do not copy the old MkDocs pages verbatim.

## Prioritized central coverage gaps

All proposed article routes are lowercase and hyphenated.

| Priority | Missing/thin topic | Source evidence versus central coverage | Proposed central article route | Recommendation |
| --- | --- | --- | --- | --- |
| P0 | Repeater Authentik/OIDC setup, reverse-proxy boundary, recovery, and token/backups behavior | Source has a dedicated 169-line guide covering provider setup and group claims (`openhop_repeater/docs/authentik-oidc.md:1-29`), safe mixed-mode rollout/recovery (`:29-85`), proxy trust (`:87-134`), and secrets/backups (`:136-169`). Current central security lists only JWT/API-token/WebSocket methods (`openHop_docs/src/content/docs/projects/openhop-repeater/security-and-authentication.md:21-29`). | `/projects/openhop-repeater/authentik-oidc/` | Add a safety-first operator page, then cross-link it from Security, Configuration Reference, and Web Dashboard. Preserve local recovery and `include_secrets` warnings. |
| P1 | Core practical examples | Source documents six executable examples, radio choices, and shared helpers (`openhop_core/docs/docs/examples.md:1-49`) plus advert/trace behavior (`:50-72`). Central Quick Start only links to upstream examples and warns they may transmit (`openHop_docs/src/content/docs/projects/openhop-core/quick-start.md:98-103`). | `/projects/openhop-core/examples/` | Curate validated no-radio or explicitly transmit-labeled examples; avoid copying stale pin/frequency assumptions. This also gives the legacy `/examples/` link a clear destination. |
| P1 | Core node usage and messaging lifecycle | Source has a 480-line MeshNode guide with creation, direct/flood/channel messaging, telemetry, repeater login/commands, diagnostics, and events (`openhop_core/docs/docs/node.md:226-337`). Central coverage is lifecycle-level only (`openHop_docs/src/content/docs/projects/openhop-core/quick-start.md:56-88`). | `/projects/openhop-core/node-usage/` | Write a corrected application guide centered on current async lifecycle, ownership, handlers, and safe transport setup; map the legacy `/node/` link here. |
| P1 | Core API reference/index | Source has module references for MeshNode, Packet, LocalIdentity, PacketBuilder/Filter, hardware backends, and constants (`openhop_core/docs/docs/api/core.md:1-82`), plus protocol/crypto/identity modules (`docs/docs/api/protocol.md:1-67`) and separate node/dispatcher pages. Central Core has no API article and explicitly delegates it (`openHop_docs/src/content/docs/projects/openhop-core/development.md:63-65`). | `/projects/openhop-core/api-reference/` | Add a stable API landing/index page with version/source links. If generated API cannot be hosted centrally, explain the contract and link exact source modules rather than claiming “complete” docs. |
| P1 | Core CompanionFrameServer command/protocol reference | Source enumerates commands and wire behavior (`openhop_core/docs/docs/companion.md:586-646`), push responses (`:646-679`), and persistence hooks (`:748-776`). Central Companion Applications gives only class choice/lifecycle and delegates the full API (`openHop_docs/src/content/docs/projects/openhop-core/companion-applications.md:78-89`). | `/projects/openhop-core/companion-frame-server/` | Split stable operator/protocol material from the already-good high-level companion page; include auth/exposure and persistence limits. |
| P1 | Repeater backup, restore, and secret-aware export/import | Source distinguishes redacted normal exports from full-secret backups (`openhop_repeater/README.md:275-303`; `docs/authentik-oidc.md:157-163`). Central security only recommends filesystem backup and generic encrypted storage (`openHop_docs/src/content/docs/projects/openhop-repeater/security-and-authentication.md:60-65`). | `/projects/openhop-repeater/backup-and-restore/` | Document redacted export versus authenticated full-secret restore artifacts, paired config/state/identity recovery, permissions, and off-air validation. |
| P2 | Repeater policy engine operations | Source exposes a web policy engine and an example drop rule (`openhop_repeater/README.md:305-313`). Central only summarizes policies (`openHop_docs/src/content/docs/projects/openhop-repeater/what-is-openhop-repeater.md:41-45`) and dashboard policy management (`Web-Dashboard.md:22-30`). | `/projects/openhop-repeater/policy-engine/` | Add rule model, ordering/evaluation, dry-run/rollback, backup, and safe examples after validating implementation/tests. Do not confuse it with transport-key flood policy. |
| P2 | Repeater sensor plug-in contributor guide | Source has discovery architecture (`openhop_repeater/docs/adding_sensors.md:1-15`), implementation rules (`:19-100`), test expectations (`:116-148`), and a checklist (`:152-171`). Central Development compresses this to six lines and delegates upstream (`openHop_docs/src/content/docs/projects/openhop-repeater/Development.md:80-88`). | `/projects/openhop-repeater/adding-sensor-plugins/` | Add only if central docs are intended to host contributor detail; otherwise keep the upstream link but make the boundary explicit. |
| P2 | Core companion use cases and persistence | Source provides chat, sensor gateway, repeater bridge, frame server, diagnostics, and group-chat patterns (`openhop_core/docs/docs/companion.md:780-901`) and explicit no-op persistence hooks (`:748-776`). Central mentions persistence limits but has one minimal lifecycle example (`openHop_docs/src/content/docs/projects/openhop-core/companion-applications.md:37-76`). | `/projects/openhop-core/companion-recipes/` | Curate a small set of current, safe recipes; retain the existing page as the conceptual entry point. |
| P3 | Repeater uninstall/removal | Source has an explicit Uninstallation section (`openhop_repeater/README.md:449-463`); no central Repeater page/section is dedicated to removal in the route inventory. | `/projects/openhop-repeater/uninstallation/` | Add only after defining data-retention and backup behavior; alternatively place a concise removal section in Installation to avoid another small page. |
| P3 | Repeater changelog | Central page is explicitly a placeholder (`openHop_docs/src/content/docs/projects/openhop-repeater/changelog.md:7-12`). | `/projects/openhop-repeater/changelog/` (existing) | Either populate from releases with a documented ownership/update process or remove the placeholder from navigation and link Releases directly. |

## Recommended link-audit decisions

1. Treat the central routes in the inventory as canonical. Do not invent `/node/`, `/examples/`, or `/api/` destinations under Core until the corresponding pages exist.
2. Update Core source links away from the old GitHub Pages hosts only when each destination exists. The project root and development destinations exist now; node/examples/API require new articles or an explicit temporary repository-source target.
3. If compatibility redirects are desired, add them deliberately and test them; the repo currently has no redirect/alias mechanism. Candidate old-path mappings are `/projects/openhop-core/node/` → `/projects/openhop-core/node-usage/` and `/projects/openhop-core/api/` → `/projects/openhop-core/api-reference/`.
4. Consolidate or rename the intent of Repeater `/home/`, `/setup/`, and `/installation/` before adding more landing/setup pages.
5. Prioritize the OIDC and backup/restore gaps because the inspected Repeater branch already exposes those behaviors and incorrect partial documentation can lock out operators or mishandle secrets.

## Final integrity verification

- `openHop_docs` remained on `audit/legacy-doc-links-2026-08-11` at `17d0fe7a97aab64303942c8eaaf048af1b1cabf7`; `git diff --check` passed. Final status showed the untracked `audits/` directory.
- This agent created/modified only `audits/legacy-doc-links-2026-08-11/docs-coverage-agent.md`.
- `repeater-agent.md` and `core-agent.md` appeared in the same audit directory during this run as concurrent agents' distinct outputs; they were not read, edited, or removed by this agent.
- `openhop_repeater` remained clean on `feat/authentik-oidc` at `0975c4b63916bf88ee60b6bdc3514ba106136570`.
- `openhop_core` remained clean on `fix/modem-cad-symbol-count` at `0e69673ca549a31e5fdbb762c337d4bb847620d8`.
