# Línea base WebSocket, seguridad HTTP, SPA y mapas

Fecha de revisión: 2026-10-08. Fase 0 de la migración propuesta a FastAPI.
Evidencia: lectura de código; no se arrancaron servidores, navegadores, radio o
brokers, ni se ejecutaron suites. Los ejemplos son sintéticos. No constituyen
capturas de una estación. No se han modificado producción, límites o intervalos.

## 1. Autoridad y alcance

Esta línea base describe el transporte web vigente, incluidos comportamientos
previos que requieren decisión explícita al portar. No presenta FastAPI como
implementado. El catálogo REST completo debe leerse junto al documento de rutas
de esta fase; la política de autenticación efectiva se define aquí porque vive
en el servidor, fuera de los controladores REST.

Fuentes de lectura:

| Fuente | Función / líneas de referencia | Responsabilidad |
| --- | --- | --- |
| [http_server.py](../../src/web/http_server.py) | `_dispatch_client_request` 458, `_is_api_auth_valid` 586, `_handle_websocket_handshake` 698, `_serve_static_file` 1073 | Ingreso, autenticación, WS, estáticos |
| [api_router.py](../../src/web/api_router.py) | `_notify_web_clients` 167, `record_incoming_event` 201, `_dispatch_misc` 779 | Puente broadcast, historial y mapas |
| [websocket.js](../../src/web/static/js/core/websocket.js) | `connect` 20, `onmessage` 62, `_startHeartbeat` 140 | Adaptador WS del navegador |
| [eventbus.js](../../src/web/static/js/core/eventbus.js) | `EVENTS` 48 | Discriminadores internos SPA |
| [rx_router.py](../../src/rx_router.py) | `_spawn_broadcast_task` 511, `_handle_mesh_msg_common` 884, `_handle_mesh_telemetry_msg` 1095 | Eventos derivados del SDK y RX |
| [repeater_handler.py](../../src/routers/repeater_handler.py) | `handle` 39 | ACK correlacionado y trace |
| [system_handler.py](../../src/routers/system_handler.py) | `handle` 38 | Eventos SDK restantes |
| [bridge_core.py](../../src/bridge_core.py) | `_broadcast_system_log` 217, `_record_tx_packet` 851, `_on_duty_cycle_alert` 1050, `_on_airtime_cutoff_change` 1080 | Eventos de logs, TX y airtime |
| [diagnostics.py](../../src/diagnostics.py) | `SystemLogRecord.to_dict` 37, `emit` / payload 122 | Esquema log |
| [packet_buffer.py](../../src/packet_buffer.py) | `CapturedPacket` 24, `to_dict` 47, `record` 90 | Esquema captura y redacción |
| [contact_manager.py](../../src/contact_manager.py) | `NodeContactInfo.to_dict` 631 | Esquema nodo |
| [map_tile_service.py](../../src/web/map_tile_service.py) | `_reload_mbtiles` 59, `_get_tile` 98, `_detect_mime` 144, `_get_status` 168 | XYZ/MBTiles y metadatos |
| [security_inspector.py](../../src/web/security_inspector.py) | `extract_client_ip` 116, `inspect_http_request` 163 | IP del socket y filtro heurístico |
| [shared_utils.py](../../src/shared_utils.py) | `sanitize_public_payload` 412 | Omisión recursiva de secretos SDK |

## 2. Autenticación y CORS efectivos

`BRIDGE_API_KEY` se lee del entorno por petición/handshake. Vacía: las rutas
protegidas se permiten en modo desarrollo con warning; WS también se permite.
Configurada: credencial UTF-8 comparada con `hmac.compare_digest`.

Precedencia exacta (`_extract_api_key`, http_server.py:649):

1. `X-Api-Key` no vacía gana incluso si es incorrecta y el query contiene la correcta.
2. Sin cabecera no vacía, se usa un único `api_key` del query, con percent decoding
   de `parse_qs(..., keep_blank_values=True, errors="strict")`.
