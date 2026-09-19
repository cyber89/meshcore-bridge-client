# openHop legacy documentation-link audit — master report

Audit date: 2026-08-11
Status: audit complete; required central documentation implemented locally, source-link changes still pending
Docs audit branch: `audit/legacy-doc-links-2026-08-11`
Docs implementation branch: `docs/legacy-link-migration`

## Scope and immutable baselines

| Repository | Audited ref | Commit | Worktree handling |
| --- | --- | --- | --- |
| `openhop_repeater` | upstream `origin/dev` | `d57baabf2e5069a2461b290a6586a3f57cafb20f` | Read through Git objects; active `feat/authentik-oidc` worktree was not switched or edited |
| `openhop_core` | upstream `origin/dev` | `0d1dbf2c10c23be07d4a3c529eee05414994b499` | Read through Git objects; active `fix/modem-cad-symbol-count` worktree was not switched or edited |
| `openHop_docs` | `origin/dev` audit base | `17d0fe7a97aab64303942c8eaaf048af1b1cabf7` | New local audit branch; only Markdown audit artifacts added |

Three independent agents audited Repeater, Core, and central Docs coverage. The parent pass independently extracted links/routes, checked the highest-priority source evidence against the immutable refs, resolved the generated Repeater link to its RepeaterUI source, and ran live HTTP checks.

Agent reports:

- `repeater-agent.md`
- `core-agent.md`
- `docs-coverage-agent.md`

## Executive result

The audit found two different situations:

1. **openHop Core has a broad legacy-site problem.** Its upstream `dev` README, package metadata, and old MkDocs configuration still advertise retired `pymc-dev.github.io` and `rightup.github.io` documentation. Every tested legacy Core Pages URL returned HTTP 404. Several destinations cannot be replaced correctly until missing Core articles exist on `docs.openhop.dev`.
2. **openHop Repeater has a smaller but visible navigation problem.** Its in-product Help page points to a nonexistent GitHub Wiki, its upgrade output contains an unlinked CH341 documentation placeholder, and its README still acts as the main documentation menu. Most Repeater README topics already have central articles; uninstallation is the main missing destination.

Agent totals before parent reconciliation:

- Repeater: 3 deduplicated findings covering 13 occurrences.
- Core: 16 deduplicated findings covering 24 occurrences.

The master plan below separates hard-broken links, migration work, required new articles, optional coverage improvements, and findings that should not be folded into this exact-ref audit.

## Live HTTP verification

The parent process checked these URLs with `curl -L`, recording the final status and destination.

### Broken legacy destinations

| URL | Final status |
| --- | --- |
| `https://pymc-dev.github.io/openhop-core/` | 404 |
| `https://pymc-dev.github.io/openhop-core/node/` | 404 |
| `https://pymc-dev.github.io/openhop-core/examples/` | 404 |
| `https://pymc-dev.github.io/openhop-core/api/` | 404 |
| `https://pymc-dev.github.io/openhop-core/contributing/` | 404 |
| `https://rightup.github.io/openhop-core/` | 404 |
| `https://rightup.github.io/pymc_dev/openhop-core` | 404 |
| `https://github.com/openhop-dev/openhop-repeater/wiki` | 404 |

### Existing central destinations

All of these returned HTTP 200:

- `https://docs.openhop.dev/projects/openhop-core/`
- `https://docs.openhop.dev/projects/openhop-core/quick-start/`
- `https://docs.openhop.dev/projects/openhop-core/architecture-and-transports/`
- `https://docs.openhop.dev/projects/openhop-core/development/`
- `https://docs.openhop.dev/projects/openhop-repeater/`
- `https://docs.openhop.dev/projects/openhop-repeater/home/`
- `https://docs.openhop.dev/projects/openhop-repeater/hardware-setup/`
- `https://docs.openhop.dev/projects/openhop-repeater/installation/`
- `https://docs.openhop.dev/projects/openhop-repeater/config-file/`
- `https://docs.openhop.dev/projects/openhop-repeater/docker/`
- `https://docs.openhop.dev/projects/openhop-repeater/development/`

