# Auditoría profunda de MeshCore Bridge — 2026-10-18

Documento de hallazgos de una revisión por capas del código de producción, con
reproducción de los defectos confirmados mediante pruebas ejecutadas en un
entorno aislado (SQLite temporal, adaptadores virtuales, servidor de loopback y
navegador Playwright). No se transmitió por radio, no se tocó un broker de
producción ni una instalación operativa.

---

## 1. Metadatos de la auditoría

| Campo | Valor |
|---|---|
| Repositorio | `C:\Users\Ruby\Desktop\meshcore-bridge` |
| Commit congelado (baseline) | `c3bd8a4` — *Fix first-access help and avoid login flash during session checks* (2026-10-18 22:41 -0400) |
| Commits inmediatos anteriores | `8c4a775` (chat: preservar posición de lectura), `bb5f232`, `d7c6e8c` |
| Intérprete | CPython 3.12.14 (`>= 3.12` de `AGENTS.md`; recomendado 3.13.5) |
| Playwright instalado | 1.62.0 (`pyproject.toml` fija 1.63.0) |
| Árbol de trabajo al cerrar | Limpio salvo el artefacto de auditoría nuevo `tests/test_audit_2026_10_18.py` (untracked) |
| Herramientas de evidencia | `pytest`, `httpx.ASGITransport`, Playwright async, lectura directa de código |

> **Nota sobre el blanco móvil.** Durante la sesión el `HEAD` avanzó de
> `bb5f232` a `c3bd8a4` (el trabajo de chat que estaba en *staging* se confirmó
> como `8c4a775` y entró después un arreglo del *flash* del login). Todos los
> hallazgos se refieren al código de `c3bd8a4`. Si el árbol sigue moviéndose,
> reconfirmar las líneas citadas.

---

## 2. Resumen ejecutivo

- **No existía un único "error" reportado por el usuario.** La petición pedía
  auditar, encontrar defectos y demostrarlos. La única evidencia de error en
  tiempo de ejecución del repositorio es un registro repetido en
  `logs/meshcore-bridge.error.log`:

  ```
  Exception in ASGI application
  Exception type: CancelledError
  asgi_ws_hub.py:242  endpoint()
  asgi_ws_hub.py:165  asyncio.wait(...)
  ```

  Se localizó la causa (el `CancelledError` de `_close_peer` escapa a `endpoint`
  y uvicorn lo clasifica como excepción no controlada) y **se reprodujo de forma
  aislada** (§6, hallazgo `WS-01`).

- **10 defectos quedaron demostrados con pruebas reproducibles** (`10 passed`,
  ver §7). Los de mayor impacto: crecimiento ilimitado de `delivery_events`
  (`DB-01`), downlink MQTT externo sin límite de tamaño ni admisión
  (`MQTT-01`), lectura/parseo del cuerpo HTTP antes de autenticar (`WEB-01`) y un
  control de seguridad (inspector de inyección) que nunca inspecciona query ni
  body (`WEB-02`).

- **Se hallaron además ~13 defectos/riesgos verificados por lectura de código**
  pero no reproducidos (§5, marcados *Estático*), y **5 contradicciones entre la
  documentación y el código** (§8).

- **El trabajo reciente (chat `8c4a775` y login `c3bd8a4`) pasa sus regresiones**
  (`tests/test_chat_reading_browser.py`: 12 passed; `tests/test_auth_startup_state.py`:
  2 passed). La auditoría no encontró que ese trabajo introduzca un fallo
  funcional, pero sí confirma que **arrastra defectos preexistentes** (DOM sin
  poda `CHAT-01`) y **estado muerto** en el módulo de chat.

---

## 3. Metodología: separación en capas y orquestación

Se dividió el sistema en capas y se asignó la investigación de cada una a
subagentes especializados (rol del Agente 0, orquestador), y luego se verificó
directamente en el código y con pruebas.

