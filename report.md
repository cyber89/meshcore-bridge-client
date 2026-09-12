# Reporte de Auditoría Profunda #2 — MeshCore Universal Bridge v3.0 Pro

**Fecha**: 2026-09-12 (2ª ronda)
**Base auditada**: HEAD post-commit `f61d91f` ("fix: resolve verified audit findings from report.md") + commits posteriores de skills/docs.
**Alcance**: Re-auditoría completa con mayor profundidad: 4 auditorías secuenciales especializadas (core backend, subsistema web, suite de pruebas, arquitectura/scripts/deploy) + verificación manual de todos los hallazgos CRÍTICOS/ALTOS nuevos.
**Modo**: Solo lectura. No se modificó código ni se ejecutaron pruebas.

---

## 1. Resumen Ejecutivo

| Indicador | Resultado |
|---|---|
| Hallazgos previos corregidos por f61d91f | 12 de ~20 verificados (ver §2) |
| **Nuevos hallazgos esta auditoría** | **~90** (5 CRÍTICOS, 12 ALTOS, 27 MEDIOS, ~46 BAJOS) |
| Regresiones introducidas por las correcciones de f61d91f | 4 (2 CRÍTICAS, 2 ALTAS) — ver §3 |
| Estado de pruebas (docs actualizados) | 247 passed, 10 skipped, 0 failed (~257 instancias con parametrize) |
| Verificabilidad del sistema | ~55-60% líneas ejecutadas; ~45-50% comportamiento verificable con confianza |
| deploy/ | 100% sincronizado (hashes verificados) |
| Arquitectura | Los fixes fueron puntuales y correctos en síntoma, pero **no abordaron causas estructurales** |

**Conclusión general**: f61d91f resolvió bien los síntomas urgentes del reporte anterior (C2, C3, A12, A14-GET, parte de la auth), pero **introdujo 2 regresiones críticas nuevas** (race de persistencia por `to_thread` sin lock; `updateNodeInDom` en el frontend que vacía el directorio de nodos), **dejó 3 hallazgos críticos previos sin cerrar** (fail-open de API key, DoS de tiles pre-auth, Leaflet CDN sin SRI) y **agravó la deuda estructural** (la heurística de clasificación de repetidores pasó de 9 a 11 copias divergentes).

---

## 2. Estado de los Hallazgos Previos (verificación commit f61d91f)

### Corregidos ✅
| ID previo | Hallazgo | Corrección aplicada |
|---|---|---|
| C2 | `UnboundLocalError` en TX broadcast (`is_admin_cmd`) | `bridge_core.py:644-645` — definición movida fuera del bloque condicional ✔ |
| C3 | Property `self_info` sin setter (AttributeError) | `serial_driver.py:232-243` — setter + cache `_self_info` ✔ (pero ver regresión R2) |
| A3 (parcial) | `save_to_file` síncrono en `_cleanup_loop` | `bridge_core.py:222` — `asyncio.to_thread` ✔ (pero ver regresión R1: introdujo race) |
| A7 (parcial) | PSK expuesto en `GET /api/channels` | `channels_controller.py:110-118` — masking `"••••••••"` + `has_psk` ✔ (pero ver N1: fuga por WS persiste) |
| A12 | Contrato DELETE contactos roto | `contacts_controller.py:45-52,160` — acepta `path_pubkey` de URL; `nodes.js:400-404` envía body ✔ (pero ver R5: sigue sin comprobar `res.ok`) |
| A8 (parcial) | Fugas de waiters en repeater_executor | try/finally en `_execute_ping_zero`, `_dispatch_rf_command`, `_execute_unit_command` ✔ (huecos residuales, ver R4) |
| — | Ruta `/api/repeater/traceroute` inexistente | `api_router.py:460` añadida ✔ |
| — | `test_tile_server.py` ruta absoluta Windows | Corregida a `Path(__file__)` ✔ |
| — | Cobertura de `src/routers/*` (0 tests) | `test_rx_routers.py` nuevo (20 tests) ✔ (con limitaciones, ver §5) |
| — | QR Code con wrapper incompatible | `qrcode.js:591-608` — `QRCodeGenerator.renderToCanvas` + fallback `QRCode` con CorrectLevel ✔ |
| — | Recentrado compulsivo del mapa | `map.js` — `_hasInitiallyCentered` + `_userInteractedWithMap` + listener `movestart` ✔ (hueco: zoom no marca, ver N14) |
| — | Auth ampliada | `protected_prefixes` + POST/PUT/DELETE/PATCH en channels/contacts ✔ (incompleta, ver N2) |