A 200 only proves the route responds; the content mapping decisions below were made from repository evidence rather than status alone.

# Required source-link changes

## openHop Core

### CORE-A — Replace broken public documentation links now

These destinations already have adequate central articles and do not need new pages first.

| Source evidence at audited ref | Current destination | Replace with |
| --- | --- | --- |
| `README.md:3,13,180` | generic `pymc-dev.github.io/openhop-core/` links; line 13 visibly says `rightup.github.io` while linking elsewhere | `https://docs.openhop.dev/projects/openhop-core/` |
| `README.md:152` | retired `/contributing/` page | `https://docs.openhop.dev/projects/openhop-core/development/` |
| `pyproject.toml:70` | malformed/retired `rightup.github.io/pymc_dev/openhop-core` package Documentation URL | `https://docs.openhop.dev/projects/openhop-core/` |

Also update the documentation badge text at `README.md:3` so it no longer says “GitHub Pages.”

### CORE-B — Replace broken links only after new articles exist

| Source evidence | Current destination | Required future destination |
| --- | --- | --- |
| `README.md:16` | retired `/node/` | `https://docs.openhop.dev/projects/openhop-core/node-usage/` |
| `README.md:17,74` | retired `/examples/` | `https://docs.openhop.dev/projects/openhop-core/examples/` |
| `README.md:18` | retired `/api/` | `https://docs.openhop.dev/projects/openhop-core/api-reference/` |
| `docs/docs/index.md:130` and `docs/docs/node.md:480` | relative legacy MkDocs API pages | central API Reference route and a real `#meshnode` section/anchor |
| `docs/docs/index.md:131` | relative `examples.md` | central Examples route |

Do not temporarily point Node Usage to Quick Start and call the migration complete. Quick Start covers safe startup/lifecycle but not the old 480-line node guide’s messaging, handlers, telemetry, login, commands, and diagnostics scope.

### CORE-C — Decide the fate of the old MkDocs tree

Evidence:

- `docs/mkdocs.yml:7` still identifies `https://github.com/pyMC-dev/openhop-core`.
- `docs/mkdocs.yml:11` still declares `https://rightup.github.io/openhop-core/` as canonical.
- `docs/docs/index.md:130-132` and `docs/docs/node.md:480` use navigation that only works inside the superseded MkDocs site.

Recommended decision: treat `docs.openhop.dev` as the public canonical site, migrate maintained material, and stop advertising the independent MkDocs deployment. If the source-tree MkDocs site remains buildable for contributor/reference use, label it as source-local/reference material and prevent it from emitting an obsolete public canonical URL.

### CORE-D — Replace mutable external documentation only where openHop needs an owned compatibility guide

These should not be handled by blindly copying vendor/upstream docs.

| Source | Current external documentation | Action |
| --- | --- | --- |
| `src/openhop_core/hardware/kiss_modem_wrapper.py:8` | mutable MeshCore `dev` blob for KISS protocol | Create an openHop compatibility article, cite a reviewed/pinned upstream protocol revision, then link the implementation note to the openHop article |
| `docs/docs/node.md:61,145` | Waveshare wiki and a generic GitHub user profile for meshadv documentation | Create an openHop direct-SX1262 setup article; retain exact vendor/hardware sources as citations |
| `src/openhop_core/hardware/lora/README.md:10,170,187,191` | mutable LoRaRF wiki/tree pages | First confirm vendoring policy. Prefer central compatibility/provenance notes while keeping pinned upstream citations; do not casually rewrite vendored material |

## openHop Repeater

### REP-A — Fix the broken in-product Help link in RepeaterUI source

Audited generated occurrence:

- `openhop_repeater` `origin/dev`, `repeater/web/html/assets/Help-B2C8hXBH.js:1`
- Current destination: `https://github.com/openhop-dev/openhop-repeater/wiki`
- Live result: HTTP 404

Authoritative source occurrence:

