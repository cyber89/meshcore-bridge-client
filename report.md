# Reporte de Auditoría Integral — MeshCore Universal Bridge v3.0 Pro

**Fecha**: 2026-09-12
**Alcance**: 106 archivos Python (src/, tests/, scripts/, config.py), 15 archivos JS, index.html, app.css (5.304 líneas), pyproject.toml y documentación (docs/, README, AGENTS.md).
**Metodología**: Análisis multi-agente (4 auditorías paralelas: módulos core, subsistema web, suite de pruebas, arquitectura/patrones) + verificación manual de cada hallazgo CRÍTICO/ALTO + compilación de sintaxis completa.
**Modo**: Solo lectura. No se modificó ningún archivo de producción ni se ejecutaron pruebas.

---

## 1. Resumen Ejecutivo

| Indicador | Resultado |
|---|---|
| Compilación Python (`py_compile`) | **106/106 OK** — sin código truncado ni errores de sintaxis |
| Sintaxis JavaScript (`node --check`) | **15/15 OK** — sin errores |
| Estado de pruebas (reportado por docs/AGENT_ACTIVITY_REPORT.md) | 227 pasados, 10 skipped, 0 fallidos |
| Hallazgos totales | **~145** (4 CRÍTICOS, 16 ALTOS, 37 MEDIOS, ~88 BAJOS) |
| Verificación del sistema con pruebas existentes | **PARCIAL (~60-65%)** — ver §6 |
| Cumplimiento arquitectura y patrones | **SÓLIDO (B+)** con desviaciones documentadas — ver §5 |
| Sincronización `/deploy/` | 100% sincronizado (44+ archivos idénticos, MD5 verificado) |

**Conclusión general**: El proyecto está **estructuralmente sano** (sin truncados, sin errores de sintaxis, arquitectura en capas bien implementada), pero existen **4 defectos críticos** (1 de seguridad, 3 de lógica), varios **contratos frontend/backend rotos**, y **huecos estructurales de cobertura de pruebas** en las zonas de mayor riesgo (pipeline RX, ciclo de vida del bridge, autenticación web, protección de airtime).

---

## 2. Hallazgos CRÍTICOS (verificados manualmente)

### C1. Bypass de autenticación API con `BRIDGE_API_KEY` vacía — fail-open
- **Archivo**: `src/web/http_server.py:463-465`
- **Evidencia**:
  ```python
  if not api_key:
      logging.warning("BRIDGE_API_KEY no configurada, omitiendo autenticación (modo desarrollo)")
      return True
  ```
- **Impacto**: Si la variable de entorno no está definida (despliegue por defecto del `.env.example` — vacía), TODOS los endpoints protegidos (`/api/tx`, `/api/admin/*`, `/api/repeater/*`, `/api/node/reboot`) quedan abiertos a cualquier cliente de la LAN: transmisión RF arbitraria, comandos admin, traceroutes, reinicio de nodos y borrado de logs.
- **Recomendación**: Fail-closed (401) con flag explícito tipo `ALLOW_UNAUTHENTICATED=true` para desarrollo.

### C2. `UnboundLocalError` en todo TX broadcast — Sniffer nunca registra broadcasts
- **Archivo**: `src/bridge_core.py:735` (uso) vs `652` (definición condicional)
- **Evidencia**: `is_admin_cmd` se define SOLO dentro de `if not is_broadcast:` (L652), pero se usa en L735:
  ```python
  packet_type="CHAT" if not is_admin_cmd else "ADMIN",
  ```
  Cuando `is_broadcast=True` (todo mensaje a canal público), la variable no existe → `NameError`/`UnboundLocalError` → capturada por `except Exception` (L745) con `logging.debug` silencioso → **el paquete TX broadcast nunca se registra en el PacketBuffer/Sniffer**.
- **Impacto**: La pestaña Sniffer/WebUI no muestra los broadcasts TX; error enmascarado. Falla en 100% de transmisiones a canal.

### C3. Asignación a property `self_info` sin setter — invalida conexiones exitosas
- **Archivo**: `src/serial_driver.py:289, 299` (asignación) vs `233-236` (property sin setter)
- **Evidencia**:
  ```python
  self.self_info = res_app.payload   # L289 — AttributeError: can't set attribute
  ```
  `MeshcoreSDKAdapter.self_info` es `@property` SIN setter. La `AttributeError` es tragada por el `except Exception as ex_init` (L304) que cae al **fallback `create_serial`** — la conexión directa con estabilización (ruta preferida y mejor instrumentada) se marca fallida aunque `send_appstart` haya tenido éxito.
- **Impacto**: En producción con SDK real, toda conexión inicial exitosa cae innecesariamente al path de fallback, degradando estabilidad del arranque (y posiblemente provocando reconexiones/retries adicionales).