3. Cero o múltiples valores `api_key`, valor vacío o fallo de decodificación no
   acreditan autenticación. `Authorization: Bearer ...` no se interpreta.

Ejemplo seguro: `X-Api-Key: <clave-de-prueba>` o `/ws?api_key=<clave-de-prueba>`.
No copiar claves operativas al documento, trazas o evidencias.

### Matriz del guard de autenticación (antes del router y de normalizar aliases)

| Ruta / conjunto de rutas | Métodos alcanzados | Con clave configurada |
| --- | --- | --- |
| Prefijos `/api/node/reboot`, `/api/config/reboot`, `/api/admin`, `/api/tx`, `/api/repeater`, `/api/config/radio`, `/api/node/config/radio` | Todos los métodos que llegan al guard | Requiere clave |
| Exactas `/api/logs/download`, `/api/logs/raw`, `/api/system/logs`, `/api/diagnostics/export`, `/api/diagnostics/report`, `/api/diagnostics/report.md`, `/api/channels/export`, `/api/packets`, `/api/packets/export` | Todos, incluido GET/HEAD | Requiere clave |
| Cualquier `/api/...` restante | POST, PUT, DELETE, PATCH | Requiere clave |
| Cualquier `/api/...` restante | GET, HEAD y otros métodos | No requiere clave en este guard; el router aún puede rechazar el método |
| `/api/map/tiles/...` | GET | Bypass del guard; lectura pública |
| `/api/map/tiles/...` | Cualquier método distinto de GET, incluido HEAD | 405 antes del guard |
| WS upgrade | Cualquier ruta que supere ingreso y Origin | Requiere clave |
| OPTIONS sin upgrade | Todas las rutas | 204 preflight sin autenticación |
| SPA/estáticos | Fuera de API y sin upgrade | No exige clave |

Los prefijos usan `startswith`, sin límite de segmento; no confundir esta matriz
con rutas existentes. Un prefijo protegido desconocido puede devolver 401 antes
de alcanzar su 404/405. `clean_p` elimina query y slash final. Los aliases del
router se aplican después: revisar cada alias frente al guard al migrar, evitando
que una lectura sensible pierda protección. La excepción GET `/api/nodes` dentro
del primer bloque no convierte GET `/api/repeater...` en público.

REST sin credencial válida: 401 `application/json`, `{"error":"Unauthorized"}`;
HEAD conserva Content-Length de ese JSON pero suprime cuerpo. Handshake WS:
401 cuerpo de texto `401 Unauthorized`, sin tipo explícito. No cambiar estos
errores a 422 automáticos por usar un modelo Pydantic.

### Origin y cabeceras

`BRIDGE_ALLOWED_ORIGINS` por defecto contiene `http://localhost:8080` y
`http://127.0.0.1:8080`. `_is_origin_allowed` además permite: ausencia de Origin,
`*`, coincidencia exacta de allowlist, Origin cuyo esquema http/https eliminado
coincida con Host (case insensitive), localhost/127.0.0.1 por su parser,
y direcciones con prefijo 192.168, 10, 127 o 172.16..31 y cuatro partes numéricas.
Aunque la condición menciona `::1`, el parser `split(":")[0]` no reconoce ese
host IPv6; IPv6 puede admitirse por coincidencia exacta de allowlist o Host.
No valida rigurosamente rango de octetos ni IPv6: registrar esto como política
previa amplia, no como allowlist estricta ni garantía de seguridad.

REST con Origin rechazado continúa sin `Access-Control-Allow-Origin`; WS con
Origin presente rechazado devuelve 403 y no acepta el socket. Ausencia de Origin
no impide clientes WS no navegador. IP auditada es la del peer del socket; se
ignoran `X-Forwarded-For` y similares por falta de un límite de confianza proxy.