| Capa | Alcance | Archivos clave | Agente |
|---|---|---|---|
| **L1 — Protocolo / Serial** | framing, tipos binarios, drivers | `src/protocol_types.py`, `src/serial_driver.py`, `src/tcp_companion_server.py` | Protocol & Firmware Investigator |
| **L2 — Core / Persistencia / Malla** | bus asyncio, SQLite, rate limiter, dedup, enrutado RX, MQTT | `src/bridge_core.py`, `src/station_database.py`, `src/rate_limiter.py`, `src/deduplicator.py`, `src/rx_router.py`, `src/mqtt_dispatcher.py`, `src/external_mqtt_client.py` | Python Bridge Architect |
| **L3 — Web / ASGI / Seguridad** | middleware, auth, WS hub, inspector | `src/web/asgi_security.py`, `src/web/asgi_ws_hub.py`, `src/web/auth_store.py`, `src/web/access_policy.py`, `src/web/security_inspector.py` | Security Auditor |
| **L4 — Frontend SPA** | chat, sesión, i18n, render | `src/web/static/js/**`, `src/web/static/index.html`, `src/web/static/css/app.css` | Web UI/UX Architect |
| **L5 — Docs / QA** | marco documental y consistencia | `docs/**`, `tests/**`, `scripts/**` | Documentation & Reference Provenance |

Marco documental usado como referencia de "verdad": `docs/README.md` (índice y
autoridad), `docs/ARCHITECTURE.md`, `docs/PROTOCOL_SPEC.md`, `docs/STORAGE.md`
(ADR 0017), `docs/TESTING.md`, `docs/audits/2026-10-17-sensor-subscriptions.md`,
`CONTEXT.md`. Regla aplicada: **el firmware/SDK oficiales definen el protocolo; el
código determina qué está implementado; toda discrepancia se registra como tal.**

---

## 4. Matriz resumen de hallazgos

| ID | Sev. | Estado | Título | Ubicación |
|---|---|---|---|---|
| `DB-01` | Media-Alta | **Demostrado** | `delivery_events` crece sin límite | `src/station_database.py:146,355,383` |
| `MQTT-01` | Media-Alta | **Demostrado** | Downlink MQTT externo sin límite de tamaño ni admisión | `src/external_mqtt_client.py:512`, `src/bridge_core.py:1154` |
| `WEB-01` | Media | **Demostrado** | Cuerpo HTTP leído/parseado antes de autenticar | `src/web/asgi_security.py:322` |
| `WEB-02` | Media | **Demostrado** | Inspector de seguridad no ve query ni body | `src/web/asgi_security.py:145`, `src/web/access_policy.py:98` |
| `WS-01` | Media | **Demostrado** | `CancelledError` escapa de `_close_peer` (el error de los logs) | `src/web/asgi_ws_hub.py:165,234` |
| `CHAT-01` | Media | **Demostrado** | El DOM del chat crece sin límite | `src/web/static/js/modules/chat.js:1854,1920` |
| `CHAT-02` | Baja | **Demostrado** | Estado muerto: `unreadCounts` / `globalChatUnreadBadge` | `src/web/static/js/modules/chat.js:58,1250` |
| `DOC-01` | Media | **Demostrado** | `STORAGE.md` documenta `SessionStorage` (el código usa cookie HttpOnly) | `docs/STORAGE.md:11` |
| `DOC-02` | Media | **Demostrado** | `PROJECT_KNOWLEDGE.md` niega backend SQLite | `docs/PROJECT_KNOWLEDGE.md:63` |
| `DOC-03` | Media | **Demostrado** | `PROTOCOL_SPEC.md` documenta `MAX_FRAME_SIZE = 512` (el código usa 300) | `docs/PROTOCOL_SPEC.md:131` |
| `DOC-04` | Media | **Demostrado** | Layout de suscripción de sensores desactualizado | `docs/PROTOCOL_SPEC.md:557` |
| `AUTH-01` | Media | Estático | `AuthStore` usa `BEGIN IMMEDIATE` también en lecturas | `src/web/auth_store.py:95` |
| `RX-01` | Media | Estático | `MeshcoreFrame` sin atributos usados por el búfer de analítica | `src/rx_router.py:308`, `src/protocol_types.py:795` |
| `RX-02` | Media | Estático | `STATUS` remoto mal atribuido a la estación local | `src/rx_router.py:593` |
| `MQTT-02` | Baja | Estático | `tag` de `binary_response` opaco publicado en `TOPIC_RX_ALL`/WS | `src/routers/system_handler.py:114` |
| `RATE-01` | Baja | Estático | `_last_save_time` se fija antes de escribir (fallo silenciado) | `src/rate_limiter.py:384` |
| `DB-02` | Baja | Estático | `_SECRET_FIELDS` incompleto y sin normalizar `-` | `src/station_database.py:34` |
| `WS-02` | Baja | Estático | `float(os.getenv("WS_METRICS_INTERVAL_SEC"))` fuera del `try` | `src/web/asgi_ws_hub.py:331` |
| `HTTP-01` | Baja | Estático | Respuestas 400/413/403 de rechazo sin cabeceras CORS | `src/web/asgi_security.py:246,277,300` |
| `DEDUP-01` | Baja | Estático | Ventana de deduplicación doc vs código | `src/deduplicator.py`, `docs/PROTOCOL_SPEC.md` |
| `QA-01` | Media | Estático | `tests/conftest.py` importa `playwright` incondicionalmente | `tests/conftest.py:17` |
| `QA-02` | Baja | Estático | `TEST_INVENTORY.md` con conteos obsoletos | `docs/TEST_INVENTORY.md:5` |
| `QA-03` | Baja | Estático | Nombres de artefactos en `TESTING.md` ≠ los reales | `scripts/inventory_verification.py:67` |