- `openHop_RepeaterUI` `origin/dev` commit `4ef9089a186ec1adbbf6607ae89ae34736734b39`
- `src/views/Help.vue:27,35,48`

Change the source UI labels away from “Repeater Wiki” / “Visit Wiki Documentation” and use:

`https://docs.openhop.dev/projects/openhop-repeater/`

Use the canonical project index rather than `/home/`; the docs inventory found `/home/` is a duplicate secondary landing page. Do not hand-edit the generated backend asset.

### REP-B — Make the CH341 upgrade warning actionable

Evidence at the audited Repeater ref:

- `manage.sh:1366` prints: `See documentation for CH341 host-side setup.`

Replace the placeholder with:

`https://docs.openhop.dev/projects/openhop-repeater/hardware-setup/#ch341-usb-spi-hosts`

This is safety-relevant host/container guidance and the central content already exists.

### REP-C — Move README documentation navigation to central articles

The README table of contents at `README.md:15-26` currently keeps users in branch-dependent duplicate prose. Keep repository-local Roadmap, Support, Disclaimer, and License entries local. For documentation topics, use these destinations:

| README entry | Central destination |
| --- | --- |
| Overview | `/projects/openhop-repeater/what-is-openhop-repeater/` |
| Screenshots/dashboard | `/projects/openhop-repeater/web-dashboard/` |
| Supported Hardware | `/projects/openhop-repeater/hardware-setup/` |
| Installation | `/projects/openhop-repeater/installation/` |
| Configuration | `/projects/openhop-repeater/config-file/` |
| Policy Engine | `/projects/openhop-repeater/web-dashboard/` initially; use a dedicated policy route only if that page is created |
| Upgrading | `/projects/openhop-repeater/installation/#upgrading-an-older-pymc-installation` plus `/docker/` where container-specific |
| Proxmox LXC | `/projects/openhop-repeater/installation/#proxmox-lxc-with-ch341` |
| Uninstallation | New `/projects/openhop-repeater/uninstallation/` article, or a dedicated removal section in Installation |
| Docker Compose | `/projects/openhop-repeater/docker/` |
| Contributing | `/projects/openhop-repeater/development/` and site-level `/contributing/` where appropriate |

This is lower urgency than the 404 Help link and CH341 placeholder. README anchors are not externally broken URLs, but they perpetuate the old split documentation model.

# Documentation work required before source migration

## New articles required

### 1. openHop Core Node Usage

Proposed route: `/projects/openhop-core/node-usage/`

Source authority:

- current `src/openhop_core/node/` implementation and tests;
- `docs/docs/node.md` as migration input, not copy authority;
- existing central Quick Start lifecycle cautions.

Required coverage:

- correct asynchronous `MeshNode.start()` task lifecycle and caller-owned radio shutdown;
- direct, flood, and channel messaging;
- handlers/events, telemetry, login/commands, and diagnostics;
- transport selection without unsafe universal RF/pin presets;
- explicit hardware/transmit labeling.

### 2. openHop Core Examples and Hardware Safety

Proposed route: `/projects/openhop-core/examples/`

Source authority:

- current files under `examples/`;
- `docs/docs/examples.md` and `examples/README.md` only as migration inputs;
- current transport constructors/tests.

Required coverage:

- no-radio examples first where possible;
- explicit labels for device access, radio reconfiguration, and RF transmission;
- examples validated against current APIs;
- no stale board/frequency assumptions copied from old prose.

### 3. openHop Core API Reference

Proposed route: `/projects/openhop-core/api-reference/`

Source authority:

- public exports/docstrings and tests;
- legacy `docs/docs/api/core.md`, `node.md`, `dispatcher.md`, and `protocol.md` as an inventory;
- companion APIs where stable.

Required coverage:

- version or branch scope stated clearly;
- stable landing/index even if full API is generated elsewhere;
- sections/anchors for MeshNode, dispatcher, protocol, identity/crypto, packets/builders/filters, hardware transports, and companion APIs;
- do not claim completeness if central generation is not established.

### 4. MeshCore KISS Modem Protocol Compatibility