Preflight: 204, `Allow-Methods: GET, POST, OPTIONS, DELETE`,
`Allow-Headers: Content-Type, Authorization, X-Api-Key`, `Max-Age: 86400`,
`Connection: close`; incluye Allow-Origin sólo cuando se acepta. Respuestas
normales con CORS permiten los mismos métodos, pero sólo `Content-Type, X-Api-Key`.
No se emite Allow-Credentials. La ausencia de PUT/PATCH/HEAD en preflight es
comportamiento previo; declarar una política nueva requiere decisión consciente.

Respuestas construidas por `_build_http_response` (http_server.py:998):
Content-Length de bytes servidos, `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Connection: close`. HTML añade CSP:

```text
default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com;
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com;
font-src 'self' https://fonts.gstatic.com data:;
img-src 'self' data: blob: https: https://*.tile.openstreetmap.org https://*.basemaps.cartocdn.com https://unpkg.com;
connect-src 'self' ws: wss: https:; frame-ancestors 'none'
```

Excepciones existentes: el 101, preflight y respuesta cruda 413 no pasan por ese
constructor y no poseen todas esas cabeceras. No asumir que cabeceras de seguridad
o CSP cubren todos los caminos. El filtro heurístico rechaza scanner UA,
traversal y rutas sensibles con 403; sus patrones incluyen `/swagger-ui` y
`/api-docs` (security_inspector.py:68). Las futuras rutas de documentación deben
definirse deliberadamente. En el ingreso actual se inspecciona path sin query y
`body_dict=None`: su comentario sobre inspección de query/cuerpo no acredita
que esas verificaciones se ejecuten en este flujo.

## 3. Contrato de conexión WebSocket

SPA abre `/ws`, ws/wss según protocolo del documento y mismo host/puerto. Consulta
`meshcore_bridge_api_key`, con fallback `bridge_api_key` del localStorage, y envía
la clave en query usando encodeURIComponent. REST usa principalmente la primera
clave y X-Api-Key (utils.js:81, app.js:833). Mantener compatibilidad con esa
diferencia hasta migrar conscientemente el cliente.

Servidor actual no restringe upgrade a `/ws`, no exige aquí método GET, versión
13 ni valida forma/longitud de Sec-WebSocket-Key. Condición de despacho:
`Upgrade: websocket` y existencia de `Sec-WebSocket-Key`; ocurre antes de
OPTIONS/API/estáticos (http_server.py:460). Esta amplitud es un comportamiento
previo a revisar, no un requisito de abrir nuevas rutas WS con FastAPI.

Orden: inspección HTTP/cuerpo → Origin (403) → cupo 32 (429 texto) → clave (401)
→ 101 `Upgrade`, `Connection: Upgrade`, `Sec-WebSocket-Accept` SHA1+base64
→ incorporar writer → dos frames iniciales → bucle de lectura. No subprotocolo,
cookie, negociación de extensiones o compresión WS explícita.

El cupo de 32 es un chequeo previo, no una reserva atómica: el handshake espera
`drain()` antes de añadir el writer al conjunto, sin lock o contador reservado.
Handshakes concurrentes pueden superar ese número. Los drains del 101 y del
estado inicial no tienen timeout; tampoco el Pong JSON de heartbeat (a diferencia
del Pong RFC, acotado a 2 s). Si el estado inicial falla tras registrar el writer,
todavía no se ha entrado al `finally` del bucle de mensajes: `_handle_client`
cierra el writer ante la excepción pero no lo retira inmediatamente del conjunto.
Son defectos previos de concurrencia/apagado que debe revisar la implementación;
no presentar cupo y cierre como garantías verificadas por esta lectura.

Frames servidor: FIN texto, UTF-8 `json.dumps(..., default=str)` sin máscara.
Cliente: frame enmascarado, FIN obligatorio, RSV=0, opcode 1/2/8/9/10;
continuación/fragmentación no soportadas. Infracciones: Close 1002. Control máximo
125 bytes, Close de un byte inválido. Texto UTF-8 inválido: Close 1007. Frame
mayor de 1 MiB: cierre sin código explícito. Binario recibido y Pong RFC válidos
se ignoran en aplicación. Close cliente se confirma con sus primeros dos bytes
o 1000 cuando no hay código; no se refleja la razón completa.

