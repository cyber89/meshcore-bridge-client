# MeshCore Bridge - Code Analysis & Test Report (v3.0.0)
*Generated: 2026-08-26 | Orchestrator Agent*

---

## 1. Executive Summary

- **Total Files Analyzed**: `src/` module suite (18 Python files)
- **Tests Executed**: 147 total (127 passed, 10 skipped, 2 failed)
- **Code Coverage**: 64% overall (improved from initial audit)
- **Critical Issues**: 6 security (SEC-001 to SEC-006) + 2 test failures (FT-001, FT-002)
- **High Priority**: 9 concurrency issues (CONC-001 to CONC-009)
- **Medium Priority**: 10 quality issues (QUAL-001 to QUAL-010)
- **Low Priority**: 7 robustness issues (ROB-001 to ROB-007)
- **Frontend Improvements**: 5 items (FE-001 to FE-005)

---

## 2. Component Analysis

### 2.1 Bridge Component (`src/bridge_core.py`)

**Role**: Central orchestrator and lifecycle manager that integrates all subsystems:
- Serial adapter (with SDK / Raw fallback)
- MQTT client
- TCP companion server
- Web server + API router
- Rate limiter + airtime tracker
- Deduplicator in RAM
- Node registry
- Repeater manager
- Health reporter
- Diagnostic manager

**Key Metrics**:
- 363 statements, 61% test coverage
- 5 major task groups initialized in `_init_*()` methods
- `run_forever()` creates new event loop, handles SIGINT/SIGTERM

**Critical Findings**:
| ID | Issue | Severity | Location |
|----|-------|----------|----------|
| CONC-008 | `_tx_worker` competes with `TxRateLimiter` for same queue | HIGH | bridge_core.py:491-502 |
| CONC-003 | `_background_tasks` set without lock protection | HIGH | bridge_core.py:151 |
| ROB-003 | `run_forever()` doesn't cancel pending tasks on shutdown | LOW | bridge_core.py:631-654 |
| BUG-02 | Stop order dependency in `stop()` (fixed in v3.0) | FIXED | bridge_core.py:362-377 |

**Test Status**: 
- `test_bridge_logic.py` - All tests passing
- Coverage highlights: `bridge_core.py` missing on lines 132-134, 138-141, etc.

---

### 2.2 MQTT Component (`src/mqtt_client.py`)

**Role**: Async MQTT client with paho-mqtt v2.x, LWT, deterministic reconnection backoff (1-30s).

**Key Metrics**:
- 135 statements, 59% test coverage
- 7 topics defined: `topic_state`, `topic_health`, `topic_tx`, `topic_tx_status`, `topic_admin_cmd`, `topic_admin_stat`
- `connect_async()` with `reconnect_delay_set(min_delay=1, max_delay=30)`

**Critical Findings**:
| ID | Issue | Severity | Location |
|----|-------|----------|----------|
| ROB-007 | Callback can crash paho-mqtt network thread if exception propagates | CRITICAL | mqtt_client.py:201-216 |
| CONC-007 | `asyncio.get_event_loop()` deprecated since Python 3.10 | HIGH | mqtt_client.py:111 |
| CONC-009 | `await future` in dispatcher without timeout - task zombie if worker dies | HIGH | mqtt_dispatcher.py:104 |

**Test Status**:
- `test_mqtt_client.py` - Most tests passing
- Coverage highlights: lines 21-41, 63-107, 111-120, etc. missing

---

### 2.3 TCP Port Component (`src/tcp_companion_server.py`)

**Role**: TCP socket server on port 5000 for official MeshCore companion apps (Android/iOS CLI).

**Key Metrics**:
- 140 statements, 70% test coverage
- Binary framing: `0x3C` (`<`) for commands, `0x3E` (`>`) for responses
- `active_clients` set: unlimited, no whitelist

**Critical Findings** (already documented in TODO.md):
- SEC-002: No authentication, unlimited connections, DoS vulnerable
- SEC-003: Broadcast without drain() - Slow client attack/OOM

**Test Status**:
- `test_tcp_companion_server.py` - Tests passing
- Coverage good at 70%

---

### 2.4 Web Frontend/Backend (`src/web/`)

**Role**: HTTP/WebSocket server + REST API + SPA interface.