Proposed route: `/projects/openhop-core/kiss-modem-protocol/`

Required coverage:

- reviewed upstream protocol revision/commit;
- openHop wrapper behavior, constants, framing, supported deviations/extensions, and tests;
- pinned upstream citation rather than a mutable `dev` blob as the sole authority.

### 5. Direct SX1262 Hardware Setup

Proposed route: `/projects/openhop-core/direct-sx1262-hardware/`

Required coverage:

- current supported backend/board mappings and constructor parameters;
- Waveshare, meshadv/meshadv-mini, and other verified direct-SPI cases;
- GPIO numbering, TCXO/DIO2/RF-switch considerations, permissions, lifecycle, antenna, region, frequency, and TX safety;
- exact vendor/repository references retained as citations;
- vendored LoRaRF provenance/compatibility notes if ownership policy permits.

### 6. Repeater Uninstallation or a dedicated Installation section

Preferred route if standalone: `/projects/openhop-repeater/uninstallation/`

Source authority:

- audited `README.md:382-395`;
- actual `manage.sh uninstall` behavior and prompts;
- container removal behavior and persistent volume ownership.

Required coverage:

- service shutdown/disable;
- application removal versus optional config/log/data/user removal;
- backups and irreversible deletion warnings;
- native, Docker, and legacy pyMC path differences.

This can be a substantial section in the existing Installation article instead of another thin page. If kept in Installation, link directly to a stable heading.

## Existing docs to modify

| Existing article/config | Modification |
| --- | --- |
| Core project index | Stop delegating all API/examples work to the old source docs once the new articles exist; add task-specific links |
| Core Quick Start | Link to Node Usage and Examples; retain safe lifecycle introduction |
| Core Development | Explain that `docs.openhop.dev` is canonical and link the central API/reference workflow |
| Core Architecture and Transports | Cross-link Direct SX1262 and KISS compatibility articles |
| Core Companion Applications | Add API anchors or split stable frame-server detail if needed; do not leave “full API” only in legacy source docs |
| Repeater project index | Make this the single canonical Help landing page |
| Repeater `/home/` page | Consolidate into the project index or clearly distinguish it; no redirects/aliases currently exist |
| Repeater Installation | Add or link uninstallation/removal guidance |
| Repeater Hardware Setup | Confirm the CH341 heading remains stable because terminal output will deep-link to it |
| Repeater Development | Consider promoting the sensor plug-in guide only if contributor docs belong centrally |
| Repeater Changelog | Replace the placeholder with commit-based development history; Core and Repeater do not publish GitHub Releases |

# Optional coverage discovered, not required to resolve audited links

These are legitimate documentation gaps, but they are not prerequisites for replacing the broken links found at the exact upstream `dev` refs:

- Repeater Policy Engine article: `/projects/openhop-repeater/policy-engine/`
- Repeater Sensor Plug-in Development: `/projects/openhop-repeater/adding-sensor-plugins/`
- Core CompanionFrameServer reference: `/projects/openhop-core/companion-frame-server/` (**implemented locally**)
- Core companion recipes: `/projects/openhop-core/companion-recipes/` (**implemented locally**)
- Repeater backup/restore guide, after confirming the exact `origin/dev` feature set

## Explicit branch caveat: Authentik/OIDC

The coverage agent found a strong need for a Repeater Authentik/OIDC article by reading the checked-out `feat/authentik-oidc` worktree. The immutable audit target `d57baabf` does **not** contain `docs/authentik-oidc.md`; this was verified with `git cat-file`.

Therefore an Authentik/OIDC page is not counted as an upstream-`dev` link-audit requirement in this master report. It should be handled in a separate feature-branch documentation pass before that feature merges, with local-login recovery, proxy trust, group/role mapping, token behavior, secret-aware backups, and safe rollout covered explicitly.

# Recommended implementation sequence for the later change pass

