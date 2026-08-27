# REPORT4 - Deep Analysis: MeshCore Bridge v3.0 Pro
**Date:** 2026-08-27  
**Scope:** Full codebase analysis (security, SOLID, architecture, coupling, redundancy, frontend)

---

## 1. SECURITY VULNERABILITIES

### 1.1 CRITICAL: Deprecated `webbrowser` module import in diagnostics
- **File:** `src/diagnostics.py:10` — `import webbrowser` is imported but never used. While not exploitable, it pulls an unnecessary system dependency and signals incomplete code cleanup.

### 1.2 HIGH: TCP Companion token transmitted in plaintext
- **File:** `src/tcp_companion_server.py:170-184` — `COMPANION_TOKEN` is sent as `TOKEN:{token}` over a raw TCP socket with no TLS. Any network-level attacker can sniff the token.
- **Mitigation:** The project documentation mentions TLS is out of scope for the bridge, but this should be documented as a known limitation and users warned.

### 1.3 HIGH: TCP Companion IP allowlist bypass
- **File:** `src/tcp_companion_server.py:164-167` — The `COMPANION_ALLOWED_IPS` check only looks at `peer[0]` (remote IP). If the bridge is behind a reverse proxy or Docker NAT, the peer IP will always be the proxy IP, rendering the allowlist ineffective or permissive.

### 1.4 MEDIUM: WebSocket Origin validation too permissive for private networks
- **File:** `src/web/http_server.py:282-289` — Any request originating from `192.168.*`, `10.*`, `127.*`, or `172.16-31.*` is automatically allowed, even if `BRIDGE_ALLOWED_ORIGINS` is explicitly configured to restrict origins. This defeats origin-based CORS restrictions on LAN deployments.

### 1.5 MEDIUM: API key comparison is not timing-safe
- **File:** `src/web/http_server.py:260` — `req_api_key != api_key` uses standard string comparison, which is vulnerable to timing side-channel attacks. Should use `hmac.compare_digest()`.

### 1.6 MEDIUM: No rate limiting on login/auth endpoints
- **File:** `src/web/api_router.py:316-328` — The `/api/repeater/remote/login` endpoint accepts unlimited password attempts. No lockout or throttling exists. Same applies to `COMPANION_TOKEN` auth at `tcp_companion_server.py:174`.

### 1.7 LOW: `_is_traversal_attempt` is incomplete
- **File:** `src/web/http_server.py:419-428` — The detection only checks for `..`, `%2e`, `%2f`, and `....`. URL-encoded variants like `%2E%2E` (double-encoded) or `..%252f` are not caught. The `Path.resolve().is_relative_to()` check at line 432 provides a second layer of defense, making this low severity.

### 1.8 LOW: `qrcode.js` loaded from external CDN
- **File:** `src/web/static/index.html` references Leaflet from `unpkg.com`. A supply-chain attack on unpkg could inject malicious JS. The CSP at `http_server.py:471` allows `script-src 'self'` which blocks inline scripts but does NOT block the external script tag at line 21 of `index.html`. This is a **CSP bypass** — external scripts are loaded before CSP enforcement, and the CSP only applies to dynamically loaded resources.

---

## 2. SOLID / CLEAN CODE VIOLATIONS

### 2.1 SRP Violation: `MeshCoreBridge` is a God Object
- **File:** `src/bridge_core.py` (699 lines)  
- The class manages serial adapter lifecycle, MQTT client, web server, TCP server, watchdog, health reporter, node registry, repeater manager, deduplicator, rate limiter, preflight, and diagnostics. It has 30+ attributes and 40+ methods.
- **Recommendation:** Extract adapter lifecycle, health monitoring, and server orchestration into separate manager classes. Use composition root pattern.

### 2.2 SRP Violation: `WebAPIRouter.handle_request` is a 350-line if/elif chain
- **File:** `src/web/api_router.py:184-528`  
- Every new endpoint requires adding another `if` block. This violates Open/Closed Principle.
- **Recommendation:** Implement a route registry pattern: `self._routes[("GET", "/api/status")] = self._route_status`.

### 2.3 OCP Violation: `record_incoming_event` method
- **File:** `src/web/api_router.py:67-183`  
- This method has complex branching for every event type (`telemetry`, `public`, `channel`, `direct`, `self_info`, etc.). Adding new event types requires modifying this method.
- **Recommendation:** Use a dispatch map or strategy pattern per event type.

### 2.4 DIP Violation: Heavy use of `getattr(self.bridge, ...)` everywhere
- **File:** `src/web/api_router.py`, `src/diagnostics.py`, `src/health_reporter.py` (not shown but referenced)  
- Nearly every method accesses bridge internals via `getattr(self.bridge, "xxx", None)` and `hasattr()` checks. This is fragile and defeats type checking.
- **Recommendation:** Define typed Protocol interfaces (already partially done in `bridge_core.py:39-62`) and inject them as dependencies.

