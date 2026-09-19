# Legacy documentation-link audit — openHop Repeater

## Result

- **Target inspected:** `openhop_repeater` commit `d57baabf2e5069a2461b290a6586a3f57cafb20f`, the locally resolved `origin/dev` target supplied for this audit.
- **Findings:** 3 deduplicated issues covering 13 source occurrences: one obsolete GitHub Wiki link, eleven README anchors being used as the documentation navigation layer, and one user-facing documentation placeholder with no link.
- **Source changes:** none. The source ref was read with Git object commands; the source worktree was not switched or checked out.
- **Output:** this report is the only file written.

## Source integrity

| Check | Before audit | After audit |
|---|---|---|
| Source worktree branch | `feat/authentik-oidc` | `feat/authentik-oidc` |
| Source worktree HEAD | `0975c4b63916bf88ee60b6bdc3514ba106136570` | `0975c4b63916bf88ee60b6bdc3514ba106136570` |
| Requested upstream ref | `origin/dev` = `d57baabf2e5069a2461b290a6586a3f57cafb20f` | unchanged |
| Requested ref tree | `1e394c5f2df88768a85e0a70c772b52743e1fe30` | unchanged |
| Source status | clean (`git status --short` emitted no paths) | clean (`git status --short` emitted no paths) |
| Docs output worktree | branch `audit/legacy-doc-links-2026-08-11`, HEAD `17d0fe7a97aab64303942c8eaaf048af1b1cabf7`, clean | same branch/HEAD; this assigned report is untracked. Concurrent agents also created `core-agent.md` and `docs-coverage-agent.md`; both were left untouched. |

## Search method and coverage

1. Enumerated the exact target tree with `git ls-tree -r --name-only d57baabf...`; it contains **259 tracked files**.
2. Read every blob directly from the immutable target with `git show d57baabf:<path>` in memory. No source checkout, switch, archive, build, install, or source write was used.
3. UTF-8 decoded and inspected **240 tracked text files**. Text coverage by suffix was: 132 `.py`, 49 `.js`, 15 `.css`, 11 `.sh`, 7 `.yaml`, 5 `.yml`, 3 `.json`, 3 `.example`, 2 `.md`, 1 `.html`, 1 `.service`, 1 `.svg`, 1 `.toml`, and 9 extensionless files.
4. Classified 19 files as binary/non-text: 17 PNG documentation/UI images, one bundled PNG, and one favicon. These were inventoried but not text-searched.
5. Extracted and reviewed Markdown link targets, absolute HTTP(S) URLs, HTML `href`/`src` values, README anchors, relative `docs/` references, and lines mentioning documentation, guides, manuals, wikis, placeholders, or old pyMC/openHop documentation domains. Bundled/minified frontend assets were included rather than skipped.
6. Compared candidate destinations with the article routes present in the docs worktree. HTTP checks were attempted but the environment denied the outbound `curl` command, so this report does **not** claim live response status. A 200 response would not, in any case, prove that a documentation destination is appropriate.

## Findings

### F1 — Help page sends users to the obsolete repository wiki