Idle entre frames provoca Ping RFC vacío y continúa, no acredita expulsión por
falta de Pong. JSON inválido/no objeto/tipo desconocido se ignora. Único mensaje
entrante con efecto de aplicación:

```json
{"type":"ping","timestamp":1700000000000}
```

Respuesta `{"type":"pong","timestamp":1700000000}`: epoch entero en segundos;
timestamp entrante JS en ms no se refleja. No existe envío de chat/admin por WS
en el bucle; se hace por REST/otros ingress. No inventar comando WS TX.

### Límites y timers existentes, sin cambio autorizado

| Recurso | Valor actual / fuente | Alcance |
| --- | --- | --- |
| HTTP cabeceras | 65.536 bytes acumulados; 10 s lectura / http_server.py:299..337 | Ingreso |
| HTTP body | 1 MiB; Content-Length no negativo; 10 s readexactly / 383..437 | JSON objeto; Transfer-Encoding produce 400; sin Content-Length se usa `{}` |
| WS conexiones | Chequeo 32 writers / 700 | Previo a auth; sin reserva atómica durante handshake |
| WS payload | 1 MiB / 880 | Frame entrante |
| WS idle | env `WS_IDLE_TIMEOUT_SEC`, default 30 s / 879 | Dispara Ping de transporte |
| WS lectura parcial | 10 s por longitud/máscara/payload / 920..936 | Cierre si timeout |
| WS métricas | env `WS_METRICS_INTERVAL_SEC`, default 5 s / 147 | Lee memoria; no consulta radio en ese loop |
| WS broadcast drain | 2 s por writer / 218 | Secuencial; writer lento se elimina/cierra |
| WS handshake, initial y Pong JSON drain | Sin timeout / 754, 818, 858 | Diferente al límite del broadcast y Pong RFC |
| SPA heartbeat | 15.000 ms / websocket.js:150 | Sólo JSON ping al servidor |
| SPA reconexión | 1.000 ms inicial, duplica hasta 30.000 ms, jitter 25% limitado / 130 | HTTP/WS, no RF |
| Historial router | mensajes 200, telemetría 200, logs 300 / api_router.py:121..123 | Buffers RAM |

Los defaults del HTTP server leen `os.getenv` directamente; no confundirlos con
validación de config.py. No existe aquí límite global HTTP de clientes ni rate
limit HTTP por IP. Cambiar estos números o crear timers RF requiere el checklist
y consulta al usuario previstos en AGENTS.md.

## 4. Catálogo de mensajes salientes y consumidores

El servidor es un bus de diccionarios abiertos. No existe una unión cerrada de
schemas Pydantic. El adaptador SPA decide `String(type || event_type || event ||
"").toLowerCase()`, con prioridad distinta a algunos consumidores secundarios.
Conservar campos/discriminadores de productores, no renombrarlos globalmente.