---

## 5. Detalle por capa

### L1 — Protocolo y serial

- **`DOC-04` (Demostrado).** `docs/PROTOCOL_SPEC.md:551-567` (§15.2) documenta
  `timeout` como `uint32` Little-Endian en los bytes 4..8 y una respuesta de
  4 B/1 B. El código construye `struct.pack("<HBB", ...)` (`src/protocol_types.py:240`)
  → `uint16 + reserved + scope`, y `parse_sensor_subscribe_reply` (`:243-270`)
  espera 6 B y distingue `unsubscribe`. La auditoría de sensores
  (`docs/audits/2026-10-17-sensor-subscriptions.md`) **sí coincide con el código**;
  la spec maestra quedó desactualizada. Evidencia reproducida:
  `bytes[4:8] = 100e0008` (código) vs `100e0000` (documentado).
- **`DOC-03` (Demostrado).** `docs/PROTOCOL_SPEC.md:131` declara
  `MAX_FRAME_SIZE = 512`; el código usa `MAX_FRAME_SIZE = 300`
  (`src/tcp_companion_server.py`).
- Sin discrepancias adicionales verificadas en framing Companion
  (dirección + longitud LE) ni en el framing raw SOF/EOF/ESC/CRC; ambos están
  cubiertos por las suites existentes y no se alteraron.

### L2 — Core, persistencia y malla

- **`DB-01` (Demostrado, Media-Alta).** La tabla `delivery_events`
  (`src/station_database.py:146`) inserta una fila por cada actualización de
  entrega (`update_delivery`, `:337`) para sobrevivir a reinicios, pero **ninguna
  ruta la poda**: `_prune_acks` (`:383`) sólo borra `pending_acks`. En una
  estación de larga vida el archivo SQLite crece indefinidamente. Reproducción: 5
  mensajes entregados → 5 filas permanentes tras invocar los puntos de limpieza.
- **`MQTT-01` (Demostrado, Media-Alta).** El camino de downlink del broker
  externo (`src/external_mqtt_client.py:512-537`) **no comprueba
  `MQTT_MAX_PAYLOAD_BYTES` (128 KiB, `config.py:122`)** ni aplica la admisión del
  dispatcher; `src/bridge_core.py:1154` invoca `_handle_tx_request` directamente,
  saltándose `src/mqtt_dispatcher.py:70-87` (límite de tamaño + contador de
  admisión). Un broker (o un cliente comprometido) puede inyectar un payload
  sobredimensionado por un método "privado". Reproducción: un payload de 256 KiB
  alcanza el callback sin rechazo.
- **`MQTT-02` (Estático, Baja).** `src/routers/system_handler.py:114-127`
  publica el campo `tag` de una respuesta binaria **opaca** en `TOPIC_RX_ALL` y
  por WebSocket, contradiciendo la exclusión de `push_tag` en las vistas
  públicas documentada en `docs/PROTOCOL_SPEC.md`.