- **Severity:** High
- **Source:** `repeater/web/html/assets/Help-B2C8hXBH.js:1`
- **Current URL:** `https://github.com/openhop-dev/openhop-repeater/wiki`
- **Label/context:** The bundled Help view is titled **“Help & Documentation”**, calls the destination **“Repeater Wiki”** and the **“official wiki”**, and labels the button **“Visit Wiki Documentation.”**
- **Why old/inadequate:** This is the application's primary in-product documentation affordance, but it points to a GitHub Wiki rather than the maintained central docs. Even if GitHub returns a valid page or redirect, the URL encodes the retired documentation location and bypasses the product's current article structure.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-repeater/home/` (**Documentation Home**). This article is the appropriate broad landing article because the Help view promises setup, troubleshooting, and other resources rather than one narrow task.
- **Implementation note:** The audited path is a tracked generated frontend bundle. The correction should be made in the standalone RepeaterUI source and then rebuilt/synchronized; do not hand-edit this minified backend asset.

### F2 — README anchors are serving as the user/developer documentation navigation

- **Severity:** Medium overall (low discoverability debt for most entries; medium for the missing uninstallation article)
- **Source/context:** `README.md:13-29`, the **Contents** list. The entries below point back into the repository README instead of to specific maintained `docs.openhop.dev` articles.
- **Why old/inadequate:** The README duplicates substantial operational documentation and its table of contents keeps users inside branch-dependent repository prose. Existing central articles are more focused and can evolve independently of a source checkout. This is the explicit “README anchors used as docs” pattern. Legal/project metadata entries (`Roadmap`, `Support`, `Disclaimer`, and `License`) are not included because they are appropriately repository-local or excluded by scope.

| Severity | Exact source | Current target | Label/context | Replacement |
|---|---|---|---|---|
| Low | `README.md:15` | `#overview` | “Overview” | `https://docs.openhop.dev/projects/openhop-repeater/what-is-openhop-repeater/` |
| Low | `README.md:16` | `#screenshots` | “Screenshots” leading to dashboard/statistics descriptions | `https://docs.openhop.dev/projects/openhop-repeater/web-dashboard/` |
| Low | `README.md:17` | `#supported-hardware` | “Supported Hardware” | `https://docs.openhop.dev/projects/openhop-repeater/hardware-setup/` |
| Low | `README.md:18` | `#installation` | “Installation” | `https://docs.openhop.dev/projects/openhop-repeater/installation/` |
| Low | `README.md:19` | `#configuration` | “Configuration” | `https://docs.openhop.dev/projects/openhop-repeater/config-file/` |
| Low | `README.md:20` | `#policy-engine` | “Policy Engine”; the current README section describes dashboard policy management | `https://docs.openhop.dev/projects/openhop-repeater/web-dashboard/` (currently covers policy management; create a dedicated policy article later if the subject is expanded) |
| Low | `README.md:21` | `#upgrading` | “Upgrading” | `https://docs.openhop.dev/projects/openhop-repeater/installation/#upgrading-an-older-pymc-installation`; Docker-specific updates are also covered by `/projects/openhop-repeater/docker/` |
| Low | `README.md:22` | `#proxmox-lxc-installation` | “Proxmox LXC Installation” | `https://docs.openhop.dev/projects/openhop-repeater/installation/#proxmox-lxc-with-ch341` |
| Medium | `README.md:23` | `#uninstallation` | “Uninstallation” | **No dedicated current article found.** Proposed article: **Uninstall openHop Repeater**, route `https://docs.openhop.dev/projects/openhop-repeater/uninstallation/`. Source material: `README.md:382-395` at the audited ref plus the `uninstall` implementation and prompts in `manage.sh`; cover service shutdown, optional config/log/state/user removal, backup warnings, native-vs-container removal, and legacy pyMC paths. |
| Low | `README.md:24` | `#docker-compose` | “Docker Compose” | `https://docs.openhop.dev/projects/openhop-repeater/docker/` |
| Low | `README.md:26` | `#contributing` | “Contributing” / development setup | `https://docs.openhop.dev/projects/openhop-repeater/development/` for repository-specific development, with `https://docs.openhop.dev/contributing/` for the general contribution process |

### F3 — Upgrade output says “See documentation” but provides no destination

- **Severity:** Medium
- **Source:** `manage.sh:1366`
- **Current target:** none; literal user-facing text is `See documentation for CH341 host-side setup.`
- **Label/context:** A container-detection note shown after upgrade warns that USB udev rules must be configured on the host.
- **Why old/inadequate:** This is a documentation placeholder in a safety-relevant hardware/container warning. A user reading terminal output has no actionable URL, and searching the README can land on branch-dependent or incomplete instructions.
- **Replacement:** `https://docs.openhop.dev/projects/openhop-repeater/hardware-setup/#ch341-usb-spi-hosts`. The existing Hardware Setup article covers CH341 hosts and host USB permissions. If terminal wrapping is a concern, print the URL on its own line.

## Deduplication and uncertain/excluded cases

- The eleven README entries are reported as one systemic finding with per-line remediation rather than eleven repetitive top-level findings.
- `repeater/web/html/assets/index-XsXY2tAx.js:1` contains a footer link to `https://openhop.dev` titled **“openHop Website.”** It was **not flagged**: it is presented as the project website, not as documentation. If the source UI later labels it as help/docs, it should use a specific docs article instead.
- The same bundled file links to local `/doc` as **“API Documentation.”** It was **not flagged**: this is an intentional appliance-local Swagger/OpenAPI reference, not a substitute for product setup documentation. Central docs may link to or explain it, but replacing it with static product prose would remove live API-schema behavior.
- `docs/adding_sensors.md` is developer documentation stored in the source tree, but it contains no legacy outbound documentation link. It was not turned into a link finding. A future docs-content audit may decide to promote its material into a dedicated central **Sensor Plug-in Development** article.
- Relative `docs/*.png` targets in `README.md` are images and were excluded by scope. The binary files themselves were still counted in coverage.
- Repository clone/source links, GitHub API/raw release URLs, package indexes, dependency/vendor documentation embedded in generated libraries, licenses, hardware-vendor links, community links, firmware/update downloads, badges/images, localhost/appliance API URLs, and issue/support destinations were reviewed and excluded under the requested rules.
- No old `docs.pymc.*`, pyMC/openHop GitHub Pages documentation domain, GitHub `blob`/`tree` documentation URL, or bare `https://docs.openhop.dev/` homepage link was found in the exact target's tracked text.

## Recommended order

1. Fix F1 in RepeaterUI source and regenerate the backend UI artifact; this is the most visible wrong destination.
2. Add the explicit CH341 article URL to the F3 upgrade message.
3. Replace the documentation-oriented README anchors with central article links while retaining repository-local legal/project metadata.
4. Create the proposed uninstallation article before changing `README.md:23`, so the replacement never points to a placeholder or missing route.