| Evento/discriminador en wire | Estructura emitida | Productor y consumidor |
| --- | --- | --- |
| `event_type=ws_connected` | `message:string`, `timestamp:int` epoch s | HTTP 758; entra como RX_PACKET genérico, sin handler especial |
| `type=event=metrics_update` | Esquema M descrito abajo; initial añade `radio_port` | HTTP 177/792; METRICS_UPDATE → app 621, settings 1167, sniffer 259, analytics 219 |
| `type=event=rf_packet` | `data:CapturedPacket` | RX router 324/379, bridge TX 875; RF_PACKET → sniffer 244, analytics 217, nodes 155 |
| `event_type=system_log` | `data:SystemLogRecord` | diagnostics 123 → bridge 217; SYSTEM_LOG → sniffer 250 |
| `type=event=duty_cycle_alert` | `level`, `status_level`, `hourly_duty_cycle_pct`, `hourly_limit_pct`, `warn_threshold_pct`, `hourly_used_ms`, `hourly_budget_ms`, `timestamp:float epoch s` | bridge 1052; DUTY_CYCLE_ALERT → app 643, analytics 229 |
| `type=event=airtime_cutoff_change` | `active:bool`, `channel_utilization_pct`, `threshold_pct`, `resume_pct`, `timestamp:float epoch s` | bridge 1084; AIRTIME_CUTOFF_CHANGE → app 649 |
| `type=event_type=public/channel/direct` | Esquema C abajo | RX router 1020; RX_PACKET → chat 303; presence se actualiza además mediante contact_updated |
| `type=event_type=message_delivered` | `msg_id`, `ack_code:8hex`, `trip_time_ms` nullable, `sender` | repeater_handler 113; RX_PACKET → chat 307/1645, nodes 124 |
| `type=event_type=contact_discovered/contact_updated` | `contact:NodeContactInfo.to_dict()`, `is_new:bool` sólo en descubrimiento/actualización de advert | RX router 764/824/869/924/1013/1178, repeater_handler 148, repeater_executor 591/879; RX_PACKET → nodes 107, chat 317, repeater 872 |
| `type=contacts_updated` | `data:list` de `node_registry.list_nodes()` | contacts_controller 465/544/568; RX_PACKET → nodes 98, chat 317 |
| `type=channels_updated` | `data:list` de canales enmascarados | channels_controller 328/365; RX_PACKET → settings 1154 |
| `type=self_info` (controlador) | `data:dict` configuración redactada, `timestamp:int epoch s` | config_controller 177/253; RX_PACKET → settings 1161 usa data, app 667 pasa payload |
| `type=clock_synced` | `clock`, `epoch`, `timestamp:int epoch s` | config_controller 211; RX_PACKET → settings 1162 |
| `type=metrics_reset` | `timestamp:int epoch s`; nodes añade `event=metrics_reset` | config_controller 243, nodes_controller 119; RX_PACKET genérico, sin handler dedicado encontrado |
| `type=event_type=repeater_response` | `sender`, `sender_name`, `text` redactado, `channel_idx`, `channel_index`, `telemetry:dict/null`, `rssi`, `snr`, `timestamp:ISO UTC` | RX router 973; RX_PACKET → repeater 865, sólo emisor del repetidor seleccionado |
| `type=trace_data` | `data:dict` de respuesta trace variable | repeater_handler 192, traceroute_executor 139; RX_PACKET genérico, sin handler trace dedicado encontrado |
| Telemetría `event_type=self_info/device_info/battery/stats_core/stats_radio/tuning/time/telemetry` y tipos ya presentes del SDK | Dict abierto normalizado: campos originales seguros + `timestamp:ISO UTC`, sender/name cuando resueltos, campos extraídos; bytes → hex | RX router 427/1095..1194; RX_PACKET → settings, app, nodes, repeater según discriminador |
| Resto de eventos de SystemHandler | Payload SDK saneado + `event_type` minúscula si falta + `timestamp` ISO UTC si falta | system_handler 23/50/74/87; RX_PACKET genérico y consumidores según tipo |

SystemHandler reconoce también `path_update`, `messages_waiting`, `new_contact`,
`contact_deleted`, `contacts_full`, `neighbours_response`, `discover_response`,
`binary_response`, `control_data`, `mma_response`, `acl_response`, `sign_start`,
`signature`, `allowed_repeat_freq`, `default_flood_scope`, `stats_packets`,
`tuning_params`, `custom_vars`, `autoadd_config`, `advert_path`, `contact_uri`,
`status_response`, `login_success`, `login_failed` y tipos compartidos con otras
estrategias. Son candidatos del handler, no promesa de que todos alcancen siempre
WS: el router puede interceptarlos antes. `channel_info` actualiza canales internos
y retorna sin broadcast; vacío también retorna. `log_data`/`rx_log_data` se
procesan como observación RF en RX antes de estrategias. `ack` se deriva a
message_delivered sólo si existe correlación local válida. No emitir un ACK
arbitrario confiando en request_id entrante.

### Esquemas abiertos que debe preservar el transporte