- **`RATE-01` (Estático, Baja).** `src/rate_limiter.py:384` fija
  `_last_save_time = now` **antes** de programar la escritura; si la escritura
  falla, el siguiente intento dentro de `save_interval` se suprime silenciosamente.
- **`RX-01` (Estático, Media).** `src/rx_router.py:308-317` lee
  `channel_idx/frame_type/sender_pubkey/recipient_pubkey/rssi/snr` del frame vía
  `getattr` con valores por defecto, pero `MeshcoreFrame`
  (`src/protocol_types.py:795-802`) **no define esos atributos** → el búfer de
  analítica/debug registra valores neutros, degradando las métricas.
- **`RX-02` (Estático, Media).** `src/rx_router.py:593-603` atribuye un evento
  `STATUS` sin emisor resoluble a la **estación local** (heurística por subcadena
  `"STATUS"`), lo que puede contaminar la analítica con actividad propia.
- **`DEDUP-01` (Estático, Baja).** La ventana efectiva del deduplicador difiere
  del texto de `docs/PROTOCOL_SPEC.md`; conviene fijar una sola fuente de verdad.
- **`DB-02` (Estático, Baja).** `_SECRET_FIELDS` (`:34`) enumera
  `psk/password/api_key/token/secret/private_key/...` pero omite variantes como
  `pin`, `admin_password`, `privatekey` y no normaliza `-`→`_`. Defensa en
  profundidad del saneado de documentos persistidos.

### L3 — Web / ASGI / Seguridad

- **`WS-01` (Demostrado, Media — *el error de los logs*).** En
  `WebSocketHub.endpoint` (`src/web/asgi_ws_hub.py:234-242`) un `finally` cancela
  las tareas pendientes; al hacerlo se cancela la propia `_close_peer`
  (`:165`, dentro de `asyncio.wait`), cuyo `except` (`:170-172`) re-lanza el
  `CancelledError`. Ese `CancelledError` **escapa del endpoint ASGI** y uvicorn lo
  registra como `Exception in ASGI application`. Reproducido de forma aislada en
  §6: `CancelledError escaped _close_peer = True`. Es **ruido de observabilidad**
  (no corrompe datos ni cierra sesiones), pero contamina el log de errores y
  oculta fallos reales.
- **`WEB-01` (Demostrado, Media).** `src/web/asgi_security.py:322-335` lee y
  parsea el cuerpo (`_read_body`, `:203-275`) **antes** de que el middleware de
  autenticación (interno) decida el 401. Una petición anónima con JSON malformado
  recibe **400** en lugar de **401**, y hasta 1 MiB se parsea sin autenticar
  (superficie de DoS/error-oracle). Reproducción: `POST /api/private` con
  `{not-json` sin cookie → `400`.
- **`WEB-02` (Demostrado, Media).** El inspector de inyección recibe
  `body_dict=None` y `safe_log_path(...)` (`src/web/access_policy.py:98-100`) que
  **recorta la query en `?`**; `src/web/asgi_security.py:145-165`. Resultado: un
  payload de inyección en el query string (p. ej.
  `?next=javascript:alert(1)`) **no dispara** los patrones de
  `security_inspector.py:98-114`. El control de seguridad es, en la práctica, un
  no-op para query/body. Reproducción: request con inyección en query →
  `allowed = True`.
- **`AUTH-01` (Estático, Media).** `src/web/auth_store.py:95-110` abre la
  conexión con `BEGIN IMMEDIATE` incluso en lecturas puras (p. ej. resolver una
  sesión). Con varias conexiones concurrentes puede serializar lecturas y
  provocar bloqueos de hasta el `timeout` (30 s) en picos de carga.
- **`HTTP-01` (Estático, Baja).** Las respuestas de rechazo 400
  (`transfer-encoding`/`Content-Length` inválidos), 413 y 403 de
  `src/web/asgi_security.py` no añaden cabeceras CORS, lo que rompe el diagnóstico
  desde un frontend cross-origin.
- **`WS-02` (Estático, Baja).** `src/web/asgi_ws_hub.py:331` evalúa
  `float(os.getenv("WS_METRICS_INTERVAL_SEC", "5.0"))` **fuera** del `try`; un
  valor inválido mata el bucle de métricas.