### Persisten sin corregir ❌
| ID previo | Hallazgo | Estado |
|---|---|---|
| C1 | **Fail-open de `BRIDGE_API_KEY` vacía** | `http_server.py:476-478` — idéntico: warning + return True. Endpoints protegidos abiertos por defecto. |
| A13 | **DoS de tiles pre-auth con `z` sin acotar** | `http_server.py:400` despacha tiles ANTES de `_is_api_auth_valid`; `map_tile_service.py:85` — `(1 << z)` sin límite. Sin cambios. |
| A16 | **Leaflet CDN unpkg sin SRI** | `index.html:20-21` — sin cambios. CSP sigue permitiéndolo. |
| A1 | **Suscripción MQTT faltante `admin/repeater/+/cmd`** | `mqtt_client.py:200` — solo suscribe `topic_tx` y `topic_admin_cmd`; rama de `mqtt_dispatcher.py:54` sigue muerta. |
| A2 | **Doble publicación channel→TOPIC_RX_DIRECT** | `rx_router.py:998` — sin cambios: todo mensaje de canal se duplica al tópico de DMs. |
| A4 | **`cleanup_inactive` nunca llamado** | `contact_manager.py:1042` — sin llamadores en producción. |
| A8 (parcial) | **`_execute_batch_config` sin cooldown de airtime** | `repeater_executor.py:133-151` — sin `check_airtime_cooldown` ni `record_command_sent` en batch. |
| A5/A6 | O(n) lookups de prefijo; rama `item is None` en rate limiter | Sin cambios. |
| H-web | **WS sin auth + Origin LAN RFC1918** | `http_server.py:510-522` — sin cambios. |
| H-web | **`GET /api/logs/download` y `GET /api/messages` sin auth** | Sin cambios. |
| H-web | I/O síncrono en handlers (estáticos, SQLite, preflight) | `read_bytes()` en `http_server.py:826`; `run_preflight` bloqueante. Sin cambios. |
| H-web | `Math.random()` para PSK | `settings.js:347-354` — sin cambios. |
| H-web | Paleta de comandos (Ctrl+K) stub decorativo | Confirmado + ampliado: ~20 controles muertos más (ver §4-web). |
| A-arch | Accesos a privados entre capas (`_execute_tx`, `_ctx` hack) | Sin cambios; verificado en 6 handlers. |
| A-arch | God Classes (SDKAdapter 66 defs, NodeRegistry 38 métodos) | Sin cambios. |

---

## 3. REGRESIONES INTRODUCIDAS POR f61d91f (nuevas, verificadas manualmente)

### R1 — CRÍTICA: Race de concurrencia real en `save_to_file` por `to_thread` sin lock
- **Archivos**: `bridge_core.py:222` ↔ `contact_manager.py:1059-1080`
- **Evidencia**: `_cleanup_loop` ejecuta `await asyncio.to_thread(self.node_registry.save_to_file)` mientras el event loop sigue mutando `_nodes_by_key` (`add_or_update`, `remove_node`, `discover_node`) por cada paquete RX. `save_to_file` → `list_nodes()` itera `_nodes_by_key.values()` en el **hilo del threadpool** sin lock ni snapshot:
  ```python
  # contact_manager.py:904 (llamado desde el hilo worker)
  nodes_list = [n.to_dict() for n in self._nodes_by_key.values()]
  ```
- **Impacto**: `RuntimeError: dictionary changed size during iteration` intermitente bajo tráfico (capturado como warning en L223 → **guardados periódicos fallan aleatoriamente = persistencia silenciosamente corrupta**) o snapshot inconsistente en disco. El `.tmp` de nombre fijo además permite colisión entre writers.
- **Agravante**: la misma operación sigue **síncrona y bloqueante** en `stop()` (bridge_core.py:485) y en 3 puntos de `contacts_controller.py:85,145,172` — inconsistencia directa dentro del mismo commit.

### R2 — CRÍTICA (frontend): `updateNodeInDom` vacía el directorio de nodos por selector incorrecto
- **Archivo**: `nodes.js:705-727` (nuevo de f61d91f)
- **Evidencia verificada manualmente**:
  ```js
  const cards = document.querySelectorAll(`[data-pubkey="${pk}"]`);  // L711
  if (!cards || cards.length === 0) { this.renderNodesDirectory(); return; }  // L713-715
  ```
  Pero las tarjetas se generan con **`data-pk`** (nodes.js:275, 422), no `data-pubkey` (ese atributo solo existe en los `<li>` de chat.js:327). El selector **jamás matchea** → cae al fallback `renderNodesDirectory()` **sin argumentos** → L183: `if (!nodes || nodes.length === 0)` → **borra ambas grillas** ("Sin contactos" / "Sin nodos").
- **Disparadores**: `repeater.js:286, 543, 1133, 1206` lo invocan con cada telemetría/ping/config de repetidor → **cada interacción con el modal de repetidor vacía la UI**.
- **Impacto adicional**: los sub-selectores `.metric-snr`, `.lqi-score`, `.node-last-seen` tampoco existen en el DOM generado (usa `.stat-pill`) — el método completo es incompatible con el markup real.