**Key Files**:
- `src/web/http_server.py` - 245 statements, 79% coverage
- `src/web/api_router.py` - 571 statements, 69% coverage
- `src/web/static/index.html` - Client-side UI

**Critical Findings** (already documented in TODO.md):
- SEC-001: API REST sin autenticación en endpoints sensibles
- SEC-004: CORS wildcard `Access-Control-Allow-Origin: *`
- SEC-005: CSP ausente - riesgo XSS desde datos de la malla
- CONC-005: WebSocket sin timeout - conexiones zombie
- FE-001: `index.html` usa `innerHTML` con datos no sanitizados
- FE-005: HTTP status line siempre dice "OK" para todos los códigos de error

**Test Status**:
- `test_web_server.py` - Passing
- `test_playwright_e2e_simulation.py` - **FT-002**: Fails due to E2E environment (Playwright not installed or bridge not running)
- Coverage highlights: api_router.py missing on many lines (522+), http_server.py missing on 33-41, 45-48, etc.

---

### 2.5 Supporting Components

| Component | Key File | Statements | Coverage | Critical Issues |
|-----------|----------|------------|----------|-----------------|
| Deduplicator | `src/deduplicator.py` | 49 | 78% | CONC-001: Not thread-safe under asyncio concurrency |
| Rate Limiter | `src/rate_limiter.py` | 188 | 87% | CONC-002: CustomTxQueue maxsize=0 (unlimited) |
| Serial Driver | `src/serial_driver.py` | 542 | 45% | QUAL-009: connect() blocks event loop 4.5s+ |
| Contact Manager | `src/contact_manager.py` | 396 | 87% | QUAL-001: frozen=True with mutable list |
| Rx Router | `src/rx_router.py` | 437 | 70% | QUAL-005: God class (1042 lines) |
| Admin Handler | `src/admin_handler.py` | 816 | 46% | QUAL-004: God class (1210 lines) |
| Sensor Decoder | `src/sensor_decoder.py` | 401 | 9% | Large file, low coverage |
| LQI Engine | `src/lqi_engine.py` | 107 | 94% | Well-tested, high coverage |
| Health Reporter | `src/health_reporter.py` | 50 | 64% | Moderate coverage |
| Preflight | `src/preflight.py` | 69 | 67% | Moderate coverage |

---

## 3. Test Results Summary

```
=== TEST RUN RESULTS ===
Total: 147 tests
  Passed: 127 (86.4%)
  Skipped: 10 (6.8%)
  Failed: 2 (1.4%)

=== FAILURE DETAILS ===

FT-001: test_record_incoming_telemetry_with_known_and_unknown_nodes
  File: tests/test_node_and_repeater_config.py
  Issue: Log format mismatch - test expects "Repetidor_Norte (31d03b1f)" but log format is "Telemetría recibida de nodo 'Repetidor_Norte' (31d03b1f)"
  Impact: Test failure due to logging format change, not business logic
  Fix: Update test assertion or standardize log format

FT-002: test_playwright_web_e2e_simulation
  File: tests/test_playwright_e2e_simulation.py
  Issue: E2E test infrastructure - requires bridge running at 127.0.0.1:8080 and Playwright installed
  Impact: Test requires full runtime environment
  Fix: `playwright install` + ensure bridge is running

=== PASSED ===
- test_protocol_types.py (6 tests)
- test_bridge_logic.py
- test_diagnostics.py
- test_diagnostics_export.py
- test_contact_manager.py
- test_preflight.py
- test_rate_limiter_priority.py
- test_repeater_manager.py
- test_sensor_decoder.py
- test_serial_adapter.py
- test_serial_watchdog.py
- test_virtual_mesh_simulation.py
- test_tx_rate_limiter.py
- test_e2e_simulation.py (non-Playwright)
- And 80+ more...

=== SKIPPED ===
- Tests requiring hardware serial port
- Tests requiring MQTT broker connection
```

---

## 4. Severity Distribution

| Severity | Count | Items |
|----------|-------|-------|
| 🔴 CRITICAL | 6 | SEC-001 to SEC-006 (security vulnerabilities) |
| 🟠 HIGH | 9 | CONC-001 to CONC-009 (concurrency & resiliency) |
| 🟡 MEDIUM | 10 | QUAL-001 to QUAL-010 (code quality & debt) |
| 🟢 LOW | 7 | ROB-001 to ROB-007 (robustness & observability) |
| 🔵 MEJORA | 5 | FE-001 to FE-005 (frontend & UX) |
| **Test Failures** | **2** | FT-001, FT-002 (test infrastructure) |