### L4 — Frontend SPA

- **`CHAT-01` (Demostrado, Media).** El módulo de chat recorta **sólo la lista en
  memoria** (`MAX_FEED_MESSAGES = 100`, `chat.js:1920-1921`) pero
  `appendChatMessage` (`chat.js:1854`) **nunca elimina nodos del DOM**. Una sesión
  que reciba mensajes en vivo acumula burbujas sin cota. Reproducción: 130
  `appendChatMessage` en `ch_1` → **130 filas** `.message-bubble-row` (esperado
  ≤100).
- **`CHAT-02` (Demostrado, Baja).** `unreadCounts` (`chat.js:58`) y
  `globalChatUnreadBadge` (`index.html:151`) se actualizan (`chat.js:1250-1257`)
  sobre un elemento inexistente: **estado muerto** que da falsa sensación de
  cobertura.
- **Revisión del cambio reciente `8c4a775` (chat).** Sus 12 regresiones de
  navegador pasan. No se detectó un fallo funcional nuevo; los defectos asociados
  (`CHAT-01`, `CHAT-02`) son **preexistentes**. Observación de honestidad
  documental: `docs/CHAT_READING_IMPROVEMENTS_2026-10-18.md` menciona métricas de
  tipografía/interlineado verificadas con "capturas", no con aserciones; y **no
  hay test** que ejercite el camino real bus/WebSocket (sólo se inyectan mensajes
  en el DOM), por lo que el acoplamiento real mensaje→DOM→posición no queda
  cubierto por la suite.
- **Revisión del cambio reciente `c3bd8a4` (login).** El nuevo
  `src/web/static/js/session_startup.js` reutiliza la promesa en
  `core/auth.js:18-42` (una sola consulta GET) y `session_payload` publica
  `requires_initial_setup` tanto para autenticados como para anónimos
  (`src/web/authentication.py`), y el esquema OpenAPI `AuthSession` se amplió
  (`src/web/asgi_openapi.py`). `tests/test_auth_startup_state.py`: 2 passed.

### L5 — Documentación y QA

- **`QA-01` (Estático, Media).** `tests/conftest.py:17` importa `playwright`
  **incondicionalmente**; sin esa dependencia la recolección de toda la suite
  falla, incluso para las pruebas que no usan navegador.
- **`QA-02` (Estático, Baja).** `docs/TEST_INVENTORY.md:5` declara 74 archivos
  (48 Python / 47 suites); lo real es 136 `.py` en `tests/` (133 `test_*.py`).
- **`QA-03` (Estático, Baja).** `scripts/inventory_verification.py:67-74` espera
  `tests/artifacts/qa-baseline.xml`, `pytest-final.xml` y `coverage.json`,
  mientras que los comandos documentados en `docs/TESTING.md` producen otros
  nombres. Los recuentos de `tests/artifacts/inventory.json` (95 tests/scripts,
  352 casos, cobertura 62 %) tampoco corresponden al árbol actual.
- **Contradicciones de documentación** (`DOC-01`…`DOC-04`): detalladas en §8;
  las cuatro están reproducidas.

---

## 6. Análisis del error de los logs (`WS-01`)

**Síntoma.** `logs/meshcore-bridge.error.log` contiene 5 entradas idénticas:
`Exception in ASGI application` / `Exception type: CancelledError` con traza
`asgi_ws_hub.py:242 endpoint() → :165 asyncio.wait`.

**Causa.** En `endpoint` el `finally` (`:234-242`) ejecuta
`await self._close_peer(peer)` mientras cancela tareas; la cancelación alcanza a
`_close_peer` (`:165`) y su bloque `except asyncio.CancelledError` (`:170-172`)
**re-lanza** la excepción en lugar de tratarla como cierre, propagándola fuera del
alcance ASGI.

**Reproducción aislada.** Se instancian `WebSocketHub` y un `_Peer` con un socket
que bloquea; se cancela la tarea `_close_peer` y se observa la propagación:

```
[DEFECT-WS-01] CancelledError escaped _close_peer = True
```

**Impacto.** Ruido de observabilidad: uvicorn clasifica el cierre normal de un
cliente WebSocket como excepción no controlada, lo que degrada la señal del log
(un error real quedaría enmascarado). No se observó corrupción de datos,
fuga de memoria ni caída del proceso.