### C4. Guarda anti-repetidor vulnerable con prefijos cortos — bypass de regla inmutable §1.1
- **Archivo**: `src/bridge_core.py:640-658` + `src/contact_manager.py:325-333, 832, 925-940`
- **Evidencia**: El target se valida con `target_str` **sin resolver primero a clave canónica**. `is_local_key` exige prefijos ≥6 chars y `get_by_key_or_prefix` (L832) exige `len(q) < len(key)` con matching de prefijo; un target de 4-5 chars hex (ej. `"a1b2"`) que sea prefijo real de la clave de un repetidor **no matchea** → `is_repeater_key()` retorna `False` → el DM de chat se envía al repetidor.
- **Impacto**: Viola la regla inmutable de AGENTS.md §1.1-1 (NUNCA mensajería a repetidores). `resolve_recipient_target` (bridge_core.py:393) y `get_canonical_key` (contact_manager.py:361) existen pero **no se invocan antes de la guarda**.
- **Recomendación**: Resolver `target → get_canonical_key(target)` antes de validar; rechazar claves no resolubles en DMs.

---

## 3. Hallazgos ALTOS

### Backend core

| # | Archivo:línea | Hallazgo |
|---|---|---|
| A1 | `mqtt_client.py:200` + `mqtt_dispatcher.py:54` | **Ruta MQTT muerta**: el dispatcher gestiona `TOPIC_ADMIN_REPEATER` pero `_on_connect` solo suscribe `topic_tx` y `topic_admin_cmd` — los comandos publicados en `{prefix}/admin/repeater/{node}/cmd` **nunca llegan** (contrato documentado en README §Mapa MQTT no operativo). |
| A2 | `rx_router.py:987-988` | Mensajes de canal (`CHANNEL_MSG_RECV`) se publican en `TOPIC_RX_CHANNEL/ch_N` **Y ADEMÁS** en `TOPIC_RX_DIRECT/{src}` — duplicación que contamina consumidores n8n de DMs. |
| A3 | `contact_manager.py:1073-1075` + `bridge_core.py:215-224` | **I/O síncrono bloqueante en event loop**: `save_to_file()` con `open()+json.dump()` se invoca desde la corrutina `_cleanup_loop` cada 60s — congela el bridge en SBCs con SD lenta. Violación directa de AGENTS.md (Agente 2, regla 1). Debería usar `asyncio.to_thread()`. |
| A4 | `contact_manager.py:1042` | `cleanup_inactive()` **nunca se invoca en producción** (solo tests) — el registro de nodos crece ilimitadamente (fuga de memoria lenta + JSON de persistencia creciente). |
| A5 | `contact_manager.py:345-358, 832` | Lookups por prefijo con escaneo O(n) completo de `_nodes_by_key` en cada `add_or_update`/`discover_node`/`record_packet` → O(n²) en mallas activas. |
| A6 | `rate_limiter.py:335-336` | `if item is None: continue` **salta el delay regulatorio** (el `finally` ejecuta `task_done` pero el `await asyncio.sleep(delay)` de L370 nunca corre) — múltiples `None` encolados producen busy-loop sin espaciado RF. |
| A7 | `admin_handler.py:417-467` | Patrón `except Exception: pass` ×3 en `_cli_version/_cli_battery/_cli_time` → reportan valores default hardcodeados como reales (batería "100%", "5.0V") — **telemetría falsa** al usuario. |
| A8 | `admin/repeater_executor.py:143-147` | `_execute_batch_config` envía login + N comandos `set_*` en ráfaga **sin `check_airtime_cooldown`** (que sí aplica `_execute_unit_command` L360-368) — viola checklist de airtime AGENTS.md §4-P1. |
| A9 | `serial_driver.py:429-441` | Monkey-patch de `self.mc._reader.handle_rx` (miembro privado del SDK) — si el SDK cambia o no expone `_reader`, falla silenciosa; doble registro apila callbacks (tramas duplicadas a companions). |
| A10 | `serial_driver.py:801-812` | Contacto sintético con clave padeada `(dest_target + "0"*64)[:64]` — contamina la libreta del firmware y reaparece como fantasma en `sync_all_contacts`. |
| A11 | `serial_driver.py:262-263` | Sombreado de `port_str` (puerto original vs puerto+baudrate del parseo TCP) + mutación de `self.port` en L259 — la reconexión pierde la config original del usuario. |

### Subsistema web

