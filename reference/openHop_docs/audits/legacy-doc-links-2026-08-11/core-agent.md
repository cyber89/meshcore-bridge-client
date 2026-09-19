# openHop Core legacy documentation-link audit

- **Audit date:** 2026-08-11
- **Source repository:** `/home/yellowcooln/openhop-dev/openhop_core`
- **Immutable target:** `0d1dbf2c10c23be07d4a3c529eee05414994b499` (`origin/dev`)
- **Output repository/branch:** `/home/yellowcooln/openhop-dev/openHop_docs`, `audit/legacy-doc-links-2026-08-11`

## Executive summary

The target contains **16 deduplicated remediation findings covering 24 link occurrences**. The most visible problem is the root README: nine documentation-link occurrences still use the retired `pymc-dev.github.io` site, including generic home-page links where a task-specific article should be used. Package metadata and the legacy MkDocs configuration also advertise obsolete `rightup.github.io` URLs. The old in-repository MkDocs pages contain relative links that are not routes on the consolidated documentation site, plus several external wiki/GitHub pages acting as documentation.

No source files were edited. This report is the only output written.

## Method and coverage

1. Recorded branch, HEAD, `origin/dev`, status, unstaged diff summary, and staged diff summary in both repositories.
2. Enumerated the immutable tree with `git ls-tree -r --name-only 0d1dbf…`: **188 tracked files**.
3. Enumerated non-empty text blobs with `git grep -Il -e '' 0d1dbf…`: **185 files**. The remaining tracked entries were two PNGs (`docs/docs/images/PyMC.png`, `docs/docs/images/openhop_transparent_trim.png`) and an empty Python file (`tests/hardware/__init__.py`). Thus every tracked text file was covered without switching or checking out the source worktree.
4. Searched the immutable ref, not the checked-out files, for HTTP(S) URLs, Markdown links, `docs`, `documentation`, `README`, `wiki`, GitHub `blob`/`tree`, relative `.md` targets, anchors, and placeholder terms. Reviewed every resulting candidate in surrounding source context.
5. Compared candidates with the consolidated docs worktree and its five current Core articles: `/projects/openhop-core/`, `quick-start/`, `architecture-and-transports/`, `companion-applications/`, and `development/`, plus the site-level `/contributing/` article.
6. Deduplicated repeated destinations by remediation intent while retaining every exact `path:line` occurrence below.

### HTTP checking limitation

An HTTP status sweep was attempted for the legacy URLs and proposed existing routes, but execution approval was denied. It was not retried or bypassed. Consequently this report records HTTP status as **not checked**. This does not weaken the central conclusion: even an HTTP 200 would not make a retired project domain, a generic account/wiki page, or a source-tree page the correct consolidated documentation article.

## Deduplicated findings

### CORE-01 — High — generic legacy documentation home page in README (3 occurrences)

- **Sources:**
  - `README.md:3` — Documentation badge target
  - `README.md:13` — “Complete documentation is available at”; visible label is the different stale URL `https://rightup.github.io/openhop-core/`
  - `README.md:180` — Support list “Documentation”
- **Current target:** `https://pymc-dev.github.io/openhop-core/`
- **Why inadequate:** Retired pyMC-branded GitHub Pages host; generic home page rather than the specific consolidated Core overview. Line 13 also presents one obsolete domain while linking to another, which is especially misleading.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/`
- **HTTP status:** Not checked (see limitation above).

### CORE-02 — High — legacy Node Usage Guide

- **Source:** `README.md:16`
- **Context:** “Node Usage Guide — Guide for using MeshNode”
- **Current target:** `https://pymc-dev.github.io/openhop-core/node/`
- **Why inadequate:** Retired GitHub Pages route. The consolidated Quick Start already documents the safe `MeshNode.start()` lifecycle and links onward to the architecture material.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/quick-start/`
- **Source material for future expansion:** `docs/docs/node.md`, current `MeshNode` implementation/tests, and the lifecycle cautions already in the consolidated Quick Start.

### CORE-03 — High — legacy Examples route (2 occurrences)

- **Sources:**
  - `README.md:17` — Quick Links “Examples — Working code examples”
  - `README.md:74` — “For examples, see the documentation”
- **Current target:** `https://pymc-dev.github.io/openhop-core/examples/`
- **Why inadequate:** Retired site, and there is no consolidated article that explains the examples and their hardware/RF side effects.
- **Proposed article:** **openHop Core Examples and Hardware Safety** at `https://docs.openhop.dev/projects/openhop-core/examples/`
- **Source material needed:** `docs/docs/examples.md`, `examples/README.md`, every tracked file under `examples/`, the current transport constructors, and the safety notes in the consolidated Quick Start/Architecture articles. Validate examples against current APIs before migrating snippets.