---

## 7. Pruebas de reproducción

Artefacto: `tests/test_audit_2026_10_18.py` (caracterización: cada prueba **fija
el comportamiento actual defectuoso**; pasar demuestra que el defecto existe y,
si se corrige, la prueba debe actualizarse). Todas usan recursos temporales o
virtuales.

Comando y salida real:

```
> .venv\Scripts\python.exe -m pytest tests/test_audit_2026_10_18.py -q --no-cov -p no:cacheprovider -s

[DEFECT-DB-01]   delivery_events rows after 5 delivered messages = 5
[DEFECT-MQTT-01] callback invocations for a 256 KiB downlink = 1
[DEFECT-WEB-01]  unauthenticated malformed POST /api/private -> 400
[DEFECT-WEB-02]  query-string injection request allowed = True
[DEFECT-WS-01]   CancelledError escaped _close_peer = True
[DEFECT-CHAT-01] rendered bubble rows after 130 appends = 130
[DEFECT-DOC-01]  STORAGE.md still documents SessionStorage credentials
[DEFECT-DOC-02]  PROJECT_KNOWLEDGE.md denies a SQLite chat/node backend
[DEFECT-DOC-03]  code MAX_FRAME_SIZE=300, doc claims 512
[DEFECT-DOC-04]  bytes[4:8]=100e0008 documented=100e0000
10 passed in 9.12s
```

Corroboración de que el trabajo reciente pasa sus regresiones:

```
> .venv\Scripts\python.exe -m pytest tests/test_auth_startup_state.py -q --no-cov
2 passed in 4.34s

> .venv\Scripts\python.exe -m pytest tests/test_chat_reading_browser.py -q --no-cov
12 passed in 168.11s
```

Semántica de cada prueba:

| Test | Demuestra |
|---|---|
| `test_defect_db01_...` | `delivery_events` no se poda nunca |
| `test_defect_mqtt01_...` | Downlink externo acepta payloads > límite |
| `test_defect_web01_...` | Parseo del body antes de autenticar (400 ≠ 401) |
| `test_defect_web02_...` | El inspector no ve la query string |
| `test_defect_ws01_...` | `CancelledError` escapa del cierre de peer |
| `test_defect_chat01_...` | El DOM del chat no se poda (130 vs 100) |
| `test_defect_doc01_...` | `STORAGE.md` contradice el contrato de cookie |
| `test_defect_doc02_...` | `PROJECT_KNOWLEDGE.md` niega el backend SQLite |
| `test_defect_doc03_...` | `MAX_FRAME_SIZE` doc 512 ≠ código 300 |
| `test_defect_doc04_...` | Layout de suscripción de sensores desfasado |

---

## 8. Contradicciones documentación ↔ código

1. **`DOC-01` — Sesión en el navegador.** `docs/STORAGE.md:11` afirma que las
   credenciales/CSRF viven en `SessionStorage`. El código usa **cookie HttpOnly +
   token CSRF en memoria** (`src/web/static/js/core/utils.js`, comentario
   explícito en `core/auth.js`: "Authentication does not depend on Web Storage").
2. **`DOC-02` — Persistencia.** `docs/PROJECT_KNOWLEDGE.md:63` niega un "backend
   SQLite de chat/nodos", pero `ADR 0017` y `src/station_database.py` lo
   implementan.
3. **`DOC-03` — Framing.** `docs/PROTOCOL_SPEC.md:131` (`MAX_FRAME_SIZE = 512`)
   vs `300` en `src/tcp_companion_server.py`.
4. **`DOC-04` — Sensores.** `docs/PROTOCOL_SPEC.md:551-567` (`uint32`, 4 B)
   vs `uint16 + reserved + scope` (`src/protocol_types.py:240-270`). La auditoría
   de sensores coincide con el código; la spec maestra no.
5. **`DOC-05` — Integridad de QA.** `docs/TEST_INVENTORY.md` y los recuentos de
   `tests/artifacts/inventory.json` no reflejan el árbol actual (§5/L5).

---

## 9. Priorización y recomendaciones