| # | Archivo:línea | Hallazgo |
|---|---|---|
| A12 | `contacts_controller.py:154-156` + `nodes.js:400` | **DELETE de contactos roto (contrato frontend/backend)**: el frontend envía `DELETE /api/contacts/{pubkey}` con clave en la URL, pero `_delete_contact` lee `req_body.get("public_key")` → siempre vacío → 404. **El botón "Eliminar contacto" nunca elimina nada en el servidor**; además `nodes.js:404` ejecuta `cCard.remove()` sin comprobar `res.ok` → borrado visual inconsistente (el contacto "revive"). |
| A13 | `map_tile_service.py:85` + `http_server.py:399` | **DoS de memoria sin auth**: `/api/map/tiles/{z}/x/y.png` se sirve ANTES de `_is_api_auth_valid` y `tms_y = (1 << z) - 1 - y` sin acotar `z` → `z=2147483647` asigna enteros de ~256 MB por petición simple y repetible. Acotar `0 <= z <= 22`. |
| A14 | `channels_controller.py:96-112` + `http_server.py:454` | **PSK de canales cifrados expuestos sin autenticación**: `GET /api/channels` no está en `protected_prefixes` y devuelve `{"psk": "..."}` en claro a cualquier cliente LAN. |
| A15 | `http_server.py:257-263` | Inspección de inyección en el **cuerpo HTTP muerta**: `_inspect_request_security` se invoca con `body_dict=None` antes de leer el body — la regla `INJECTION_EN_PAYLOAD` nunca recibe datos reales. |
| A16 | `index.html:20-21` | **Leaflet desde `https://unpkg.com` sin SRI** (subresource integrity) — (a) rompe autonomía offline en SBCs, (b) riesgo supply-chain: si unpkg se compromete, la CSP que lo permite habilita XSS total. `qrcode.js`/`icons.js` ya son self-hosted; Leaflet debería igualarlo. |

---

## 4. Hallazgos MEDIOS (selección por impacto)

### Backend
- `bridge_core.py:460-503` — `stop()` puede ejecutarse hasta 3 veces (run_until_complete + finally + señal) sin idempotencia garantizada.
- `mqtt_dispatcher.py:109` — cada TX MQTT crea una tarea que espera `wait_for(future, 30s)`; un flood de 500 mensajes genera 500 tareas colgadas; `CancelledError` del future no se captura.
- `mqtt_client.py:133-135` — `publish(offline)` en `stop()` sin `wait_for_publish` puede perderse (LWT lo cubre; redundante).
- `admin_handler.py:214-229` — `_wait_for_repeater_response` interroga serial cada ~1s durante 6s por comando; re-despacha eventos (dedup solo cubre frames, no eventos).
- `admin_handler.py:116-129` — fallback de `broadcast_advert` envía texto "ADVERT" como **mensaje de chat broadcast** (spam visual en canal público).
- `admin/traceroute_executor.py:50-51` — RTT calculado sin esperar el evento `TRACE_DATA`; los saltos se sintetizan del input del usuario (medición ficticia).
- `admin/local_config_executor.py:425-451` — mutación de `mc.self_info` local ANTES de confirmar el resultado del comando → desincronización RAM vs firmware ante fallo.
- `deduplicator.py:34-51` — doble lock (asyncio + threading) sobre el mismo `_cache` sin coordinación — race condition latente entre hilo y corrutina.
- `tcp_companion_server.py:242-258` — de-framing con `find(0x3C)` vulnerable a desincronización si `0x3C` aparece en payload de trama previa; limpiado total de buffer >128 bytes puede descartar tramas parciales legítimas.
- `routers/channel_handler.py:29-30` — fallback demasiado amplio: cualquier evento con texto no-direct cae al channel handler (eventos de sistema con texto incidental publicados como chat de canal).
- `routers/advert_handler.py:63` — heurística frágil: payloads de telemetría con claves largas matchean como "contact sync".
- `rx_router.py:282-287` — solo el PRIMER handler que matchea procesa; excepción en `can_handle` pierde el evento completo.
- `rate_limiter.py:367-369` — `AirtimeTracker.is_throttled` se calcula pero **nadie lo consulta antes de transmitir** (solo en `get_stats`); delay post-TX de airtime*0.1 insuficiente en SF12.
- `virtual_mesh_adapter.py:508-515` — eco a destinos desconocidos creando nodos fantasma (enmascara errores de routing en pruebas).
- `health_reporter.py:76` — `while True` sin sleep garantizado antes del catch: si `interval_sec=0` por config, busy-loop.
- `diagnostics.py:376-382` — `get_raw_log_tail` lee TODO el archivo de 5MB (deque maxlen) síncronamente desde contexto async.

### Web
- `http_server.py:813, 767-833` — `read_bytes()` de estáticos (index.html 120KB, app.css 129KB) y SQLite de tiles **síncronos en handlers async** — head-of-line blocking en SBCs.
- `http_server.py:224-244` — `_parse_request_head` sin `wait_for` en `readline()` → slowloris; sin límite de conexiones/`active_websockets`.
- `http_server.py:512-523` — WebSocket sin autenticación: cualquier navegador LAN recibe broadcast de chat/telemetría. Combinado con `GET /api/messages` y `GET /api/logs/download` (api_router.py:635-650) también sin auth → divulgación de mensajería y logs.
- `http_server.py:733-741` — CSP con `'unsafe-inline'` en script-src innecesario.
- `http_server.py:149-164` — `broadcast_event` hace `drain()` secuencial por cliente (timeout 2s c/u) — head-of-line blocking.
- `tx_controller.py:29-31` — guarda de repetidor "best-effort": solo bloquea si el repetidor está registrado; destino desconocido con rol indeterminado pasa.
- `contacts_controller.py:117-137` — `_create_or_update_contact` no valida `role` contra el enum canónico: acepta `role="REPEATER"` vía API directa (violación §1.1 explotable aunque el frontend filtre).
- `config_controller.py:86-91` — `set_local_config` devuelve 200/"ok" siempre sin inspeccionar `res.get("status")`; y L67-83 muta el dict devuelto por `get_local_config()` (contaminación de caché por referencia).
- `channels_controller.py:98-108` — cada `GET /api/channels` dispara `ser.get_channels()` (consulta activa al transceptor en cada poll) — contradice principio de recepción pasiva AGENTS.md §4.
- `system_controller.py:113-131` — `run_preflight` síncrono (pings MQTT, escaneo serial) congela el event loop.
- `api_router.py:84-90` — `asyncio.create_task(res)` fire-and-forget sin guardar referencia (GC prematuro).
- `api_router.py:38-40` — `GET /api/contacts/<cualquier-ruta-inexistente>` devuelve 200 con listado completo (rompe semántica REST).
- `api_router.py:426` — `/api/contacts/accept` fallido devuelve 200 con `status:"error"`.