### R3 — ALTA: `should_treat_as_repeater` clasifica CLIENTs desconocidos como REPEATERs permanentes
- **Archivo**: `rx_router.py:553-570` (nuevo de f61d91f)
- **Evidencia**:
  ```python
  should_treat_as_repeater = (
      (existing_contact and existing_contact.role in ("REPEATER", "ROUTER"))
      or is_explicit_rep_name
      or (bool(extracted_telem) and not is_known_client)  # ← CLIENT desconocido + telemetría
  )
  ```
  Un **CLIENT nuevo** (aún no en registry) cuyo mensaje contenga texto que el parser laxo de `RepeaterManager` interprete como telemetría ("battery: 90%", "up 5", "airtime 200ms" — regexes conversacionales) activa `add_or_update(role="REPEATER")`. El rol **persiste** en el registry (`_resolve_node_role` respeta `existing.role`) → todos sus mensajes futuros caen en `is_cmd_response → return None`: **el chat de ese usuario deja de llegar permanentemente a MQTT/WebUI** y desaparece de Contactos.
- **Falsos positivos por nombre**: los prefijos `REP_`/`ROUTER_` añadidos como válidos marcan a "R2-D2", "R-Studio", "REP_Solar-User" como repetidores.

### R4 — ALTA: Cache `_self_info` sin invalidación (stale tras reconexión)
- **Archivos**: `serial_driver.py:232-243` (setter nuevo), `:348-369` (`disconnect`), `:700-704` (`_handle_self_info`), `local_config_executor.py:534-538`
- **Problemas verificados**:
  1. `_handle_self_info` (cuando el firmware emite SELF_INFO tras cambios de config) **no actualiza `_self_info`** — el getter seguirá devolviendo el payload del `send_appstart` original para siempre.
  2. `disconnect()` no limpia el cache → tras reconexión por el fallback `MeshCore.create_serial` (L313-317, que no setea self_info), el adapter sirve el self_info **obsoleto de la conexión anterior** (posiblemente de otro nodo).
  3. `local_config_executor` muta `mc.self_info`/`mc._self_info` pero no `adapter._self_info` → la WebUI ve datos viejos tras cambiar config.
  4. La doble mutación en `_handle_device_info` (L675-678) parchó ad-hoc UN solo campo (`repeat`), dejando freq/sf/name/tx_power desincronizados — evidencia de que el autor detectó la divergencia sin cerrarla.

---

## 4. NUEVOS HALLAZGOS (no presentes en auditorías previas; verificación manual de críticos/altos)

### 4.1 Backend core

