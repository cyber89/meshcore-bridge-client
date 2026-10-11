# Frontend modernization meeting — 2026-10-10

**Status: proposed plan.** This meeting does not implement the changes below. Evidence comes from static source inspection; no browser, suites, operational services or radio were used. The current visual baseline is commit `eb99232`.

## Participants and agreement

Three delegated agents reviewed UI/UX, components/accessibility, and frontend architecture. The lead compared their findings with the source and circulated the findings for discussion. All three agreed to prioritize truthful states, request coordination and dialog ownership before further visual restructuring.

Keep Vanilla JS/CSS, local Bootstrap Icons, system fonts, the current color direction, and the existing minified/precompressed delivery. Modernization should improve clarity, keyboard interaction and maintainability. The previous refinement already introduced theme tokens, button styling and dialog visual treatment; this plan builds on it.

## Phase 1 — Interaction correctness

| Work | Source evidence | Acceptance criteria |
| --- | --- | --- |
| Distinguish loading, empty, stale/cache, offline and error states. | `ChatModule.renderCurrentConversation()` clears the feed before awaiting history; on failure it deletes the feed and can render the empty-message state. Initial analytics markup labels serial/MQTT as connected before a verified update. | Keep eligible current data during refresh; show explicit loading and error states; do not represent a failed read as an empty result or display success before confirmation. Authorization changes must clear protected views appropriately rather than retain unauthorized data. |
| Coordinate requests. | `AnalyticsModule.fetchAnalytics()` requests the selected range without cancellation or a generation guard. | A response for a previous range cannot replace the current range; preserve usable data on recoverable failure; state busy/error explicitly. Request cancellation must not replay writes or radio commands. |
| Give dialogs one lifecycle owner. | `_initBootstrapModalBridge()`, `_initModalFocus()` and `_displaySystemDialog()` all manage aspects of visibility/focus. The repeater module's Escape listener does not check the top dialog or `defaultPrevented`. | Escape closes only the top dialog; cancellation keeps its parent open; restore focus after the closing transition; queued dialogs resolve once; destructive confirmations initially focus Cancel. The competing-handler risk needs runtime reproduction. |
| Make selection and errors accessible. | Chat/contact/channel selectors use click-only `div`/`li`; some channel `role=option` entries have no keyboard handling. Form submission errors commonly use notifications. | Native controls for selection, distinct secondary actions, visible focus, field-linked errors and preserved inputs after rejection. Busy states prevent duplicate submission. |

The dialog controller should own the active stack, opening/closing transitions, focus and dismissal, keeping Bootstrap as the current modal adapter. Modules request open/close operations instead of maintaining competing observers. Preserve existing public `showConfirm`, `showPrompt` and `showAlert` promise contracts and migrate call sites incrementally.

## Phase 2 — Layout and component consistency

1. **Shell and responsive navigation:** distinguish web connection from radio connection; retain a compact operational status on mobile; make secondary metrics accessible outside XL layouts. Clarify the current 900px chat and 991.98px global-navigation transitions. Keep search, back-navigation and composer usable with the mobile keyboard.
2. **Typography and density:** create a semantic scale for body, labels, technical metadata and headings. Review existing 11px labels and compact root sizing. A comfortable/compact preference can live in LocalStorage; exact sizes are to be selected and checked in the real layouts.
3. **Shared controls:** define primary, secondary, destructive, icon-only and compact variants, with common loading, disabled, selected and focus states. Use the existing icon library for interface actions; keep user chat emojis as content. Add translated accessible names to icon-only actions and pressed state to favorites.
4. **Forms and long dialogs:** standardize section headings, help text, validation and visible actions around scrollable content. Preserve explicit confirmation and RF warnings in repeater administration; group advanced fields without hiding required context.
5. **Tabs and translation:** reuse the main navigation's keyboard pattern for local/repeater subtabs. Translate explicit text spans rather than relying on mixed icon/text-node heuristics. Language switches must preserve selection, input and operation state.

## Phase 3 — Maintainability and measured performance

Split editable CSS into tokens, base, shell, components and view styles, preserving cascade order and the public `/css/app.css` entry point. Adapt the build to bundle source dependencies into one served `app.min.css`, track their hashes and regenerate gzip. Splitting source files alone must not create an unnecessary chain of runtime requests. Do not introduce cascade layers mechanically: unlayered Bootstrap/vendor rules can outrank layered application styles.

Extract focused modules for dialog lifecycle, navigation and request/view state from the application coordinator. Retain unsubscribe handles from EventBus and define activation/deactivation/disposal before adding deferred initialization. Keep live data handling separate from whether a panel is visible; an inactive view must not lose incoming chat. Consolidate inline styles by component rather than replacing every override globally. Keep existing DOM identifiers and event contracts while migrating consumers.

Only consider deferred module loading or alternative rendering strategies after measuring startup, long lists, view changes, CPU and memory in an isolated station. Source size and counts of inline styles or `!important` declarations are maintenance signals, not performance measurements. Do not promise CPU/RAM reductions without a benchmark.

Documentation discrepancy: the design skill currently refers to `css/tokens.css`, which does not exist in this checkout. Tokens currently live in `css/app.css`, as documented in `FRONTEND_DELIVERY.md`. Correct the skill reference when implementing the source organization, rather than assuming a nonexistent file is authoritative.

## Ownership and execution order

| Role | Ownership for a future implementation |
| --- | --- |
| Lead | Integration, public contracts, phased review, documentation and build artifacts. |
| Components agent | Dialog controller, keyboard controls, tabs and form error behavior. |
| UI/UX agent | CSS tokens/components, shell/layout and responsive presentation. |
| Frontend architecture agent | Request coordination, view states and build/source organization. |

Assign actual files exclusively before work: several roles need `app.js`, `chat.js` and `index.html`, so these must have one owner per phase. Start with interaction contracts and state handling, then components/layout, then source organization and measured optimization. Each phase should remain reviewable and deployable independently.

## Constraints and validation

- Preserve CLIENT/LOCAL/REPEATER messaging restrictions, manual RF actions and existing cooldowns. This plan adds no radio polling, retries or timers. Any future radio-related change must use the repository's airtime checklist and user-selected intervals.
- Keep SQLite authoritative, IndexedDB as station-scoped downloaded history, LocalStorage for interface preferences and SessionStorage for tab credentials.
- Retain ES/EN, theme events, current endpoints and dialog promise contracts; a frontend refresh must not introduce dependencies on new backend routes accidentally.
- Static checks: source syntax, selector/event inventories, available icons, actual color-pair contrast and reproducible minified/gzip build.
- Browser/suites require an explicit user request under `AGENTS.md`. When requested, use an isolated virtual station to check 320/375/768/1024px and desktop widths, both themes/languages, zoom 200%, keyboard focus/Escape, nested and queued dialogs, slow/reordered responses, authorization failures and offline cached history. Never use an operational station as a fixture.

The next implementation milestone is Phase 1. This document records recommendations and acceptance criteria, not verified runtime fixes.