### CORE-04 — High — legacy API Reference route

- **Source:** `README.md:18`
- **Context:** “API Reference — Detailed API documentation”
- **Current target:** `https://pymc-dev.github.io/openhop-core/api/`
- **Why inadequate:** Retired site; the consolidated Core section has no API-reference article.
- **Proposed article:** **openHop Core API Reference** at `https://docs.openhop.dev/projects/openhop-core/api-reference/`
- **Source material needed:** `docs/docs/api/core.md`, `api/node.md`, `api/dispatcher.md`, `api/protocol.md`, `docs/docs/companion.md`, current public exports/docstrings, and tests. Generated API content should be pinned to a release or clearly marked as tracking `dev`.

### CORE-05 — High — legacy contributing guide

- **Source:** `README.md:152`
- **Context:** “Please see our contributing guide”
- **Current target:** `https://pymc-dev.github.io/openhop-core/contributing/`
- **Why inadequate:** Retired project Pages route. A current project-specific development article exists on the consolidated site.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/development/`

### CORE-06 — High — stale package metadata Documentation URL

- **Source:** `pyproject.toml:70`
- **Context:** `[project.urls]` key `Documentation`
- **Current target:** `https://rightup.github.io/pymc_dev/openhop-core`
- **Why inadequate:** Obsolete owner/brand and malformed legacy path; package indexes expose this as the canonical documentation link.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/`

### CORE-07 — High — stale MkDocs canonical site URL

- **Source:** `docs/mkdocs.yml:11`
- **Context:** `site_url`
- **Current target:** `https://rightup.github.io/openhop-core/`
- **Why inadequate:** The legacy build identifies an obsolete GitHub Pages deployment as canonical, which can generate incorrect canonical/search links even if the page content is later reused.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/` if this MkDocs tree is retained as a Core subsection; preferably retire its independent deployment and migrate maintained material into the consolidated docs repository.

### CORE-08 — Medium — relative API link in the legacy docs index

- **Source:** `docs/docs/index.md:130`
- **Context:** “API Reference — API documentation”
- **Current target:** `api/core.md`
- **Why inadequate:** A source-relative MkDocs path, not a stable consolidated public article; it also covers only one of several API pages.
- **Replacement:** Proposed `https://docs.openhop.dev/projects/openhop-core/api-reference/` (CORE-04).

### CORE-09 — Medium — relative Examples link in the legacy docs index

- **Source:** `docs/docs/index.md:131`
- **Context:** “Examples — Code examples and tutorials”
- **Current target:** `examples.md`
- **Why inadequate:** Source-relative path from the superseded MkDocs tree, not a consolidated docs route.
- **Replacement:** Proposed `https://docs.openhop.dev/projects/openhop-core/examples/` (CORE-03).

### CORE-10 — Medium — relative Contributing link in the legacy docs index

- **Source:** `docs/docs/index.md:132`
- **Context:** “Contributing — How to contribute to the project”
- **Current target:** `contributing.md`
- **Why inadequate:** Source-relative legacy docs path; the consolidated project development article is the maintained destination.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-core/development/`

### CORE-11 — Medium — relative node API reference

- **Source:** `docs/docs/node.md:480`
- **Context:** “For detailed API documentation, refer to the API Reference”
- **Current target:** `api/node.md`
- **Why inadequate:** Source-relative legacy MkDocs path with no equivalent consolidated route.
- **Replacement:** Proposed `https://docs.openhop.dev/projects/openhop-core/api-reference/#meshnode` (CORE-04; anchor should be created with the article).