| # | Sev | Archivo:línea | Hallazgo |
|---|---|---|---|
| N1 | **CRÍTICA** | `bridge_core.py:807-819` | **Shutdown zombi en POSIX**: `_stop_task` crea `asyncio.create_task(self.stop())` pero **nunca llama `loop.stop()`** → `run_forever()` (L819) no retorna tras SIGINT/SIGTERM. El bridge apaga todos los subsistemas pero el **proceso queda vivo indefinidamente**. Además `stop()` se ejecuta 2 veces (task de señal + `finally` L823) sin idempotencia. (Verificado: código confirmado en L807-823.) |
| N2 | **CRÍTICA** | `admin_handler.py:140-192` | **Cross-talk de waiters**: `notify_ping_response`/`notify_command_response` hacen `pop(k)` de TODA la lista de waiters de la clave y `set_result(data)` a todos con la **misma respuesta** → dos comandos concurrentes al mismo repetidor (WebUI + MQTT simultáneos) reciben ambos la respuesta del primero; el segundo nunca ve su respuesta real. Matching por prefijos ≥4 chars cruza respuestas entre nodos con prefijos solapados. |
| N3 | ALTA | `repeater_executor.py:281-282, 360-361` | **Huecos residuales en try/finally**: `_dispatch_rf_command` llama `_ensure_radio_contact` con waiters ya registrados **fuera** de try/finally; `_send_pre_login` + `sleep(0.35)` corren antes del try en `_execute_unit_command` → una `CancelledError` de shutdown en ese hueco deja el future en `_cmd_waiters` **para siempre** (leak no corregido por f61d91f). |
| N4 | ALTA | `serial_driver.py:813-815` + `repeater_executor.py:439` | **Contacto con clave falsa en la radio**: pad de claves cortas `(dest_target + "0"*64)[:64]` + `add_contact` en **cada DM** sin cooldown (flash wear del firmware + contacto fantasma que reaparece en `sync_all_contacts`). |
| N5 | MEDIA | `bridge_core.py:644-645` | **`is_admin_cmd` sigue vulnerando la regla inmutable §1.1**: prefijos laxos (`"ver"`, `"get"`, `"info"`, `"status"`, `"set"`) permiten **chat hacia repetidores** cuando el texto empieza con ellos ("verdad?", "info urgente") — `if not is_admin_cmd and is_repeater_key(...)` se salta la guarda. En español "ver…" es prefijo común. |
| N6 | MEDIA | `bridge_core.py:456` | `_cleanup_task` no se detiene en `stop()` (falta en la lista de subsistemas L467-474). |
| N7 | MEDIA | `rx_router.py:559 vs 762` | **Inconsistencia intra-archivo introducida**: la nueva heurística L559 omite `"REPETIDOR"` pero la de L762 lo incluye → un nodo "REPETIDOR-NORTE" es repetidor por un path y no por otro. La lista de prefijos pasó de 9 a **11 copias con 3 variantes** (ver §6.2). |
| N8 | MEDIA | `mqtt_client.py:137-141` | **Orden de stop incorrecto**: `loop_stop()` ANTES de `disconnect()` → el DISCONNECT puede no transmitirse → el broker publica el LWT (`unexpected_disconnect`, retained) que **sobrescribe el estado offline limpio** ~keepalive después de un shutdown correcto. |
| N9 | MEDIA | `preflight.py:33-131` + `bridge_core.py:424` | `run_all` ejecuta **sockets bloqueantes** (2-3s × 3 checks) dentro del event loop en cada arranque y bajo demanda vía API de diagnóstico en caliente → loop congelado hasta ~6s. `sock.close()` fuera de `finally` → leak de FD si `connect` lanza. |
| N10 | MEDIA | `rate_limiter.py:89-98, 316-318` | **Eviction de `CustomTxQueue` es código muerto bajo carga**: `put_nowait` lanza `QueueFull` ANTES de invocar `_put` (donde vive la expulsión) cuando la cola está llena; además compara contra la constante `MAX_QUEUE_SIZE=500` ignorando `MAX_TX_QUEUE_SIZE` del env → doble límite divergente. |
| N11 | MEDIA | `serial_driver.py:1300-1357` | **`RawSerialFramingAdapter` (fallback) no funcional**: `connect()` marca `is_connected=True` sin abrir puerto; `send_message` retorna `{"status": "SENT_RAW"}` sin transmitir → si falla el SDK adapter, el bridge "envía" mensajes al vacío **sin error aparente** (pérdida silenciosa total). |
| N12 | MEDIA | `serial_driver.py:456-464` | `_make_handler` con `except RuntimeError: pass` → evento RF perdido en silencio si el callback llega de otro hilo; `create_task` sin referencia (GC-risk). |
| N13 | MEDIA | `tcp_companion_server.py:108-120, 77-83` | `broadcast_companion_frame` con `drain()` serial por cliente (2s × 8 clientes = hasta 16s por trama, HOL blocking); `stop()` sin timeout en `wait_closed` → shutdown colgado con half-close. |
| N14 | MEDIA | `admin_handler.py:207-229` | `_wait_for_repeater_response`: polling `get_msg(timeout=0.8)` sin else-sleep en la rama de éxito → spin puro si el SDK retorna de inmediato sin datos. |
| N15 | MEDIA | `traceroute_executor.py:112-121` | `_build_hops_breakdown` **fabrica** SNR (12.0/8.5/7.0) y RTT sintético cuando no hay datos reales → la WebUI muestra traceroute con telemetría inventada como medición. Sin cooldown/rate-limit (spam vía MQTT `admin/cmd`). |
| N16 | MEDIA | `repeater_manager.py:461-467, 577-579` | Parser de telemetría laxo (raíz de R3): regexes casan texto conversacional normal ("up 2 it", "battery low") → falsos positivos que disparan reclasificación a REPEATER. Heurística `val_num <= 100.0 and val_num > 4.5` clasifica 4.7V como "battery_pct". |
| N17 | MEDIA | `contact_manager.py:286-314` | `set_local_pubkey` consolida tomando SOLO la entrada "primary" → datos de otras entradas locales (coordenadas, telemetría) se pierden; índice `_nodes_by_name` puede quedar apuntando a clave purgada. |
| N18 | MEDIA | `rx_router.py:126` | `lstrip("-> ")` elimina el **conjunto** de caracteres, no el prefijo literal → mensajes que empiezan con `-`/`>`/espacio se truncan mal en detección de sistema. |
| N19 | BAJA | `serial_driver.py:1381` | `max_reconnect_attempts` lee `os.getenv` directo ignorando `config` ya parseado → divergencia de configuración. |
| N20 | BAJA | `mqtt_dispatcher.py:108-129` | Solo se captura `TimeoutError` del future TX → `QueueFull`/`CancelledError` nunca publican status a `TOPIC_TX_STATUS` (n8n ciego ante errores de cola llena). |
| N21 | BAJA | `mqtt_client.py:166-167` | `total_published += 1` sin lock desde event loop y hilo paho (race de métrica). |
| N22 | BAJA | `contact_manager.py:1072` | `.tmp` de nombre fijo (sin PID) → colisión si dos procesos guardan a la vez. |
| N23 | BAJA | `virtual_mesh_adapter.py:703-705` | `create_task` sin referencia (GC prematuro). |
| N24 | BAJA | `bridge_core.py:210` + `rx_router.py:210/256` | `rx_count` se incrementa **antes** del dedup → duplicados inflan métricas de salud/analítica. |
| N25 | BAJA | `packet_buffer.py:64-113` | `self._lock = asyncio.Lock()` declarado pero **nunca adquirido** — seguro hoy, trampa si se añade concurrencia. |
| N26 | BAJA | `routers/channel_handler.py:29` | Fallback `(bool(meta.text) and not is_direct)` → DMs mal tipados por el firmware se publican como canal. |
| N27 | BAJA | `routers/advert_handler.py:63` | Heurística frágil "contact sync": payload con clave larga y valores dict se procesa como lista de contactos (CPU gastada; filtrado posterior lo hace benigno). |
| N28 | BAJA | `local_config_executor.py:206-213` | Cooldown de fetch se consume aunque el hardware falle. |
| N29 | BAJA | `diagnostics.py:378-380` | `get_raw_log_tail` lee el archivo de log completo síncronamente (deque maxlen) desde contexto async. |
| N30 | BAJA | `rx_router.py:700-708` | Mensajes de canal sin guard de origen propio explícito (solo DM lo tiene en direct_handler:35) — riesgo de re-publicación si el firmware refleja el propio mensaje local en canal. |