### Frontend
- `nodes.js:587-606`, `map.js:370-372` — `setInterval` sin guardar id ni `clearInterval` (módulos sin `destroy()`).
- `map.js:101-114` — `NODE_UPDATED` recentra el mapa compulsivamente (`centerOnLocalNode(13)`) en cada actualización de nodo — UX rota en mallas activas; y polling de airtime duplicado (WS ya entrega `metrics_update`).
- `repeater.js:702-720` — **ráfaga de 10 comandos RF por apertura de modal** (espaciados 350ms) — coste airtime O(10) por click; contraviene §4-P1 (límites definidos unilateralmente).
- `repeater.js:551-582` — contraseñas de repetidores cacheadas en memoria y reinyectadas al reabrir (sobreviven al logout visual).
- `storage.js:84-111` — `updateMessageDelivery` abre cursor sobre TODA la tabla IndexedDB por cada ACK (O(n) por mensaje); `chat_messages` crece sin límite en disco.
- `sniffer.js:302-312` — re-render completo de 200 filas por cada paquete RF recibido.
- `index.html:1079-1090` + `app.js:188-216` — **paleta de comandos (Ctrl+K) stub muerto**: abre el modal pero nunca filtra/renderiza resultados.
- `chat.js` — `btnShareLocation` sin handler registrado (botón inerte).
- `settings.js:354-361` — `generateRandomHex` con `Math.random()` (no cripto-seguro) para PSKs de canales cifrados → usar `crypto.getRandomValues`.
- `settings.js:152` — `contactModalRole` no existe en DOM ni `_bindElements` → rol de contacto nuevo siempre "CLIENT" hardcodeado.
- `settings.js`/`map.js:21` — input de URL de tiles locales (`inputLocalTileUrl`) sin wiring: **nada escribe `meshcore_local_tile_url`** — feature de tiles personalizados no operativa.
- `nodes.js:294-464` — interpolaciones `innerHTML` sin `escapeHtml` (valores numéricos hoy; vector XSS latente si una fuente futura inyecta strings).
- `repeater.js:1159-1202` / `settings.js:120` — doble escape visible (`&amp;`) en terminal y toasts.
- i18n — cadenas hardcodeadas en español fuera del sistema i18n en `map.js:422-550`, `repeater.js:615-697` (mezcla de idiomas al cambiar a EN).

---

## 5. Arquitectura y Patrones de Diseño

### 5.1 Cumplimiento de patrones declarados (docs/ARCHITECTURE.md)

| Patrón | Módulo | Estado | Nota |
|---|---|---|---|
| Facade | `MeshCoreBridge` | ⚠️ CUMPLE con desviación | `_execute_tx` (146 líneas) retiene lógica de negocio (validación+TX+ACK MQTT+sniffer+broadcast). |
| Adapter | `serial_driver.py` | ✅ CUMPLE | `BaseSerialAdapter(abc.ABC)` real con 4 abstractmethods; 3 adaptadores sustituibles. Desviación ISP: ~15 métodos por defecto inflan la interfaz. |
| Strategy | `routers/*` | ⚠️ DESVIADO | `BaseRxHandler(Protocol)` + registro correcto, PERO las estrategias hacen callback a métodos privados del router (`ctx._handle_mesh_telemetry_msg`) y hack `getattr(ctx, "_ctx", ctx)` — acoplamiento inverso. |
| Command | `admin_handler.py` + `admin/*` | ✅ CUMPLE parcial | Despacho a executors correcto; handler retiene 646 líneas / 31 defs con métodos de ~100 líneas. |
| Repository | `NodeRegistry` | ⚠️ CUMPLE / God Class | API correcta, pero `get_analytics_summary`+`_extract_top_repeaters` son responsabilidad de analítica, no del repositorio (Feature Envy). |
| MVC Controllers | `web/controllers/*` | ✅ CUMPLE | 8 controladores por dominio + `ApiContext` (DI). Residuos: `record_incoming_event` (~122 l.) y `_route_logs` (~112 l.) viven aún en `api_router.py`. |
| Observer | Watchdog / WS Hub | ✅ CUMPLE informal | Sin bus de eventos en backend (existe solo `eventbus.js` en frontend). |
| Rate Limiter / Deduplicator | `rate_limiter.py` / `deduplicator.py` | ✅ CUMPLE | PriorityQueue + fórmula Semtech correcta; dedup con ventana deslizante. |