### 2.5 ISP Violation: `NodeContactInfo` has 50+ fields
- **File:** `src/contact_manager.py:47-101`  
- The dataclass conflates: identity (name, alias, role), RF metrics (rssi, snr, lqi), telemetry (battery, temp, gps), traffic stats (rx, tx, errors), and routing (neighbors, best_route). These should be split into separate value objects.
- **Recommendation:** Create `NodeIdentity`, `NodeRFMetrics`, `NodeTelemetry`, `NodeTrafficStats` and compose them.

### 2.6 DRY Violation: `escapeHtml` defined twice in frontend
- **File:** `src/web/static/js/app.js:6-14` (global function) and `app.js:357-365` (class method)  
- Both do exactly the same thing. The global one is the correct entry point; the class method is redundant.

### 2.7 DRY Violation: Uptime formatting duplicated
- **File:** `src/web/api_router.py:266-270` and `src/sensor_decoder.py:433-441`  
- Both compute `Xd Xh Xm Xs` from seconds. Should be a shared utility.

---

## 3. ARCHITECTURE COMPLIANCE

### 3.1 Adapter Pattern (✅ Compliant)
- `BaseSerialAdapter` → `MeshcoreSDKAdapter`, `RawSerialFramingAdapter`  
- Clean abstraction at `src/serial_driver.py`. Both adapters implement the same interface with `send_raw_companion_frame()`, `set_rx_callback()`, etc.

### 3.2 Facade Pattern (⚠️ Partially Compliant)
- `MeshCoreBridge` serves as facade but exposes too many internal components (deduplicator, node_registry, rate_limiter, etc.) directly to the web layer. A proper Facade would provide a simplified interface.

### 3.3 Strategy Pattern (✅ Compliant for adapters)
- Serial adapter selection via `_create_serial_adapter()` at `bridge_core.py:202+`. The strategy is chosen at init time.

### 3.4 Dependency Inversion (❌ Violated)
- Web layer, diagnostics, and health reporter all reach through `bridge` object to access internals. No abstraction boundaries.

### 3.5 Event-Driven Architecture (✅ Mostly Compliant)
- `RxEventRouter` handles incoming events and routes to MQTT/WebSocket. The callback chain `serial_adapter.on_mesh_event → bridge.on_mesh_event → rx_router.route → mqtt/websocket` is well-structured.

---

## 4. REDUNDANT / DEPRECATED / DEAD CODE

### 4.1 `webbrowser` import in diagnostics
- **File:** `src/diagnostics.py:10` — `import webbrowser` never used.