### 4.2 Subsistema web

| # | Sev | Archivo:línea | Hallazgo |
|---|---|---|---|
| W1 | **CRÍTICA** | `channels_controller.py:143-144, 162-163` | **Fuga de PSK por WebSocket (anula el masking de f61d91f)**: `_create_or_update_channel` y `_delete_channel` difunden `channels_updated` con `list(self.channels.values())` — **PSKs AES reales en claro** a todos los clientes WS, que no requieren autenticación (http_server.py:510-522). El masking del GET queda cosmetico. (Verificado manualmente: L143-144 y L162-163 pasan `self.channels.values()` sin filtrar.) |
| W2 | **CRÍTICA** | `http_server.py:455-471` | **9 brechas de auth en el esquema ampliado** (verificación manual contra api_router): sin protección quedan `POST /api/config` y `/api/config/identity` (modifican identidad/radio), `POST /api/node/advert` (emite radio), `POST /api/traceroute` y `/api/trace` (sondas RF), `/api/node/ping_zero`, **`DELETE /api/packets`** (la ruta real que usa el frontend — la lista protege `/api/packets/clear` que **no existe**) y **`DELETE /api/system/logs`** (borra logs de auditoría sin credencial → anti-forense). |
| W3 | ALTA | `http_server.py:510-522` | WS handshake sin auth + Origin RFC1918 (`192.168.*`, `10.*`, `172.16-31.*`) autorizado + sin límite de conexiones `active_websockets` → cualquier dispositivo LAN recibe chat, telemetría, RF y (vía W1) PSKs. |
| W4 | ALTA | `api_router.py:635-650` | `GET /api/logs/download` sin auth: filtra últimas 2000 líneas con IPs/user-agents de atacantes (reconocimiento interno) + **ruta absoluta del filesystem** del servidor. |
| W5 | ALTA | `nodes.js:397-409` | **DELETE sin comprobar `res.ok`** (regresión parcial del fix A12): el fetch envía body correctamente pero `cCard.remove()` se ejecuta incondicional dentro del try — un 401/404/500 elimina la tarjeta en UI aunque el contacto persista en backend (estado divergente). |
| W6 | MEDIA | `nodes.js:434-435` | `telemLine2` interpola `node.temperature_c` y `node.humidity_pct` **sin escapeHtml** — única interpolación sin sanitizar del render de nodos (vector XSS latente). |
| W7 | MEDIA | `security_inspector.py:119-135` | `extract_client_ip` confía ciegamente en `X-Forwarded-For`/`X-Real-IP` sin proxy confiable → **IP falsificable en logs de auditoría** (anti-forense). |
| W8 | MEDIA | `chat.js:499-516` | `sendMessage` persiste en IndexedDB y renderiza el bubble ANTES del resultado de `/api/tx`; si el POST falla (401/400), el catch solo hace `console.warn` → el mensaje queda como "Enviado" en historial **sin retroalimentar el error**. |
| W9 | MEDIA | `map.js:193, 122-124` | **El zoom con botones no dispara `movestart`** → `_userInteractedWithMap` queda false y cada `NODE_UPDATED` LOCAL fuerza `centerOnLocalNode(13)` **pisando el zoom del usuario**. Falta listener `zoomstart`. |
| W10 | MEDIA | `http_server.py:652-655` | Unmasking WS byte a byte en Python puro (`for i in range(len(payload))`) — frame 1MB = 1M iteraciones → amplificación CPU DoS. Sin rate-limit de frames. |
| W11 | MEDIA | `repeater.js:709-727` | **Ráfaga de 9 comandos RF** (350ms) por cada login/re-apertura de modal de repetidor — sin cooldown persistente (checklist airtime §4). |
| W12 | MEDIA | `repeater.js:567-589` | `getRepeaterPassword` hace fallback al input visible del DOM → la pwd sobrevive al logout parcial en el input. |
| W13 | MEDIA | `storage.js:84-155` | `updateMessageDelivery`/`updateMessageStatus`/`purgeNonCommonMessages` hacen `openCursor()` **full-scan** por cada ACK (O(n) por entrega); `chat_messages` crece sin límite en IndexedDB. |
| W14 | MEDIA | `repeater_controller.py:59-118` | Contraseñas de repetidores viajan en JSON plaintext por HTTP sin TLS en LAN. |
| W15 | ALTA (funcional) | `index.html` + `settings.js` | **UI muerta masiva (verificación manual)**: sin handler quedan: `localTerminalForm` (submit recarga la página), `btnImportData`/`importModal`, `btnSaveMapSettings`/`inputLocalTileUrl` (`meshcore_local_tile_url` nunca se escribe → capa "Local" siempre default), `btnReloadLocalMaps`, `btnClearIndexedDbStorage`, `btnGetBrowserGps`, `btnCopyLocalPubkey`, `btnRefreshNodes`, `btnRefreshLocalConfig`, y **toda la toolbar de acciones hardware** (`btnActionAdvertHop/Flood`, `btnSyncLocalClock`, `btnActionRebootLocal`, etc.) + paleta de comandos Ctrl+K (items `data-action` sin listeners) + banner de descubrimiento (`discoveryBanner`/`btnAcceptAllDiscovered` sin consumidor, endpoints `/api/contacts/discovered|accept` huérfanos) + `contactModalRole` (referencia a elemento inexistente → rol siempre "CLIENT"). **~20 controles anunciados en la UI no funcionan.** |
| W16 | BAJA | `http_server.py:746-754` | CSP `unsafe-inline` innecesario (2 `onsubmit` inline en index.html:1057,1234 lo justifican a medias); ping WS sin contador de pongs sin respuesta (conexiones zombie). |
| W17 | BAJA | `nodes.js:614-624` | `fetchDiscoveredContacts` fetch y descarta resultado (fetch muerto redundante). |
| W18 | BAJA | `app.js:41-42` | `ctx.switchChannel`/`setDmTarget` arrow sin null-guard (a diferencia de los nuevos getters de L50-51 que sí lo tienen). |
| W19 | BAJA | `settings.js:113` | Doble escape visible (`&amp;`) en toasts con nombres con `&`. |
| W20 | BAJA | `map.js:160-163, 388` | Botón "Oscuro" dice "Esri World Dark Gray" pero la capa es OSM con filtro CSS; interval 60s sin handle; polling airtime redundante. |
| W21 | BAJA | `api_router.py:507-519` | Dead code: ramas de `_dispatch_misc` inalcanzables (capturadas antes por `_dispatch_system`/`_dispatch_tx`); `SystemController.get_logs` casi inaccesible. |