### 5.2 Violaciones de dependencias

1. **Acceso a miembros privados entre capas (ALTA)**: `tx_controller.py:47` (`bridge._execute_tx`), `bridge_core.py:286` (inyección post-construcción vía `rx_router._ctx`), `routers/telemetry_handler.py:46-54` (cadena `admin_handler._ctx.last_rx_rssi`, 3 niveles — Ley de Demeter), `api_router.py:73-79` (`channels_ctrl._load_channels()`).
2. **SSoT de roles roto (ALTA)**: `shared_utils.classify_device_role` se declara Single Source of Truth pero solo lo usa `serial_driver.py:1080`; `advert_handler.py:98-105`, `rx_router.py:484-499` y `contact_manager.py:448-465` reimplementan la clasificación con heurísticas de nombre divergentes — riesgo directo sobre las reglas inmutables §1.1.
3. **Contratos débiles con `Any` (MEDIA)**: `ApiContext.bridge: Any`, `RxRouterContext.serial_adapter/web_server/admin_handler: Any`, `AdminContext.web_server: Any` — los `Protocol` correctos existen (`bridge_core.py:40-62`) pero no se aplican a estos campos, socavando `mypy --strict`.
4. **Imports circulares defensivos (MEDIA)**: `TYPE_CHECKING` en los 3 executors + imports diferidos en `api_router.py:233,301` — grafo de dependencias tenso.
5. **`config` global singleton por importación (BAJA)** en 10+ módulos — DI bien hecha excepto configuración.

### 5.3 Cumplimiento de reglas inmutables AGENTS.md

| Regla | Estado | Evidencia |
|---|---|---|
| Repetidores nunca en Contactos | ⚠️ PARCIAL | `list_client_contacts` filtra ✔ (contact_manager.py:942-949), PERO `_create_or_update_contact` acepta `role="REPEATER"` vía API (contacts_controller.py:117-137). |
| NUNCA chat a repetidores/local | ⚠️ PARCIAL | Triple guarda ✔ (bridge_core.py:644-658, tx_controller.py:27-31, chat.js:453-468) PERO vulnerable a prefijos cortos (C4) y best-effort si el repetidor no está registrado. |
| Guarda de origen propio | ✅ CUMPLE | `is_outgoing` + `is_local_sender` en rx_router.py:332, 397-404; eco local filtrado. |
| Anti-spam/anti-bucle (rate limiter, dedup, backoff) | ⚠️ PARCIAL | Rate limiter y dedup implementados ✔, PERO `is_throttled` nunca se aplica, batch config sin cooldown (A8), A6 busy-loop con `None`. |
| asyncio sin bloqueantes | ❌ INCUMPLE | save_to_file en corrutina (A3), read_bytes/SQLite/preflight síncronos en handlers async, `get_raw_log_tail` O(archivo completo). |
| Persistencia atómica JSON | ✅ CUMPLE | `os.replace` sobre `.tmp` en contact_manager.py:1072 y channels_controller.py:50-53. |
| `protocol_types.py` aislado | ✅ CUMPLE | Solo importa stdlib; 7 dataclasses `frozen=True`, Enums, `Protocol` (V3/V4 verificados). |
| Frontend Vanilla sin frameworks | ⚠️ PARCIAL | SPA 100% vanilla ✔ PERO Leaflet CDN externo sin SRI (A16) + Google Fonts externas. |
| RFC 7807 Problem Details | ✅ CUMPLE | `problem_details()` en controllers/base.py con type/title/status/detail. |

### 5.4 Code smells

- **God Class**: `MeshcoreSDKAdapter` (~84 defs, ~1.063 líneas), `NodeRegistry` (~35 métodos, 1.178 líneas), `MeshCoreBridge` residual (~50 métodos), `serial_driver.py` (1.477 líneas, 4 clases).
- **Long Methods (>80 líneas)**: `rx_router._handle_mesh_telemetry_msg` (~243 l.), `_extract_normalized_meta` (~140 l.), `_handle_mesh_msg_common` (~136 l.), `serial_driver._on_sdk_event` (~133 l.), `api_router.record_incoming_event` (~122 l.), `repeater_manager._parse_json_telemetry` (~117 l.), `virtual_mesh_adapter.__init__` (~213 l.) — 10 archivos afectados.
- **Primitive Obsession**: `NodeContactInfo` con ~60 campos escalares agrupables en value objects (`RfMetrics`, `GeoPosition`, `RadioParams`, `OwnerInfo`); `_build_updated_contact` repite el patrón `update.X if ... else existing.X` ~50 veces.
- **Duplicación DRY divergente (peligrosa)**: `_get_coord` en `rx_router.py:43` (sin límite) vs `advert_handler.py:16` (con rango ±180); `_safe_int` duplicado; heurística de repetidores `startswith(("R-","R1-",...))` repetida en **5+ ubicaciones** con variantes.
- **Dead code**: `TelemetryPayload` deprecado (protocol_types.py:320-359), `_watchdog_loop` dummy "compatibilidad tests" (bridge_core.py:609-612), `_flush_offline_buffer` stub que retorna 0, `fetchDiscoveredContacts` que descarta el resultado (nodes.js:613-623), capas `darkLayer`/`cartodb` duplicadas (map.js:148-167), paleta de comandos stub.