### 4.2 `asyncio` + `threading` dual locks in deduplicator
- **File:** `src/deduplicator.py:28-29` — Both `asyncio.Lock()` and `threading.Lock()` are created. The `_async_lock` is never used (the async `is_duplicate` method uses it, but `is_duplicate_sync` doesn't). If only async code calls this, the threading lock is dead weight.

### 4.3 Duplicate `import os` inside functions
- **Files:** `src/tcp_companion_server.py:155`, `src/web/http_server.py:172,247,378`  
- `import os` is repeated inside functions instead of at module level. While Python caches imports, this is non-idiomatic and clutters function bodies.

### 4.4 `PreflightCheckResult.passed` vs `is_critical` naming
- **File:** `src/preflight.py:22` — `passed` field is `bool` but the naming suggests a result. The `run_all()` method returns a dict with a `status` field that doesn't use the `passed` field. This creates confusion.

### 4.5 Hardcoded version strings
- **Files:** `src/__init__.py:40` (`__version__ = "3.0.0"`), `src/diagnostics.py:259` (`"version": "3.0.0"`), `src/web/static/index.html:33` (`v3.0 Pro`)  
- Three places where version is hardcoded independently.

### 4.6 `is_common_chat_message` duplicated in frontend and backend
- **File:** `src/web/api_router.py:178` calls `rx_router.is_common_chat_message()` (Python)  
- **File:** `src/web/static/js/app.js:436-478` defines `isCommonChatMessage()` (JS)  
- Both implement the same filtering logic independently. If they diverge, messages may be dropped by one but not the other.

---

## 5. COUPLING ISSUES

### 5.1 Web layer → Bridge internals (Tight Coupling)
- `api_router.py` directly accesses: `bridge.node_registry`, `bridge.rate_limiter`, `bridge.serial_adapter`, `bridge.mqtt`, `bridge.diagnostics`, `bridge.admin_handler`, `bridge.web_server`, `bridge.tcp_server`, `bridge.preflight`. This creates a web of implicit dependencies.

### 5.2 Diagnostics → Bridge internals (Tight Coupling)
- `diagnostics.py:188-233` — `collect_health_snapshot()` accesses bridge attributes via `getattr(self.bridge, ...)`. Any attribute rename breaks diagnostics silently.

### 5.3 `NodeContactUpdate` mirrors `NodeContactInfo` (Data Duplication)
- **File:** `src/contact_manager.py:116-167`  
- `NodeContactUpdate` has 40+ fields that mirror `NodeContactInfo`. Any new field in `NodeContactInfo` must be manually added to both. This violates DRY and is error-prone (the `load_from_file` method at lines 803-891 must also be updated).

---

## 6. BACKEND ISSUES

### 6.1 `NodeRegistry._find_existing_key` has O(n) scan
- **File:** `src/contact_manager.py:248-272`  
- Iterates all nodes on every `add_or_update()` call for prefix matching. With many nodes, this degrades performance.
- **Recommendation:** Use a trie or maintain a prefix index.

### 6.2 `save_to_file` not atomic on Windows
- **File:** `src/contact_manager.py:793-796` — Uses `tmp_path.replace(target_path)` which is not atomic on Windows (raises `PermissionError` if target is open).

### 6.3 `SensorReading` not hashable
- **File:** `src/sensor_decoder.py:35-42` — `SensorReading` uses `@dataclass(frozen=True)` but has `value: Any` field which may contain unhashable types, making it unusable in sets.

### 6.4 `_route_contacts` DELETE path accesses private `_nodes_by_key`
- **File:** `src/web/api_router.py:676` — `del self.bridge.node_registry._nodes_by_key[pubkey]` directly modifies private state instead of using a public API method.

### 6.5 No graceful shutdown for background tasks
- **File:** `src/bridge_core.py:174-183` — `_cleanup_loop` runs forever with `while self.running` but there's no mechanism to cancel it on shutdown. The `set` of tasks is cleaned up but not awaited.

---

## 7. FRONTEND ISSUES

### 7.1 `app.js` is a monolith (3000+ lines)
- Single class `MeshCoreStationApp` manages all UI, WebSocket, map, chat, contacts, logs, settings, analytics, and terminal. Violates SRP.
- **Recommendation:** Split into ES modules: `ChatManager`, `NodeDirectory`, `MapController`, `LogsConsole`, `SettingsManager`.

### 7.2 No CSP compliance for external scripts
- **File:** `index.html:21` — `<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js">` loads from CDN. CSP at `http_server.py:471` allows `script-src 'self'` but this doesn't apply to static HTML loaded before CSP enforcement. A CSP `meta` tag in the HTML would block this.

### 7.3 DOM manipulation via string interpolation (XSS risk)
- **File:** `app.js` uses `element.innerHTML = ...` with escaped content in many places. While `escapeHtml()` is defined and used, the sheer volume of DOM manipulation makes it easy to miss a spot.

### 7.4 localStorage for repeater passwords
- **File:** `app.js:1224-1270` — Repeater passwords stored in `localStorage` in plaintext JSON. Any XSS vulnerability exposes all stored passwords.

### 7.5 `generateRandomHex` uses `Math.random()`
- **File:** `app.js:1004-1011` — `Math.random()` is not cryptographically secure. Should use `crypto.getRandomValues()`.

### 7.6 CSS uses `clamp()` for typography (good) but no fallback
- **File:** `css/app.css` — Uses modern CSS features. IE11/older browsers will fail. Acceptable for this use case but worth noting.

### 7.7 Leaflet map double initialization
- **File:** `app.js:686-704` — When the map tab is clicked, `initLeafletMap()` is called, but if the map already exists, `invalidateSize()` is called twice (lines 691 and 703).

---

## 8. RECOMMENDATIONS (Priority Order)

### HIGH PRIORITY
1. **Refactor `MeshCoreBridge`** — Extract `AdapterManager`, `HealthMonitor`, `ServerOrchestrator` classes
2. **Replace if/elif router** — Implement route registry pattern in `api_router.py`
3. **Fix CSP bypass** — Add `<meta http-equiv="Content-Security-Policy">` to `index.html` or serve Leaflet locally
4. **Use `hmac.compare_digest()`** for API key comparison
5. **Add rate limiting** to auth endpoints

### MEDIUM PRIORITY
6. **Split `NodeContactInfo`** into identity, metrics, telemetry, and stats value objects
7. **Deduplicate uptime formatting** — Extract to `event_utils.py`
8. **Deduplicate `isCommonChatMessage`** — Use a shared config or generate from protocol types
9. **Add typed Protocol interfaces** for bridge dependencies injected into web/diagnostics
10. **Make `save_to_file` atomic on Windows** — Use `shutil.move()` or Windows-specific rename

### LOW PRIORITY
11. **Remove `webbrowser` import** from diagnostics
12. **Deduplicate `escapeHtml`** in frontend
13. **Use `crypto.getRandomValues()`** for hex generation
14. **Clean up `import os`** inside functions
15. **Fix Leaflet double init** in map tab

---

*Report generated by Lead Orchestrator Agent — MeshCore Bridge v3.0 Pro*