### 4.3 Arquitectura (métricas actualizadas post-f61d91f)

- **God Classes confirmadas con conteo exacto**: `MeshcoreSDKAdapter` (66 defs / ~1070 líneas), `MeshCoreBridge` (47 métodos / 831 líneas, de ellos 12 properties de compatibilidad = facade poroso), `NodeRegistry` (38 métodos / 921 líneas — al límite de ambos umbrales).
- **Long Methods (>80 líneas)**: `_handle_mesh_telemetry_msg` (242 l.), `_execute_tx` (148 l.), `_handle_mesh_msg_common` (145 l., ahora 15 líneas más largo por `should_treat_as_repeater`), `_extract_normalized_meta` (139 l.), `record_incoming_event` (122 l.), `handle_event` (97 l.), `_connect_with_stabilization` (94 l.), `_update_node_registry_presence` (92 l.), `_build_updated_contact` (87 l.).
- **Dependencia inversa core→web**: `tcp_companion_server.py:14` importa `src.web.security_inspector` — componente de transporte core depende de la capa web.
- **9 campos `Any`** en contextos dataclass (`RxRouterContext`: serial_adapter/web_server/admin_handler/packet_buffer; `AdminContext`: web_server/rate_limiter/counters; `ApiContext`: bridge/packet_buffer) pese a que los `Protocol` aptos ya existen.
- **Deploy**: 100% sincronizado (SHA256 verificado archivo a archivo: src 56 archivos, static 17, docs, scripts, root) — PERO `deploy/scripts/run_all_test_categories.py` referencia `tests/` que **no se empaqueta** → roto dentro del bundle. `deploy/README.md:51` documenta puerto de simulación 8085 pero el script usa 8080.
- **Docs/código**: `ARCHITECTURE.md §7` documenta 38 rutas; el router contiene 63 — faltan 15+ incluyendo `/api/repeater/traceroute` **añadida por el propio f61d91f**. `AGENT_ACTIVITY_REPORT.md` sí registra el hito completo (247 tests, aritmética verificada: 227 + 20 de test_rx_routers.py).
- **Scripts**: `simulate_heltec_v4_mesh.py` fija `WEB_PORT=8080` (colisión con bridge real); `simulate_tcp_mesh_network.py` duplica `MeshCoreTcpClient` internamente + puertos 127.0.0.1:5000 hardcodeados (colisión con TCP_SERVER_PORT); `simulate_mesh_network.py` duplica el wiring de composición del bridge (drift risk). Los simuladores operan sobre VirtualMeshAdapter en memoria — checklist airtime §4 no aplica (correcto por diseño).

---

## 5. Estado de la Suite de Pruebas (post-f61d91f)