1. Create and validate the five missing Core articles and Repeater removal guidance on a documentation feature branch.
2. Consolidate Repeater `/home/` versus the canonical project index before choosing the permanent in-product Help destination; recommendation is the project index.
3. Update existing Core and Repeater cross-links/navigation after the new routes exist.
4. Change Core README/package metadata and decide how the legacy MkDocs tree is retired or retained.
5. Change RepeaterUI `src/views/Help.vue`; rebuild through RepeaterUI only when an integration pass is authorized.
6. Change Repeater `manage.sh` CH341 output and README documentation navigation.
7. Add redirects only if there is a deliberate compatibility requirement; the docs repository currently defines none.
8. Build, link-check, and visually inspect the docs in a later authorized implementation pass. Do not deploy until separately approved.

# Local documentation implementation update

The authorized follow-up pass created `docs/legacy-link-migration` from the audit
base. It did not modify Core, Repeater, or RepeaterUI source links and did not commit,
push, upload, release, or deploy anything.

## Required routes implemented

- `/projects/openhop-core/node-usage/`
- `/projects/openhop-core/examples/`
- `/projects/openhop-core/api-reference/`
- `/projects/openhop-core/kiss-modem-protocol/`
- `/projects/openhop-core/direct-sx1262-hardware/`
- `/projects/openhop-repeater/uninstallation/`

The Core migration was expanded to account for every tracked file under
`openhop_core/docs/`. See `core-docs-migration-matrix.md`. Additional central pages
were created for Node/Dispatcher API, Protocol API, CompanionFrameServer, and
companion recipes so the old detailed source docs are no longer the only coverage.

## Existing pages changed locally

- Core overview, Quick Start, Architecture, Companion Applications, and Development
  now lead into the central task/API pages.
- Repeater Overview, Installation, and Documentation Directory now link removal
  guidance.
- The duplicate Repeater `/home/` route is retained for compatibility but presented
  as a directory rather than a second project home.
- The placeholder `/changelog/` route is now **Development History** and directs users
  to `dev`/`main` commit history. Core Development does the same. Neither project is
  documented as publishing GitHub Releases.

## Uninstaller discrepancy resolved

The audited README claims optional removal prompts, but `manage.sh uninstall` at
`d57baabf` performs one confirmation and then removes current and legacy application,
configuration, log, data, and service-user state. The new article documents the
script behavior, including the best-effort configuration-only backup under `/tmp`,
instead of repeating the stale README claim.

## Verification

- Canonical build: passed with Repeater OpenAPI pinned to exact audited ref
  `d57baabf2e5069a2461b290a6586a3f57cafb20f`.
- Output: 58 static HTML pages and a Pagefind search index.
- Rendered internal-link scan: 5,106 links checked; zero missing routes or anchors.
- Rendered stale-destination scan: zero retired Core GitHub Pages URLs and zero Core
  or Repeater GitHub Releases links.
- Browser inspection caught and corrected literal danger directives and a clipped
  nine-column hardware table; both corrections were rebuilt and re-inspected.

## Remaining source-repository work

The source-link changes in CORE-A through CORE-D and REP-A through REP-C remain the
next authorized phase. The central destinations now exist, but no source repository
was changed in this pass.

# Integrity and side-effect verification

At completion of this audit:

- `openhop_repeater` remained on `feat/authentik-oidc` at `0975c4b63916bf88ee60b6bdc3514ba106136570`, clean and unchanged.
- `openhop_core` remained on `fix/modem-cad-symbol-count` at `0e69673ca549a31e5fdbb762c337d4bb847620d8`, clean and unchanged.
- `openHop_RepeaterUI` remained on its existing local `dev` checkout at `229fbc363565d919e77160060ad95f454515f055`; it was only read through `origin/dev` and not changed.
- `openHop_docs` remained on `audit/legacy-doc-links-2026-08-11` at base HEAD `17d0fe7a97aab64303942c8eaaf048af1b1cabf7`.
- Only files under `audits/legacy-doc-links-2026-08-11/` were created.
- No source checkout was switched.
- No product documentation was authored or modified.
- No build, install, commit, push, PR, release, deployment, or hardware action occurred.