---

## 6. Suite de Pruebas y Verificabilidad del Sistema

### 6.1 Configuración de calidad (pyproject.toml)

- pytest ✅ (`testpaths`, `asyncio_mode="auto"`, `pythonpath`), mypy `--strict` ✅, ruff ✅.
- **pytest-cov sin umbral**: `--cov=src --cov-report=term-missing` existe pero NO hay `--cov-fail-under` ni `[tool.coverage] fail_under` — la build nunca falla por cobertura insuficiente.
- `filterwarnings` ignora `DeprecationWarning` globalmente — puede enmascarar APIs obsoletas.

### 6.2 Inventario y tipos (38 archivos, ~209 funciones test, ~250 casos)

| Tipo | Volumen | Archivos |
|---|---|---|
| Unitarias | ~140 tests / ~28 archivos | protocol_types, contact_manager, lqi (5/5 públicos), packet_buffer, dedup, sensor_decoder+fuzz, rate limiter, preflight, sanitization_fixes (51 micro-tests), security, health, event_utils, target_resolver, shared_utils… |
| Integración | ~50 tests | web_server, rest_controllers (9/9 controllers), diagnostics, admin_executors (9), node_and_repeater_config (8), mqtt_subsystem (6), tcp_companion (5/5), virtual_mesh, tile_server, tx_rate_limiter |
| E2E in-process | 4 | e2e_simulation, virtual_mesh_simulation |
| E2E Playwright | 11 (condicionadas a servidor 8080) | e2e_playwright (10 flujos navegador), playwright_e2e_simulation (autocontenida) |
| Fuzzing | ~45 casos | fuzzing_and_edge_cases (≈34 param), sensor_decoder, mutation_resilience (bit-flips CRC) |
| Stress | 3 | stress_flood (500 RX / 50 TX), concurrency_and_flapping (10 hilos) |
| Mutación | 3 (tramas binarias, NO mutación de código) | mutation_resilience |

**Skips**: ~10-11 tests E2E Playwright via `pytest.skip(allow_module_level=True)` en fixture session-scoped si no hay servidor en `localhost:8080` — patrón frágil (allow_module_level dentro de fixture).

### 6.3 Matriz de cobertura por módulo