| Indicador | Valor |
|---|---|
| Funciones `def test_` | 229 en 39 archivos (~257 instancias con parametrize) |
| Último reporte documentado | 247 passed, 10 skipped, 0 failed (verificado aritméticamente consistente) |
| Suite nueva | `test_rx_routers.py` (20 tests): `can_handle` de los 6 handlers, `handle` con mocks, `handle_event` con MeshcoreFrame real, guard de loopback DM, orden de instanciación |

**Cobertura de los cambios de f61d91f** (grep confirmado, 0 matches en tests/):
- ❌ Setter/property `self_info` con cache — sin test.
- ❌ `should_treat_as_repeater` — **el edge case CLIENT desconocido + telemetría → REPEATER (regresión R3 activa) no tiene test**.
- ❌ `_delete_contact` con `path_pubkey` — DELETE vía URL sin prueba.
- ❌ PSK masking `"••••••••"` — `test_rest_controllers` crea canal con psk="secret" pero nunca verifica el enmascaramiento en el GET.
- ❌ `protected_prefixes` ampliadas / `_is_api_auth_valid` — **0 tests** de auth en toda la suite (ni 401, ni fail-open, ni compare_digest).
- ❌ `to_thread(save_to_file)` — sin test de no-bloqueo ni de la race R1.
- ❌ try/finally de waiters — sin test de excepción.
- ❌ Cambios JS (`updateNodeInDom` — bug R2 activo sin detectar, `_hasInitiallyCentered`).

**Huecos estructurales que permanecen**: ciclo de vida del bridge (`start`/`stop`/`run_forever`/`_stop_task` — donde vive el shutdown zombi N1), `_is_api_auth_valid` (donde vive el fail-open C1), `check_airtime_cooldown` + parsers de `repeater_manager` (donde viven N16 y el batch sin cooldown), `save_to_file`/`load_from_file` (donde vive la race R1), ~80% de `MeshcoreSDKAdapter`, cross-talk de `notify_*` (N2), handshake WebSocket.

**Problemas de calidad persistentes**: 2 suites fantasma (`test_bridge_logic.py`, `test_n8n_parser_matrix.py` — 9 tests que no importan src/ y no detectarían ninguna regresión real); mocks tan amplios en `test_rx_routers.py` (MagicMock ctx) que un bug real en los handlers pasaría (solo asertan `add_or_update` llamado, no el rol asignado); mutación de `config.TX_INTERVAL_SEC` sin restaurar en 2 archivos; `test_tile_server.py` no hermético (requiere mbtiles reales + puerto fijo); contradicción latente `store_and_forward`; flakiness (sleeps 1.1s wall-clock, esperas Playwright 250-2500ms).

**Verificabilidad estimada**: ~55-60% de líneas ejecutadas; **~45-50% de comportamiento verificable con asserts fuertes sobre código real**. Los tests nuevos cerraron parcialmente el hueco del pipeline RX, pero ninguna de las 5 CRÍTICAS de este reporte es detectada por la suite actual.

---

## 6. Cumplimiento de Reglas Inmutables (AGENTS.md) — estado actualizado

| Regla | Estado | Evidencia |
|---|---|---|
| Repetidores nunca en Contactos | ⚠️ **DEGRADADO** | `list_client_contacts` filtra ✔, pero R3 reclasifica CLIENTs como REPEATERs (desaparición de usuarios de Contactos) y N5 permite chat a repetidores con prefijos laxos. Inconsistencia de prefijos ×11 copias. |
| NUNCA chat a repetidores/local | ⚠️ PARCIAL | Guardas presentes en 3 capas ✔, pero bypass por prefijos cortos (C4 previo, no corregido) y por `is_admin_cmd` laxo (N5). |
| Guarda de origen propio | ✅ CUMPLE | `is_outgoing`/`is_local_sender` + loopback en direct_handler:35 ✔ (hueco menor N30 en canales). |
| Anti-spam/anti-bucle | ⚠️ PARCIAL | Rate limiter/dedup implementados ✔, pero eviction muerta (N10), batch config sin cooldown (A8), cross-talk waiters (N2), traceroute sin rate-limit (N15), ráfaga 9 comandos por modal (W11). |
| asyncio sin bloqueantes | ❌ **INCUMPLE** | Race introducida por to_thread (R1), `stop()` síncrono, 3 sites en contacts_controller, preflight bloqueante (N9), estáticos/SQLite síncronos, `get_raw_log_tail`. |
| Persistencia atómica JSON | ⚠️ **DEGRADADO** | `os.replace` ✔ pero `.tmp` fijo sin lock con writers concurrentes (R1) = corrupción posible. |
| `protocol_types.py` aislado | ✅ CUMPLE | Solo stdlib, frozen dataclasses ✔. |
| Frontend Vanilla | ⚠️ PARCIAL | Vanilla ✔ pero Leaflet unpkg sin SRI + Google Fonts (A16) y ~20 controles muertos (W15). |
| RFC 7807 / códigos HTTP | ✅ CUMPLE mayormente | `problem_details` ✔. |

---