**M, metrics_update:** siempre `event`, `type`, `node_count`, `rx_count`,
`tx_count`, `error_rate` (porcentaje a 1 decimal de errores TX+RX / RX+TX),
`queue_depth`, `serial_connected`, `radio_connected`, `uptime` (segundos enteros),
`uptime_str`, `airtime_ms`, `duty_cycle_pct`, `hourly_limit_pct`,
`warn_threshold_pct`, `is_warning`, `is_critical`, `status_level`, `channel_stats`,
`airtime` (dict completo), `duplicate_packets`, `packet_errors`. Initial añade
`radio_port:string`; broadcast periódico no lo añade. Conectividad usa
`is_hardware_alive()` cuando existe, fallback `is_connected`. No sondea RF aquí.

`airtime` viene de [rate_limiter.py](../../src/rate_limiter.py):440/481:
`hourly_used_ms`, `hourly_budget_ms`, `hourly_duty_cycle_pct`, `hourly_limit_pct`,
`warn_threshold_pct`, `hourly_packets`, `daily_used_ms`, `total_airtime_ms`,
`total_packets`, `is_throttled`, `is_warning`, `is_critical`, `status_level`,
`channel_utilization_pct`, `cutoff_active`, `cutoff_enabled`,
`cutoff_threshold_pct`, `cutoff_resume_pct`, `last_tx_time`,
`channel_stats:{channel:{airtime_ms,packets}}`. JSON convierte claves numéricas
de canal a strings. Si no existe tracker, `airtime={}` y se usan defaults del
productor. Esos defaults no autorizan fijar nueva política de airtime.

**C, chat:** `type`, `event_type`, `is_direct:bool`, `sender`, `sender_name`,
`text`, `channel_idx`, `channel_index`, `txt_type`, `rssi`, `snr`, `lqi_score`,
`lqi_status`, `metrics:{rssi,snr,lqi_score,lqi_status}`, `telemetry:dict/null`,
`timestamp:ISO UTC`, `sender_timestamp`. No se inventa `msg_id` RX: chat.js:1613
usa payload.msg_id o genera uno local. canal 0 → public, resto → channel.
El historial REST se alimenta de `broadcast_event` antes de mirar conexiones;
puede registrar eventos aunque ningún cliente esté conectado. No moverlo dentro
de un `if clients` en la migración. No insertar comandos admin como chat.

**CapturedPacket:** `packet_id:int`, `timestamp:float`, `iso_time:string`,
`direction:rx/tx`, `channel_idx:int`, `packet_type:string`, `sender`,
`sender_name`, `target`, `text`, `rssi:int/null`, `snr:float/null`,
`lqi_score:float/null`, `lqi_status`, `payload_dict:dict`, `size_bytes:int`,
`session_id`, `raw_hex:string`; `raw_bytes` no sale en JSON. La captura redacta
CLI/private/admin antes de publicar. No usar el envelope como captura cruda segura
sin conservar las guardas de packet_buffer.record.

**SystemLogRecord:** `timestamp:float epoch s`, `iso_time`, `level`, `logger`,
`module`, `func`, `line:int`, `message`, `exception:string/null`, `source`.
El historial `recent_system_logs` del router tiene otra forma:
`timestamp:int`, `iso_time`, `level`, `source`, `message`; no equipararlos.

**NodeContactInfo:** dict plano resultante de las dataclasses NodeIdentity,
NodeRfMetrics y NodeTelemetry (contact_manager.py:47..130) más campos derivados
en to_dict: `key_prefix`, `total_packets`, `error_rate_pct`, `lat`, `lon`,
`distance_m`, `out_path_hash_mode_raw`, `min_tx_power`, `default_tx_power`,
`tx_power_limits_source`, `presence_status`, `status_label`, `last_seen_iso`,
`last_seen_formatted`. Mantener campos opcionales nulos y rutas completas, no
reducirlo a public_key/name/role. `presence_status` online/idle/offline y LQI se
derivan al serializar. `distance_m` es null en broadcasts sin coordenadas locales.
Un evento de nodos puede representar un repetidor; eso no autoriza incluirlo en
la libreta CLIENT ni habilitar DM. LOCAL no debe duplicarse ni ser destino TX.