| Módulo | Estado | Qué falta |
|---|---|---|
| protocol_types, packet_buffer, lqi_engine, event_utils, health_reporter, diagnostics, sensor_decoder, target_resolver, shared_utils, mqtt_client, mqtt_dispatcher, tcp_companion, map_tile_service, security_inspector, web/controllers (9/9) | ✅ DIRECTA | — |
| contact_manager | 🟡 PARCIAL | `discover_node`, `list_discovered`, `accept_discovered_contact`, `record_packet`, `record_neighbors`, `find_by_name`, `remove_node`, `save_to_file`/`load_from_file` (persistencia sin probar), `is_repeater_key`, **`list_client_contacts`** (regla §1.1 sin verificación automática), `get_analytics_summary` |
| serial_driver | 🟡 PARCIAL | ~25 métodos SDK sin probar (`send_login`, `get_stats_*`, `device_query`, `send_path_discovery_sync`, `set_flood_scope`…), `detect_serial_port()`, `_connect_with_stabilization` (crítica de arranque), los ~25 handlers `_handle_*`, `SerialWatchdog._supervise_loop` |
| bridge_core (MeshCoreBridge) | 🟡 INDIRECTA | Sin tests directos de `start()/stop()/shutdown()/run_forever()`, `_auto_bootstrap_heltec_state`, `_reconnect_serial`, `_cleanup_loop`, `resolve_recipient_target`, `on_mqtt_connect/disconnect` |
| **rx_router** | 🔴 MUY PARCIAL | Solo 2 funciones puras. **`handle_event`, `_dispatch_parsed_frame` y todos los `_handle_mesh_*` sin pruebas aisladas** (solo indirectos vía E2E) |
| **src/routers/** (6 handlers) | 🔴 SIN PRUEBAS | Cero importaciones en tests/ — toda la estrategia de eventos RX sin cobertura aislada |
| repeater_manager | 🔴 MUY PARCIAL (~20%) | `check_airtime_cooldown`, `record_command_sent` (protección §4 sin verificación), `parse_repeater_telemetry_or_response`, 5 parsers `_parse_*` (~350 líneas), `get_repeater` |
| http_server | 🟡 PARCIAL | **`_is_api_auth_valid` SIN PRUEBAS** (autenticación API no verificada), handshake WebSocket real, `_read_websocket_frame`, `_serve_static_file`, `start()/stop()` |
| preflight | 🟡 PARCIAL | Solo serial "AUTO"; checks MQTT/versión/permisos sin probar |
| virtual_mesh_adapter | 🟡 INDIRECTA | Sin unitarios propios |
| `__main__.py` | 🔴 SIN PRUEBAS | Punto de entrada |

### 6.4 Problemas de la suite

| Severidad | Problema | Ubicación |
|---|---|---|
| ALTA | **Tests fantasma**: no importan código de producción; validan lógica re-implementada en el propio test (falsa seguridad si `src/` cambia) | `test_bridge_logic.py` (0 imports src), `test_n8n_parser_matrix.py` (0 imports src, incluye dead-code `raw_text.toLowerCase()` L67) |
| ALTA | Mutación de `config.TX_INTERVAL_SEC` global sin restaurar (riesgo de orden entre tests) | `test_tx_rate_limiter.py:35`, `test_stress_flood.py:94` |
| ALTA | Autenticación API (`_is_api_auth_valid`) y handshake WebSocket sin NINGUNA prueba — superficie OWASP no verificada | http_server.py:451,512 |
| MEDIA | `try/except pass` alrededor del assert central: tramas mutadas que lanzan excepción pasan silenciosamente | `test_mutation_resilience.py:60-64` |
| MEDIA | Tests de estructura via `hasattr`/`inspect.getsource` — frágiles, no prueban comportamiento | `test_sanitization_fixes.py:385-408` |
| MEDIA | `test_tile_server.py` no idiomático: ruta absoluta Windows hardcodeada, requiere MBTiles reales, puerto fijo 8082, `if __name__ == "__main__"` | test_tile_server.py:7,32-33 |
| MEDIA | Contradicción entre tests: uno afirma `assertFalse(hasattr(bridge, "store_and_forward"))` mientras otros lo mockean | test_store_and_forward.py:34 vs test_web_server.py:37 |
| MEDIA | Flakiness: márgenes de 200ms en eco (sleep 1.0 vs 800ms), watchdog 2×, `time.sleep(1.1)` wall-clock, 31 `wait_for_timeout` en Playwright | test_virtual_mesh_simulation.py:69, test_store_forward_modular.py:26 |
| BAJA | Solapamientos: `test_repeater_manager` ⊂ `test_node_and_repeater_config` (~90% redundante); `test_store_and_forward` ≈ `test_store_forward_modular` (kwargs legacy); `test_ha_discovery` no prueba HA; eco DM probado 3 veces; 2 vías de importación del bridge (`meshcore_bridge` vs `src.bridge_core`) | — |
| BAJA | `tearDown` manipula handlers del logger raíz global; fixtures con `new_event_loop()` manual mezcladas con `asyncio_mode="auto"`; `tests/artifacts/` creado en import-time | test_diagnostics_export.py:28-33 |

### 6.5 Verificación de "¿cada función tiene su prueba unitaria?"

**No.** La cobertura por función es desigual:
- **Bien cubiertas (≈90-100%)**: `LinkQualityEngine` (5/5 funciones públicas), `protocol_types`, `packet_buffer`, `tcp_companion_server` (5/5), `web/controllers` (9/9), `lqi_engine`, `event_utils`, `target_resolver`, `shared_utils`, `deduplicator`, `sensor_decoder`.
- **Parciales (≈40-60%)**: `NodeRegistry` (~15/35 métodos), `MeshcoreSDKAdapter` (~5/84 defs), `MeshCoreBridge` (indirecta), `AdminCommandHandler` (parcial), `preflight`.
- **Huecos críticos (0-20%)**: `RxEventRouter.handle_event` + `_handle_mesh_*`, **los 6 handlers de `src/routers/`** (0 pruebas), `RepeaterManager` (solo `build_repeater_command_payload`), `_is_api_auth_valid`, handshake WebSocket, `check_airtime_cooldown`, persistencia `save_to_file/load_from_file`, ciclo de vida completo del bridge.

### 6.6 ¿Se puede comprobar TODO el sistema con las pruebas existentes?

**NO — verificabilidad estimada ~60-65%.** La suite es amplia y de buena calidad en utilidades puras y API REST, pero el sistema NO es verificable al 100% porque:
1. El **pipeline RX completo** (router + 6 estrategias) no tiene pruebas aisladas — un refactor ahí puede romper silenciosamente (los tests "fantasma" no lo detectarían).
2. El **orquestador central** (`MeshCoreBridge`) no tiene tests de ciclo de vida/bootstrap/reconexión.
3. La **seguridad web** (API key, WebSocket auth) — precisamente donde está el hallazgo C1 — carece de toda verificación automática.
4. La **protección de airtime LoRa** (§4 AGENTS.md, donde están A6/A8) no tiene tests.
5. No existe umbral de cobertura (`--cov-fail-under`) que impida regresiones silenciosas.

---

## 7. Optimización y Rendimiento (resumen)

1. **Event loop bloqueado** (violación directa directivas): `save_to_file` (A3), `read_bytes` estáticos, SQLite tiles, `run_preflight`, `get_raw_log_tail` — todos candidatos a `asyncio.to_thread()`.
2. **O(n²) potencial**: lookups de prefijo en `NodeRegistry` (A5); `_collect_target_info` reconstruye `to_dict()` de todos los nodos por comando admin.
3. **Sin límites**: registro de nodos sin `cleanup_inactive` programado (A4); `chat_messages` IndexedDB ilimitado; sin límite de conexiones HTTP/WS concurrentes.
4. **Frontend**: re-render completo del sniffer por paquete; `updateMessageDelivery` O(n) por ACK; recentrado compulsivo del mapa; polling redundante de airtime; ráfaga de 10 comandos RF por modal de repetidor.
5. **Broadcast WS secuencial** (`drain()` por cliente) — paralelizar con `asyncio.gather`.
6. **Desperdicio silencioso**: bytes de estáticos releídos de disco en cada petición (sin cache en RAM para SBCs).

---

## 8. Plan de Remediación Priorizado (recomendado, sin cambios aplicados)

| Prioridad | Acción | Hallazgos |
|---|---|---|
| P0 (inmediato) | Fail-closed en API key (401 si no configurada) | C1 |
| P0 | Resolver target a clave canónica ANTES de guardas repetidor/local | C4 |
| P0 | Corregir `UnboundLocalError` (`is_admin_cmd` definido fuera del bloque) | C2 |
| P0 | Eliminar asignación a property `self_info` (guardar en `self._self_info_cache` con setter o atributo distinto) | C3 |
| P1 | Contrato DELETE contactos (leer pubkey de URL o body) + verificar `res.ok` en UI | A12 |
| P1 | Acotar `z/x/y` en tiles + mover despacho de tiles tras la autenticación | A13 |
| P1 | Suscribir `admin/repeater/+/cmd` o eliminar rama muerta | A1 |
| P1 | Mover I/O a `asyncio.to_thread()` (save_to_file, estáticos, tiles, preflight, log tail) | A3 + §7.1 |
| P1 | Sanitizar PSK en respuestas GET + auth en `/api/logs/download` y `/api/messages` | A14, §4-web |
| P2 | Self-host de Leaflet con SRI | A16 |
| P2 | Aplicar `check_airtime_cooldown` en batch config; aplicar `is_throttled` en el worker; arreglar busy-loop `None` | A8, A6, §4 |
| P2 | `cleanup_inactive` programado + `asyncio.to_thread` en persistencia | A4 |
| P2 | Unificar clasificación de roles en `shared_utils.classify_device_role` (SSoT) | §5.2-2 |
| P3 | Tests directos para `src/routers/*` + `rx_router.handle_event` + `_is_api_auth_valid` + `check_airtime_cooldown` + ciclo de vida del bridge | §6.3-6.5 |
| P3 | Umbral `--cov-fail-under` en pyproject; eliminar/reescribir tests fantasma contra código real; `monkeypatch` para config global | §6.4 |
| P3 | Descomposición God Classes (SDKAdapter, NodeRegistry, `_handle_mesh_telemetry_msg`); extraer analítica del repositorio; agrupar `NodeContactInfo` en value objects | §5.4 |
| P3 | Frontend: paleta de comandos funcional o eliminada; wiring de `btnShareLocation`/`inputLocalTileUrl`; `crypto.getRandomValues` para PSKs; `escapeHtml` en interpolaciones pendientes; i18n completo | §4-frontend |

---

## 9. Conclusión Final

**MeshCore Bridge v3.0 es un proyecto de madurez arquitectónica sólida (B+)**: la separación en capas es real, los patrones declarados existen y funcionan (con desviaciones documentadas), las reglas inmutables críticas están implementadas en triple capa, la persistencia es atómica, `deploy/` está 100% sincronizado y no existe código truncado ni errores de sintaxis en ningún archivo.

**Sin embargo, no está listo para considerarse verificable ni seguro al 100%**:
- 4 defectos críticos (1 fail-open de seguridad, 1 bypass de regla inmutable, 2 bugs de lógica enrutinas centrales) requieren corrección inmediata.
- La suite de pruebas (227 tests) es fuerte en API REST y utilidades puras pero deja sin cobertura precisamente las zonas de mayor riesgo: pipeline RX, ciclo de vida, autenticación y protección de airtime.
- La deuda de optimización (event loop bloqueado en 6+ puntos, God Classes, O(n²)) es manejable pero acumulativa en SBCs.

**El sistema puede verificarse de forma confiable en ~60-65% de su comportamiento con las pruebas actuales**; el 35-40% restante (radio routing, seguridad perimetral, ciclo de vida) depende de verificación manual hasta cerrar los huecos identificados en §6.

---

*Reporte generado por análisis multi-agente (Agente 0 Lead Orchestrator, Agente 2 Bridge Architect, Agente 4 Web Architect, Agente 5 Security Auditor, Agente 3 QA) con verificación manual de hallazgos críticos. Sin modificaciones aplicadas al código.*