**Prioridad 1 (media-alta).**
- `DB-01`: añadir poda de `delivery_events` (ventana temporal o por número de
  filas) en el mismo punto donde ya se podan `pending_acks`; preservar la
  semántica de "ACK temprano tras reinicio" acotando por antigüedad.
- `MQTT-01`: validar tamaño y pasar por la admisión de `mqtt_dispatcher` en el
  camino de downlink externo; dejar de invocar `_handle_tx_request` directamente.
- `WEB-01`: decidir autenticación **antes** de leer/parsear el cuerpo; reservar
  límites de tamaño sin parsear.

**Prioridad 2 (media).**
- `WEB-02`: inspeccionar query y body en el punto de admisión (o documentar
  explícitamente que el inspector sólo cubre la ruta, cerrando la falsa garantía).
- `WS-01`: convertir el cierre normal en no-error (no re-lanzar `CancelledError`
  desde `_close_peer`; distinguir cancelación de cierre).
- `AUTH-01`: usar transacción diferida (`BEGIN DEFERRED`) en lecturas de sesión.
- `RX-01`/`RX-02`: alinear `MeshcoreFrame` con los atributos usados por el búfer
  de analítica y endurecer la heurística de atribución de emisor.
- `CHAT-01`: podar el DOM al ritmo de `MAX_FEED_MESSAGES` en `appendChatMessage`.
- `QA-01`: hacer opcional el import de `playwright` en `conftest.py`.

**Prioridad 3 (baja).** `CHAT-02`, `MQTT-02`, `RATE-01`, `DB-02`, `WS-02`,
`HTTP-01`, `DEDUP-01` y las correcciones de documentación `DOC-01`…`DOC-05`.

---

## 10. Limitaciones (lo que esta auditoría NO demuestra)

- No se verificó con radio física ni con un broker/estación de producción; todo
  es entorno aislado (`AGENTS.md` §7).
- `MQTT-01` se demostró por **tamaño**; el desvío de la **admisión** se sostiene
  por lectura de código (`bridge_core.py:1154` → `_handle_tx_request`), no por una
  prueba de carga con el dispatcher real.
- No se reprodujo la **contención** de `BEGIN IMMEDIATE` de `AUTH-01` (requeriría
  provocar bloqueos concurrentes de hasta 30 s).
- `RX-01`/`RX-02` y `MQTT-02` son análisis estáticos: se confirmó el código, pero
  la **alcanzabilidad** en producción (siempre llegan frames/eventos con ese
  formato) no se reprodujo.
- No se ejecutó la suite completa ni cobertura global; se usaron subconjuntos
  dirigidos. Los números de cobertura citados en `TESTING.md` no se revalidaron.
- El `CancelledError` no se reprodujo a nivel de **endpoint ASGI real** (sólo a
  nivel de `_close_peer`/script aislado y por evidencia de log).
- No se auditó seguridad criptográfica, TLS, ni el SDK/firmware de `reference/`
  (solo lectura, usado como verdad de protocolo).

---

## 11. Trazabilidad de la evidencia

- Reproducciones: `tests/test_audit_2026_10_18.py` (nuevo, untracked).
- Comandos: `pytest` (subconjuntos), `git rev-parse/log/diff/status`, lecturas de
  código citadas con `archivo:línea`.
- Logs: `logs/meshcore-bridge.error.log` (5 × `CancelledError`).
- Documentos de referencia leídos: `docs/README.md`, `docs/ARCHITECTURE.md`,
  `docs/PROTOCOL_SPEC.md`, `docs/STORAGE.md`, `docs/TESTING.md`,
  `docs/TEST_INVENTORY.md`, `docs/PROJECT_KNOWLEDGE.md`,
  `docs/audits/2026-10-17-sensor-subscriptions.md`,
  `docs/CHAT_READING_IMPROVEMENTS_2026-10-18.md`,
  `docs/AUTH_STARTUP_FIX_2026-10-18.md`, `CONTEXT.md`.

> Los 10 hallazgos *Demostrados* tienen una prueba que pasa y fija el defecto;
> los *Estáticos* tienen ubicación exacta pero pendiente de prueba de
> reproducibilidad. Ninguna corrección fue aplicada: este documento es un informe,
> no un parche.