Canales enmascarados usan `_get_masked_channels_list` (channels_controller.py:173):
orden por índice, copia de campos internos como index/name/channel_hash y campos
derivados `has_psk:bool`, `is_encrypted:bool`, `is_public:bool`; índice 0 público
sin cifrado ni PSK; restantes con PSK usan el literal `••••••••`, sin PSK usan
string vacío. No sustituirlo por dicts internos con PSK.
`sanitize_public_payload` elimina recursivamente private_key,
privatekey, channel_secret, secret, secrets, psk, password, passwd, admin_password,
mqtt_password, pin, token, api_key, normalizando case y guiones. También convierte
bytes a hex y floats no finitos a null. `broadcast_event` no hace por sí mismo
esta redacción universal: conservar la de cada productor/controlador.

Ejemplo de entrega sintético:

```json
{"type":"message_delivered","event_type":"message_delivered","msg_id":"req-demo-1","ack_code":"1234abcd","trip_time_ms":420,"sender":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

No existen replay/resume de WS, sequence number universal o confirmación de
recepción del navegador. `send()` del cliente acepta objetos/string, pero no
amplía lo que reconoce el servidor. El adaptador desempaqueta rf_packet con
`payload.data || payload.packet || payload`, system_log con
`payload.data || payload`; el último fallback es el objeto completo, no un campo
`payload.payload`. El resto se
mantiene. Los enums del EventBus contienen nombres sin productor WS dedicado
(por ejemplo TX_STATUS/NODE_DISCOVERED); no son pruebas de nuevos eventos wire.

## 5. SPA, MIME, caché y HEAD

`/`, chat/map/nodes/contacts/settings/telemetry/logs/analytics sirven index.html.
Una ruta inexistente sin sufijo también hace fallback SPA; una con sufijo devuelve
404 texto. Query se elimina para resolver archivo. Resolución canónica dentro de
static_dir y guardas traversal rechazan escape/symlink externo con 403.
StaticFiles estándar no acredita por sí solo este fallback: conservarlo en un
handler o definir explícitamente el cambio. API se despacha antes y no cae al SPA.

Servidor actual admite métodos estáticos sin filtro GET/HEAD; documentado como
comportamiento previo, no recomendación. HEAD de estático 200 omite cuerpo y
conserva Content-Length de representación seleccionada (gzip o raw). Errores
estáticos 403/404/500 no siempre suprimen el cuerpo de HEAD; no generalizar soporte.

MIME via `mimetypes.guess_type`; fallback HTML para .html, octet-stream para otro.
Añade `; charset=utf-8` a todos los MIME estáticos si no existe, incluidos
binarios. Cache RAM por path + mtime; ETag SHA256(raw) primeros 16 hex entre
comillas. Validación admite coincidencia exacta, weak `W/` y búsqueda de valor
entre comillas en If-None-Match; devuelve 304 vacío, con MIME, ETag, Vary.
HTML: `Cache-Control: no-cache, no-store, must-revalidate`; otros:
`public, max-age=300`. Vary Accept-Encoding en 200/304.

Gzip nivel 6, sólo textual (>256 bytes) por sufijo o MIME y si resultado es menor;
selección Accept-Encoding con q-values y q>0. El helper primero exige substring
literal `gzip`; `*` solo no basta y algunas variantes de mayúsculas no activan
compresión. ETag es común raw/gzip. No usar defaults de middleware de compresión
como evidencia de paridad. Falta index: fallback HTML de inicialización 200.
Lectura/stat/compresión estáticos son síncronos actualmente en el event loop:
registrar como problema previo a abordar, no capacidad no bloqueante acreditada.

## 6. Teselas y estado de mapas

GET `/api/map/tiles/{z}/{x}/{y}.ext`: parser acepta al menos 3 segmentos,
interpreta y antes del primer punto, ignora extensión solicitada y segmentos
extra. Coordenadas z 0..22 y 0<=x,y<2**z; inválido/ausente retorna 404 vacío
`image/png`. HEAD retorna 405 JSON. No ETag ni compresión HTTP adicional;
éxito binario 200 con MIME real y `Cache-Control: public, max-age=86400`.
Este handler ocurre antes de auth, por lo que las teselas son públicas.

MapTileService usa data_dir/config.DATA_DIR y crea `maps`/`maps/tiles` al
construirse. No instanciarlo en inspección documental. Búsqueda XYZ primero,
extensiones png→jpg→jpeg→webp→pbf, con pertenencia canónica. Luego MBTiles *.mbtiles
sin orden explícito; SQLite readonly, check_same_thread=False, protegido RLock.
`scheme` metadata xyz usa y directo; cualquier otro valor/default tms usa
(2**z)-1-y. Consulta parametrizada tabla `tiles`, LIMIT 1. reload cierra conexiones
anteriores y reindexa; servidor llama get_tile por asyncio.to_thread y stop cierra.

Magic MIME: PNG, JPEG, RIFF/WEBP; magic gzip → application/x-protobuf.
Fallback según extensión; MBTiles sin magic conocido usa png por defecto. Los
bytes de pbf gzip no llevan Content-Encoding: gzip en el handler actual; registrar
defecto previo para una decisión separada, evitando recompresión accidental.
SPA map.js:20 usa por defecto URL .png aunque servicio puede retornar otro MIME.

GET `/api/map/status`: 200 `{"status":"ok","data":S}` público.
POST `/api/map/reload` (alias `/api/map/refresh`): protegido por regla mutaciones;
200 `{"status":"ok","message":"Archivos MBTiles reindexados correctamente","data":S}`;
método distinto POST 405, fallo reload 500 problem_details. S:

```text
has_local_maps: bool
maps_directory: string (ruta absoluta)
tiles_directory: string (ruta absoluta)
mbtiles_count: int
mbtiles_files: [{filename:string, size_mb:number, name:string, format:string,
                min_zoom:string, max_zoom:string, description:string}]