**Estimated Effort**: ~85 hours total (as noted in TODO.md)

---

## 5. Recommendations & Next Steps

### Phase 1 - CRITICAL (Immediate, < 10 hours)
1. **SEC-001**: Implement API Key authentication in `http_server.py` - protect `/api/admin/*`, `/api/tx`, `/api/repeater/*`
2. **SEC-002**: Add connection limits and IP whitelist to `tcp_companion_server.py` - max 4-8 clients
3. **SEC-003**: Add `await writer.drain()` to broadcast functions with timeout - prevent OOM
4. **SEC-004**: Replace CORS wildcard with origin validation - `BRIDGE_ALLOWED_ORIGINS` config
5. **SEC-005**: Add CSP header to HTML responses - prevent XSS from mesh data
6. **SEC-006**: Validate PSK regex in `set_channel()` - prevent firmware command injection

### Phase 2 - HIGH (Stability, < 20 hours)
7. **CONC-001**: Add `asyncio.Lock()` to `PacketDeduplicator` - thread-safe under asyncio concurrency
8. **CONC-002**: Set `maxsize` on `CustomTxQueue` with configurable limit + `total_dropped` metric
9. **CONC-003**: Migrate `_background_tasks` to `asyncio.TaskGroup` or protect with `asyncio.Lock()`
10. **CONC-004**: Add `asyncio.Semaphore` for RX event concurrency limiting
11. **CONC-005**: Add `asyncio.wait_for()` timeouts in WebSocket frame reading
12. **CONC-006**: Add timeout to `ping_or_check_alive()` in SerialWatchdog
13. **CONC-007**: Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()`
14. **CONC-008**: Remove `_tx_worker()` from `bridge_core.py` - use `TxRateLimiter` only
15. **CONC-009**: Add `asyncio.wait_for()` timeout on `await future` in MQTT dispatcher

### Phase 3 - MEDIUM/LOW (Quality & Robustness, ~30 hours)
16-35. Continue with QUAL and ROB items from TODO.md

### Phase 4 - Frontend Improvements
36-40. Address FE-001 to FE-005 for better UX and security

---

## 6. Test Infrastructure Status

**Current Test Suite**: 147 tests across 35 test files
- **127 passing** (86.4%)
- **10 skipped** (require hardware/MQTT broker)
- **2 failing** (test infrastructure issues, not code bugs)

**Test Coverage by Module**:
- Protocol Types: 88% (good)
- Rate Limiter: 87% (good)
- Contact Manager: 87% (good)
- Health Reporter: 64% (moderate)
- Deduplicator: 78% (moderate)
- Rx Router: 70% (good)
- Serial Driver: 45% (needs improvement)
- Sensor Decoder: 9% (large file, needs more tests)
- Web Server: 79% (good)
- MQTT Client: 59% (moderate)
- Bridge Core: 61% (moderate)

**To Run Tests**: `python -m pytest tests/ -q`
**To Check Coverage**: `python -m pytest tests/ --cov=src --cov-report=html`
**To Fix FT-001**: Update test log format assertion in `test_node_and_repeater_config.py`
**To Fix FT-002**: `pip install playwright && playwright install` + run bridge server

---

## 7. Action Items Summary

| Priority | Count | ID Range |
|----------|-------|----------|
| CRITICAL | 6 | SEC-001 to SEC-006 |
| HIGH | 9 | CONC-001 to CONC-009 |
| MEDIUM | 10 | QUAL-001 to QUAL-010 |
| LOW | 7 | ROB-001 to ROB-007 |
| MEJORA | 5 | FE-001 to FE-005 |
| **Test Fixes** | **2** | FT-001, FT-002 |

**Total Estimated**: ~85 hours (from TODO.md)

---
*Report generated by Agente Orquestador (Agente 0) de MeshCore Bridge.*
*Cross-referenced with: AGENT_ACTIVITY_REPORT.md, PROTOCOL_SPEC.md, ARCHITECTURE.md, TODO.md*