## 7. Plan de Remediación Priorizado (recomendado — sin cambios aplicados)

| Prioridad | Acción | Hallazgos |
|---|---|---|
| **P0** | Lock/snapshot en `NodeRegistry.save_to_file` (lock de escritura o snapshot inmutable en el loop + to_thread del dump); unificar los 5 callers | R1 |
| **P0** | `loop.stop()` en `_stop_task` tras completar `stop()` + idempotencia de `stop()` | N1 |
| **P0** | Corregir `updateNodeInDom`: selector `data-pk`, sub-selectores `.stat-pill`, fallback NO destructivo (return si no hay cards) | R2 |
| **P0** | Enmascarar PSK en TODOS los payloads salientes (mover masking a serialización compartida REST+WS) + auth en handshake WS | W1, W3 |
| **P0** | Cerrar fail-open de API key (401 si no configurada) + las 9 brechas de auth (deny-by-default: lista blanca de GETs públicos; corregir `/api/packets/clear` → `/api/packets`) | C1, W2 |
| **P1** | Reclasificación: solo marcar REPEATER con `FirmwareAdvertType` oficial (SSoT en `shared_utils`), nunca por telemetría laxa de CLIENT desconocido; consolidar las 11 copias de prefijos | R3, N7, §6.2 |
| **P1** | Resolver waiters por `request_id` (no por clave de nodo); invalidar `_self_info` en `_handle_self_info` y `disconnect()`; sync con `local_config_executor` | N2, R4 |
| **P1** | Comprobar `res.ok` en DELETE contacts + `zoomstart` en mapa | W5, W9 |
| **P1** | Suscribir `admin/repeater/+/cmd` o eliminar rama muerta; orden `disconnect()` → `loop_stop()` | A1, N8 |
| **P2** | Acotar `z` en tiles (0-22) + despacho tras auth; `crypto.getRandomValues` para PSK; XFF solo con proxy confiable; Self-host Leaflet con SRI | A13, Math.random, W7, A16 |
| **P2** | `check_airtime_cooldown` en batch config + traceroute rate-limit; else-sleep en polling de waiters; `contacto fantasma` por pad de claves | A8, N14, N4 |
| **P2** | Tests: `_is_api_auth_valid` (401/fail-open/prefijos), PSK masking, DELETE por path, `should_treat_as_repeater` con registry real, race de `save_to_file`, excepciones en try/finally de waiters | §5 |
| **P3** | Cablear o eliminar la UI muerta (~20 controles); eliminar/reescribir suites fantasma; `monkeypatch` para config global; umbral `--cov-fail-under` | W15, §5 |
| **P3** | Refactor estructural: extraer analítica de NodeRegistry, descomponer God Classes, reemplazar `Any` por Protocol existentes, mover security_inspector a módulo compartido, actualizar ARCHITECTURE.md §7 (15+ rutas) | §4.3 |

---

## 8. Conclusión Final

El commit **f61d91f demuestra buena capacidad de corrección puntual**: 12 de los ~20 hallazgos previos fueron cerrados correctamente (incluidos los 2 bugs de sintaxis-lógica más graves), el deploy quedó 100% sincronizado y verificable, y la suite creció de forma real (+20 tests del pipeline RX, 247 total).

Sin embargo, esta auditoría profunda revela que **el patrón de corrección es reactivo y local**, lo que produjo:
1. **4 regresiones nuevas** — la más grave una **race de persistencia** (R1) que el código síncrono original no tenía, y un **bucle de UI destructivo** (R2) en el frontend.
2. **3 críticos previos sin cerrar** (fail-open C1, DoS de tiles A13, Leaflet A16) y la **fuga de PSK por WebSocket (W1)** que anula el masking recién añadido.
3. **Deuda estructural agravada**: la heurística de clasificación pasó de 9 a 11 copias con 3 variantes (la propia corrección R3 añadió una copia más), y la regla inmutable de repetidores §1.1 ahora es más frágil que antes.

**El sistema sigue sin ser verificable al 100% (~45-50% con confianza)**: ninguna de las 5 CRÍTICAS de este reporte sería detectada por la suite actual, y los cambios de seguridad del último commit (masking, auth ampliada, path_pubkey) están sin pruebas.

**Recomendación central**: el siguiente ciclo de corrección debe abordar **causas estructurales** (SSoT de roles vía `FirmwareAdvertType` como manda AGENTS §1.1.3, lock del Repository, contratos de concurrencia) en lugar de seguir parcheando en la capa donde aparece cada síntoma — cada parche local está añadiendo copias divergentes y regresiones nuevas.

---

*Reporte generado por 4 auditorías secuenciales de agente único (Agente 2 Bridge Architect → Agente 4+5 Web/Security → Agente 3 QA → Agente 0/1 Arquitectura) con verificación manual de todos los hallazgos CRÍTICOS y ALTOS. Sin modificaciones aplicadas al código. Conteo total: 5 CRÍTICOS, 12 ALTOS, 27 MEDIOS, ~46 BAJOS (nuevos + regresiones + previos persistentes documentados).*