has_loose_tiles: bool
```

`min_zoom/max_zoom` son strings de metadata, no int garantizado; defaults 0/18.
No convertir tipos silenciosamente. Exponer rutas absolutas en lectura pública
es comportamiento previo con impacto de información; distinguirlo de secreto.

## 7. Invariantes y pendientes de aceptación

Conservar antes de declarar paridad: discriminadores y envelopes, historia
independiente de clientes, autenticación común REST/WS y precedencia, omisión de
secretos, correlación de ACK de un solo uso, CLIENT/REPEATER/LOCAL, rechazo de
traversal, límites ya configurados y cierre de recursos. No transformar el WS
en un origen adicional de transmisiones RF o publicación MQTT automática.

Decisiones separadas, sin corregir producción en fase 0: restringir upgrade a
/ws y handshake estándar; política Origin/Host; errores HEAD; métodos estáticos;
MIME/charset binarios; Accept-Encoding; PBF gzip; auth de aliases; exposición de
rutas de mapas; defaults y validación de env; reserva atómica del cupo WS;
drains sin timeout y limpieza si falla el estado inicial; cola/backpressure por cliente;
historia/discriminadores abiertos. La divergencia comprobada debe quedar
registrada al cambiar un contrato, sin copiar vulnerabilidades por inercia.

Pruebas de aceptación pendientes de autorización explícita: REST y HEAD aislados,
credenciales ambiguas y Unicode, Origin y rechazo de handshake, conexión WS real
en loopback con heartbeat/cupo/cierre/frames, consumers SPA, ETag/gzip/fallback,
XYZ y MBTiles TMS/XYZ/gzip con archivos temporales. Un httpx.AsyncClient con
ASGITransport valida HTTP; no valida WebSocket real, RFC framing, handshake o
apagado de sockets. No atribuir esas garantías a una lectura estática o al mero
uso de FastAPI.