### CORE-12 — Medium — KISS protocol documentation is a mutable GitHub blob

- **Source:** `src/openhop_core/hardware/kiss_modem_wrapper.py:8`
- **Context:** Module-level implementation note pointing readers to the KISS modem protocol
- **Current target:** `https://github.com/meshcore-dev/MeshCore/blob/dev/docs/kiss_modem_protocol.md`
- **Why inadequate:** Clearly used as developer protocol documentation, but points to a mutable `dev` blob outside the OpenHop docs information architecture. It can drift independently from this implementation.
- **Proposed article:** **MeshCore KISS Modem Protocol Compatibility** at `https://docs.openhop.dev/projects/openhop-core/kiss-modem-protocol/`
- **Source material needed:** the upstream MeshCore protocol document at a reviewed commit, this wrapper and its protocol constants, KISS tests, supported deviations/extensions, and an explicit upstream-version/commit note. Keep a pinned upstream source citation in the article.

### CORE-13 — Medium — Waveshare hardware wiki used as the setup authority

- **Source:** `docs/docs/node.md:61`
- **Context:** “official documentation available at Waveshare Wiki”
- **Current target:** `https://www.waveshare.com/wiki/SX1262_XXXM_LoRaWAN/GNSS_HAT`
- **Why inadequate:** The vendor wiki is an appropriate primary citation, but it does not document OpenHop-specific constructor parameters, lifecycle, regional RF safety, or tested compatibility. It is currently serving as the only linked documentation for this setup.
- **Proposed article:** **Direct SX1262 Hardware Setup** at `https://docs.openhop.dev/projects/openhop-core/direct-sx1262-hardware/`
- **Source material needed:** relevant sections of `docs/docs/node.md`, current SX1262 wrapper/transports/tests, supported board mappings, RF-safety guidance, and the vendor wiki retained as an external citation rather than the article destination.

### CORE-14 — Medium — meshadv documentation points only to a GitHub user profile

- **Source:** `docs/docs/node.md:145`
- **Context:** “The documentation for the meshadv and meshadv Mini are available on github”
- **Current target:** `https://github.com/chrismyers2000`
- **Why inadequate:** A user profile is neither a specific document nor a stable device guide; readers must guess which repository/revision applies.
- **Replacement:** Proposed `https://docs.openhop.dev/projects/openhop-core/direct-sx1262-hardware/#meshadv-and-meshadv-mini` (CORE-13).
- **Source material needed:** exact board repositories/revisions, board schematics/pinout, current OpenHop board configuration, and hardware tests. Preserve direct, pinned upstream links as citations.

### CORE-15 — Low — vendored LoRaRF wiki pages presented as complete/operational documentation (3 occurrences)

- **Sources and current targets:**
  - `src/openhop_core/hardware/lora/README.md:10` — “complete documentation” → `https://github.com/chandrawi/LoRaRF-Python/wiki`
  - `src/openhop_core/hardware/lora/README.md:170` — transmit details → `https://github.com/chandrawi/LoRaRF-Python/wiki/Transmit-Operation`
  - `src/openhop_core/hardware/lora/README.md:187` — receive details → `https://github.com/chandrawi/LoRaRF-Python/wiki/Receive-Operation`
- **Why inadequate:** These are mutable wiki pages for the upstream dependency and may not match OpenHop's vendored/forked code. They are explicitly presented as documentation, so they meet the audit criterion despite being dependency material.
- **Proposed replacement:** `https://docs.openhop.dev/projects/openhop-core/direct-sx1262-hardware/#vendored-lorarf-notes`
- **Source material needed:** exact vendored provenance/version, local modifications, supported methods, and current hardware tests. The upstream wiki should remain cited for provenance; do not silently rewrite the vendored README without an ownership decision.

### CORE-16 — Low — vendored LoRaRF examples use mutable GitHub tree pages (3 targets on one line)

- **Source:** `src/openhop_core/hardware/lora/README.md:191`
- **Context/targets:** “SX126x”, “SX127x”, and “simple network implementation” example links to, respectively:
  - `https://github.com/chandrawi/LoRaRF-Python/tree/main/examples/SX126x`
  - `https://github.com/chandrawi/LoRaRF-Python/tree/main/examples/SX127x`
  - `https://github.com/chandrawi/LoRaRF-Python/tree/main/examples/network`
- **Why inadequate:** Mutable upstream source-tree pages are acting as user examples and can diverge from the vendored implementation. They are not OpenHop-specific and omit this repository's hardware/RF cautions.
- **Proposed replacement:** `https://docs.openhop.dev/projects/openhop-core/direct-sx1262-hardware/#low-level-lorarf-examples`
- **Source material needed:** reviewed/pinned upstream examples, locally supported API differences, relevant vendored code, and hardware-safety review.

## Uncertain cases and exclusions

- **Vendored dependency ownership (CORE-15/16):** These are included as low-severity findings because their labels explicitly make them documentation/examples. However, the file appears vendored from LoRaRF. The remediation may belong in a central OpenHop article while leaving the vendored file byte-for-byte upstream-compatible. Confirm vendoring policy before any source change.
- **Vendor documentation (CORE-13):** The Waveshare wiki should remain an authoritative external citation. The issue is that it is the only linked setup authority, not that vendor documentation is inherently invalid.
- **No-link API prose:** `docs/docs/node.md:300` says to refer to API documentation but contains no actual URL/target. It is a documentation-content gap, not a link finding, so it was not counted.
- **Placeholder search:** `docs/docs/examples.md:72` mentions a placeholder repeater hash inside example guidance, not a placeholder URL, so it was not counted.
- **Ordinary exclusions applied:** Source repositories, PyPI, licenses, issues/discussions, Discord/community links, API endpoints, badges/images, dependency pins, and upstream acknowledgements were not flagged unless the surrounding text explicitly presented the target as documentation or examples.
- **No README-anchor findings:** The immutable ref had no Markdown documentation links to README section anchors.

## Recommended remediation order

1. Replace README and package-metadata destinations (CORE-01 through CORE-06).
2. Decide whether the old MkDocs deployment is retired or retained, then correct canonical configuration and relative navigation (CORE-07 through CORE-11).
3. Publish version-aware API, examples, direct-SX1262, and KISS compatibility articles before replacing destinations that currently have no adequate consolidated equivalent (CORE-03/04/12–16).
4. Preserve pinned upstream citations and vendored provenance; do not turn OpenHop docs into an unversioned copy of mutable upstream wikis.

## Source integrity

### Before audit

- Source worktree branch: `fix/modem-cad-symbol-count`
- Source worktree HEAD: `0e69673ca549a31e5fdbb762c337d4bb847620d8`
- `origin/dev`: `0d1dbf2c10c23be07d4a3c529eee05414994b499` (exact requested target)
- Source status: clean (`## fix/modem-cad-symbol-count...yellowcooln/fix/modem-cad-symbol-count`)
- Docs worktree branch: `audit/legacy-doc-links-2026-08-11`
- Docs worktree HEAD: `17d0fe7a97aab64303942c8eaaf048af1b1cabf7`
- Docs status: clean (`## audit/legacy-doc-links-2026-08-11...origin/dev`)

### After audit

- Source worktree branch/HEAD remained `fix/modem-cad-symbol-count` at `0e69673ca549a31e5fdbb762c337d4bb847620d8`; `origin/dev` remained the requested `0d1dbf2c10c23be07d4a3c529eee05414994b499`.
- Source status remained clean and unchanged (`## fix/modem-cad-symbol-count...yellowcooln/fix/modem-cad-symbol-count`). No checkout, switch, or source edit occurred.
- Docs worktree remained on `audit/legacy-doc-links-2026-08-11` at `17d0fe7a97aab64303942c8eaaf048af1b1cabf7`.
- Docs status showed this newly created report plus a concurrently created sibling-agent report: `?? audits/legacy-doc-links-2026-08-11/core-agent.md` and `?? audits/legacy-doc-links-2026-08-11/repeater-agent.md`. This audit did not read or modify the sibling report.
- `git diff --no-index --check /dev/null audits/legacy-doc-links-2026-08-11/core-agent.md` completed successfully, validating the untracked report for whitespace errors.
