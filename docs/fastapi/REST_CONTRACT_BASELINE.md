# Fase 0: contrato REST observado antes de FastAPI

Fecha: 2026-10-08. Base de lectura: HEAD `457903ddf623768a1c5f90f952fb8b77db45e0c6` y archivos presentes. Responsable: agente de contratos REST; integración y publicación: líder. Skill aplicada: `contract-openapi-sync`. Este catálogo describe lectura estática, sin importar la aplicación, ejecutar suites, arrancar servicios o consultar hardware/datos operativos. No acredita ejecución, interoperabilidad o ausencia de fallos.

## Alcance, fuentes y notación

Se inspeccionaron [router](../../src/web/api_router.py), [servidor HTTP](../../src/web/http_server.py), los diez [controladores](../../src/web/controllers/), [BaseController](../../src/web/controllers/base.py), [MapTileService](../../src/web/map_tile_service.py), consumidores SPA y flujo n8n. Los números de línea siguientes corresponden a ese checkout. Auth y transporte se complementan con [WEB_CONTRACT_BASELINE.md](WEB_CONTRACT_BASELINE.md); propiedad de estado con [INTERNAL_CONTRACT_BASELINE.md](INTERNAL_CONTRACT_BASELINE.md).

Notación: `OK` significa `{"status":"ok",...}`; `PD` significa error de `problem_details`; `CF` significa la traducción de rechazo del comando en BaseController. `P` indica autenticación condicionada a `BRIDGE_API_KEY` configurada, `U` lectura pública, `T` tile anterior a auth. Los códigos de las tablas son los explícitos; **toda operación JSON puede terminar en 500 PD por excepción no capturada por su controlador**. Para CF se conserva el código remoto entero 400..599 cuando es válido, además de 400/422/503 descritos abajo. No reducir el catálogo a 200/422.

RF/efecto: `pasivo` = lectura de estado recibido, sin consulta RF iniciada por ese endpoint; `serial` = lectura/escritura Companion local, no equivalencia automática con transmisión RF; `RF` = puede transmitir según operación/ejecutor; `local` = buffers, disco o configuración host; `red` = conexiones MQTT/TCP. No se han medido cantidades de paquetes ni airtime. Este inventario no añade límites, intervalos, reintentos ni notificaciones.

## Conteo sin doble conteo

| Familia | Operaciones JSON funcionales método + ruta/plantilla | Rutas/plantillas distintas |
|---|---:|---:|
| Sistema y diagnóstico | 11 | 9 |
| Nodos y analítica | 8 | 7 |
| Contactos, incluidos discovered/accept | 11 | 8 |
| Canales | 6 | 3 |
| TX e historial reciente | 2 | 2 |
| Repetidores/admin | 15 | 15 |
| Configuración | 22 | 13 |
| Servicios | 6 | 4 |
| Paquetes | 3 | 2 |
| Mapas e historial adicional | 6 | 6 |
| **Subtotal JSON** | **90** | **69** |
| Tile binario, patrón | 1 | 1 |
| **Subtotal API funcional** | **91** | **70** |

`GET /api/logs` se enumera aparte: el dispatcher lo reconoce, pero LogsController siempre devuelve 404 `log_not_found`. No se cuenta como funcional. Las 39 claves de `ROUTE_ALIASES` añaden 50 combinaciones método + alias, sin volver a contar los destinos. Total de combinaciones funcionales conocidas con alias: **141**; total de rutas/plantillas con alias: **109**. La tabla conserva `/api/health` y `/api/diagnostics`, los dos reportes y las dos rutas de ping/traceroute explícitas como rutas distintas: no pertenecen al diccionario de aliases. OPTIONS general y estáticos no entran en ese total. Patrones permisivos de tiles y suffix de presets representan familias infinitas, no cantidad de URLs concretas.

## Semántica común HTTP y router

- HTTP convierte método a mayúsculas; las llamadas directas al router no hacen esa conversión. El servidor dirige únicamente paths que empiezan por `/api/` a API; `/api` sin slash se trata como estático. No hay 307 automático.
- Router `handle_request`, líneas 307–393: separa `?`, elimina **todas** las barras finales y aplica una vez el alias exacto. `dict(body) if body else {}` se construye antes de su `try`: HTTP ya exige objeto, pero llamadas internas con tipos inesperados pueden fallar fuera del PD global.
- Query se parsea con `parse_qs(..., keep_blank_values=True)` y se fusiona sólo si la clave no existe en body. Un valor repetido queda lista; body gana aunque su valor sea null/false/vacío. Campos desconocidos no se rechazan globalmente. Algunos controladores ignoran esos campos; config/admin reenvían el diccionario. **LogsController es excepción:** vuelve a parsear query cruda y no usa el body fusionado.
- HTTP `_read_request_body`, líneas 387–447: sin Content-Length o longitud 0 ⇒ `{}`; JSON `{}` válido; JSON `null`, array, número, texto o booleano ⇒ 400 `{"error":"Bad Request","detail":"Malformed JSON payload"}`; UTF-8/JSON malformado igual. Content-Type no se usa para exigir JSON. Transfer-Encoding presente ⇒ 400 texto, Content-Length inválido/negativo ⇒ 400 texto, >1 MiB ⇒ 413 directo sin envelope; lectura incompleta/timeout 10 s cierra conexión sin una respuesta JSON prometida.
- JSON de controlador se serializa `json.dumps(..., indent=2, default=str)` UTF-8; Content-Type `application/json`, incluso PD. **204** se convierte en body vacío y sin Content-Type; `HEAD` conserva status calculado y Content-Length de representación pero omite cuerpo. HEAD no se convierte en GET en router y normalmente recibe 405; excepciones 404 documentadas abajo.
- Cabeceras comunes: Content-Length, X-Content-Type-Options `nosniff`, X-Frame-Options `DENY`, Referrer-Policy `strict-origin-when-cross-origin`, Connection `close`. CORS permitido añade origen concreto, métodos `GET, POST, OPTIONS, DELETE`, headers `Content-Type, X-Api-Key`. API JSON no añade cache, ETag, gzip, Content-Disposition, Allow ni Retry-After. Excepciones de lectura/perímetro y OPTIONS no pasan todas por el mismo constructor.
- `OPTIONS` de cualquier path pasa por preflight antes del router/auth: 204 sin cuerpo, Access-Control-Allow-Methods `GET, POST, OPTIONS, DELETE`, Access-Control-Allow-Headers `Content-Type, Authorization, X-Api-Key`, Max-Age 86400; Allow-Origin sólo cuando permitido. Esto no implementa autenticación Bearer.
- Auth se evalúa **antes de canonicalizar alias**, sobre ruta cruda sin query/barras finales. Todos POST/PUT/DELETE/PATCH `/api/` requieren clave si configurada, además de prefijos protegidos y lecturas sensibles de la matriz. Clave vacía en entorno omite auth. Prioridad X-Api-Key no vacío; si falta, exactamente un `api_key` query. Rechazo 401 `{"error":"Unauthorized"}`. Tiles se despachan antes de auth.
- Parámetros enteros paginados del router usan `int(val)` (pueden aceptar bool y truncar floats), null o `""` ⇒ default; límites ⇒ 400 `param_out_of_bounds`, coerción fallida ⇒ 400 `invalid_integer_param`. No generalizar esa coerción a índices/modes que rechazan bool/float.
- `to_bool` [shared_utils.py](../../src/shared_utils.py), línea 373: null ⇒ default; bool igual; numérico !=0; strings true/1/yes/on/t y false/0/no/off/f/vacío; string no reconocido ⇒ default; otros ⇒ bool(). Servicios/presets usan en varios campos `bool()` nativo, por lo que `"false"` puede ser verdadero allí.

### Envelope de errores y comandos

`PD`, base.py:29: `type=urn:meshcore:error:<error_code o status>`, `title`, `status` **numérico**, `detail`, `error`, `message`, `timestamp` segundos float; extras pueden sobrescribir campos. El catch global expone `str(exception)` en `detail/message` y registra log; documentar esa conducta no la avala como política futura.

`CF`, BaseController.command_failure:61 / serial_mutation:94: None/False ⇒503 `command_unconfirmed`; estados OK/SUCCESS/SENT/DELETED/CLEARED sin error ⇒ éxito; ERROR/FAILED/PARTIAL/NOT_SUPPORTED/LOCAL_ONLY/LOCAL_DELETED o campo error ⇒ código válido remoto 400..599, fallback 400 o503 para NOT_SUPPORTED/LOCAL*. Error `command_failed` o `command_partial`, extras `applied/config/action/dispatched_commands/target_node`, PARTIAL añade partial=true. Estado desconocido no vacío ⇒503. Resultados sin status y eventos sin marcador error se aceptan. Serial mutation ausente ⇒503 `serial_unavailable`, ValueError/TypeError ⇒422 `invalid_serial_parameters`, otra excepción ⇒503 `serial_operation_failed`. **No implica ACK remoto**. RepeaterController acepta expresamente status `dispatched` sin error; en rechazos agrega `data` redactada.

## Catálogo por operación

Cada fila singular corresponde a una combinación método + ruta/plantilla; los parámetros usan la fusión común salvo la excepción Logs. Fuente de dispatcher: api_router.py `_dispatch_*`; fuente de implementación: función concreta/línea citada.

### Sistema y diagnósticos

Fuentes: router `_dispatch_system`:395; SystemController get_status:51, get_health:71, clear_logs:84, run_preflight:94; LogsController route_logs:18 / get_system_logs:70 / report:113.

| Método | Ruta | Auth | Entrada/default/coerción | Respuesta/status | Efecto; consumidor identificado |
|---|---|---|---|---|---|
| GET | `/api/status` | U | ninguna |200 OK + uptime_seconds, uptime_str, health, rx_count, tx_count, error_count, timestamp |pasivo; diagnóstico externo posible, sin consumidor literal SPA localizado |
| GET | `/api/health` | U |ninguna |200 OK data health |pasivo |
| GET | `/api/diagnostics` | U |ninguna |200 OK data health, mismo get_health |pasivo; sniffer.js:687 |
| GET | `/api/preflight` | U |ninguna; checker toma configuración host |200 OK data reporte de run_all_async o thread; no traduce fallos de checks a status HTTP |red/serial/chequeos locales según PreflightChecker; no se ejecutó |
| GET | `/api/diagnostics/report.md` | P |ignora limit/offset una vez parseados |200 OK markdown,text iguales; fallback texto no disponible |local; sin descarga HTTP raw |
| GET | `/api/diagnostics/report` | P |igual report.md |200 OK markdown,text |local; app.js:540 |
| GET | `/api/diagnostics/export` | P |ninguna |200 OK data bundle si DiagnosticManager; sin manager 200 {status:error,message:"No diagnostics"} |local; generate_full_diagnostic_bundle en thread |
| GET | `/api/system/logs` | P |query limit=100, sólo isdigit; level/search primer valor, offset parseado pero no usado |200 OK data[],count,counters{errors,warnings,info,debug},current_level,total_logs |pasivo; sniffer.js:665 |
| DELETE | `/api/system/logs` | P |ninguna |204 vacío, limpia deque/handler |local; sniffer.js:876 |
| GET | `/api/system/logs/level` | U |ninguna |200 OK level; fallback INFO |pasivo; app.js:551 |
| POST | `/api/system/logs/level` | P |level=INFO convertido str |200 OK level;400 invalid_log_level o diagnostic_unavailable |local; app.js:555 / sniffer.js:839 |

Health devuelve snapshot de bridge si dict, después diagnóstico si dict, después fallback `{status:healthy|degraded,timestamp,uptime_seconds,subsystems:{serial_companion:{connected,port},mqtt_broker:{connected}}}`. El status superior HTTP permanece200 aunque degradado. Los snapshots son diccionarios del servicio, no esquema cerrado demostrado por este catálogo.

### Nodos y analítica

Fuentes: router `_dispatch_nodes`:480; NodesController list_nodes:17, get_lqi:31, analytics:44, reset:99, heatmap:130, airtime:165.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/nodes` | U |limit100 [1..500],offset0 [0..100000], int acotado |200 OK data[],count,total_count,limit,offset;400 parámetros |pasivo; nodes.js:206 |
| GET | `/api/lqi` | U |ninguna |200 OK data[],count; fallback[] |pasivo |
| GET | `/api/analytics` | U |range=str(value), default24h; controlador no enumera rechazo |200 OK data summary/enriquecimientos |pasivo; analytics.js:240 / nodes.js:1137 |
| POST | `/api/analytics/reset` | P |ninguna |200 OK message,data resultado reset |local; WS metrics_reset; analytics.js:161 |
| DELETE | `/api/analytics/reset` | P |igual POST |200 OK message,data |local; variante explícita |
| GET | `/api/rf/heatmap` | U |ninguna |200 OK data{points[],count}; descarta lat/lon inválida y0,0 |pasivo; map.js:329 |
| GET | `/api/airtime/stats` | U |ninguna |200 OK data tracker; fallback hourly_used_ms0,hourly_budget_ms36000,hourly_duty_cycle_pct0 |pasivo; analytics.js:243 / map.js:424 |
| GET | `/api/rf/noise` | U |ninguna |200 OK data.matrix[] {pubkey,name,role,noise_floor_dbm,snr,rssi,channel(default0),freq(default915)} |pasivo; router inline:530 |

Analítica conserva diccionario del registro, queue_depth/deduplication_count, serial_connected/mqtt_connected, routing_efficiency, packet_type_breakdown, error_breakdown, time_series y radio_hardware. Contadores summary se ajustan con máximo de bridge/registro; radio_hardware puede agregar uptime_secs. No inicia ping/traza para generar métricas. Heatmap point: public_key,name,role,lat,lon,rssi,snr,noise_floor,is_local.

### Contactos

Fuentes: router `_dispatch_contacts`:553; ContactsController route:62, validation:31, sync:110, share:152, export:166, import:248, create/update:472, delete:550. Lock del controlador incluso para lecturas; discovered/accept del router no usan ese lock.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/contacts` | U |ninguna, sin paginación |200 OK data client_contacts[],count |pasivo; lista excluye infraestructura/local |
| POST | `/api/contacts` | P |esquema C abajo |201 nuevo /200 existente OK data contact.to_dict;400/422 validación;CF;500 persistence_failed |serial+disco; WS contacts_updated; chat.js:1352,nodes.js:612/1039,settings.js:451 |
| DELETE | `/api/contacts` | P |public_key > key > vacío, str.strip.lower |204;400 cannot_delete_local_station;404 contact_not_found;CF;500 persistence_failed |serial+disco; no borrar masivo |
| DELETE | `/api/contacts/{public_key}` | P |regex exactamente64 hex, minúscula; **body/query public_key/key puede reemplazar clave path** |mismos status DELETE root; key path inválida⇒404 route_not_found |serial+disco; nodes.js:655 |
| POST | `/api/contacts/sync` | P |ninguna |200 OK imported,data client_contacts[],count;503 transceiver_offline/sync_failed |serial lectura tabla +registro/disco |
| POST | `/api/contacts/share` | P |public_key > key, str.strip; faltante400 missing_public_key |200 OK result;CF |RF share_contact; el controlador no llama validation de creación |
| GET | `/api/contacts/export` | U |public_key OR pubkey OR key; name OR alias si no registro |200 OK uri,qr_uri,message_tag,data,result;400 missing_public_key;422/400 validation C |serial export local opcional; no raw Content-Disposition |
| POST | `/api/contacts/export` | P |igual GET |mismos status/envelope |serial; diferencia auth por método |
| POST | `/api/contacts/import` | P |esquema I abajo |201 OK imported,data[]; rama binaria200 OK result;400/422/CF/500 |serial+disco; WS contacts_updated; settings.js:1456 |
| GET | `/api/contacts/discovered` | U |ninguna |200 OK data{discovered[],count} |pasivo; router inline:559 |
| POST | `/api/contacts/accept` | P |public_key > target_node, str.strip |400 missing_public_key;200 {status:ok\|error,accepted:bool}, incluso false |registro accept_discovered_contact; router inline:563 |

**C:** public_key > key, obligatorio; clave válida y longitud64 hex ⇒422 invalid_public_key; name/alias/role se convierten str y strip, defaults vacío/vacío/CLIENT. Validación del nombre efectivo name OR alias OR Node_<prefijo>: ≤31bytes UTF-8 sin control ⇒422 invalid_contact_name. LOCAL por identidad ⇒400 cannot_add_local_station; role REPEATER/ROUTER/LOCAL o nodo existente de esos roles ⇒400 repeater_contact_forbidden. Roles aceptados CLIENT/CHAT/NONE/ROOM/SENSOR; otros422 invalid_contact_role. is_favorite opcional vía to_bool. latitude > lat > adv_lat y longitude > lon > adv_lon si valor no nulo, float con error ignorado ⇒None; sin límites finitos/rangos en esta capa. Primero add_contact confirmado, después registro/save; fallos de persistencia no revierten comando físico. ROOM/SENSOR admitidos aquí frente a list_client_contacts CLIENT es discrepancia previa por resolver, no cambio de FastAPI.

**I:** prioridad campos directos public_key/pubkey/key, luego contacts list filtrando no-dicts, luego `data OR payload OR uri` string.strip. Parser acepta tag `<64hex:type:name>` simple/múltiple; URI meshcore:// con query; JSON textual dict/list; hex que contenga JSON/URI UTF-8; o binario remitido a SDK import_contact. URI canal ⇒400 channel_payload_in_contacts; hex inválido⇒400 invalid_hex_data; sin registros⇒400 no_valid_contacts. Batch valida nombre/rol/clave antes de primer add_contact; omite entradas sin key, clave local y role REPEATER/ROUTER. Batch vacío⇒400 import_rejected. Campos de nombre/alias, rol, favorite y coordenadas como C. La rama binaria delega validación al SDK y no acredita inspección del rol en esta capa. En fallo intermedio puede haber registros ya importados/persistidos: error CF no necesariamente incluye conteo importado. Export genera URI/tag, contact_type numérico, raw_hex desde serial cuando disponible; ausencia serial permite export local con raw_hex null.

### Canales

Fuente ChannelsController route:100, masked list:173, export:217, max_channels:265, create:278, delete:334. Shared lock incluye GET/sync/export.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/channels` | U |ninguna; sync_serial=False |200 OK data[] enmascarados,count |pasivo; settings.js:1233 |
| POST | `/api/channels` | P |index1 entero estricto, name defaultCanal N, psk vacío, overwrite to_bool false |201 nuevo/200 overwrite OK data enmascarada;400 index fuera;409 channel_already_exists;422 índice/nombre;CF;500 global save |serial+disco; WS channels_updated; settings.js:373/1395 |
| DELETE | `/api/channels` | P |index0 entero estricto |204;422 invalid_channel_index;400 cannot_delete_public_channel;404 channel_not_found;CF;500 global |serial delete_channel o set_channel vacío;disco; settings.js:1336/1436 |
| POST | `/api/channels/sync` | P |ninguna |200 OK data[] enmascarados,count;503 sync_failed |serial lectura;slots eliminados no resucitan;disco |
| GET | `/api/channels/export` | P |index=int(default0), aquí bool/float admitidos por int |200 OK uri,qr_uri,data{type,index,name,secret,is_encrypted,is_public};400 invalid_channel_index/cannot_export_public_channel;404 channel_not_found |local;secret real en URI/data; settings.js:1300 |
| POST | `/api/channels/export` | P |igual GET |mismos status |local |

Índice POST/DELETE rechaza bool/float; string entero con espacios admitido; índice POST 0..max_channels-1 (capacidad self_info positiva, fallback8). Name debe ser string≤31bytes sin controles; se strip después. PSK `••••••••` conserva anterior en overwrite. GET/POST/sync masks `psk` a ocho bullets si privado con clave, añade has_psk,is_encrypted,is_public; canal0 psk vacío. Export sí divulga secret a cliente autenticado y utiliza secret canónico público para abierto/sin clave; ejemplos aquí no contienen secretos reales.

### TX e historial reciente

Fuentes router `_dispatch_tx`:578; TxController send_tx:20 / get_recent_messages:113.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| POST | `/api/tx` | P |text=str().strip obligatorio; destino to si existe, si no target; channel_index > channel_idx default0 vía int; request_id defaultweb_<ms> |200 OK data resultado;400/422 validación;408 tx_timeout;429/503 tx_submission_failed;CF |RF cola NORMAL submit y espera hasta30s; chat.js:1486 |
| GET | `/api/messages/recent` | U |ninguna; no paginación |200 OK data[] todos recent_messages,count |pasivo; no consulta RF |

Text vacío400 missing_text_field; falta ambas claves destino400 missing_target_destination; destino null422 null_target_destination, str.strip vacío422 empty_target_destination; channel int fallido400 invalid_channel_index. Targets broadcast/public/0xffff/* o que empiecen por channel (case insensitive) se consideran broadcast; otro destino local400 tx_to_local_forbidden, nodo reconocido REPEATER/ROUTER400 tx_to_repeater_forbidden. Controlador no valida aquí cada límite RF/byte ni formato de key; SDK/cola mantienen esa responsabilidad. Submit debe devolver future/coroutine; timeout puede ocurrir después de admisión, **no autoriza retry HTTP**. QueueFull o texto excepción con Full/RateLimit⇒429, otra excepción⇒503. Sin Retry-After. request_id se convierte str al submit, no es respuesta202 pendiente. Resultado exitoso es comando/resultado actual; no prometer ACK remoto que el resultado no contiene. La rama posterior `status == "error"` que declara `tx_transmission_failed` no es alcanzable para ese resultado: CF ya reconoce ERROR en mayúsculas y devuelve `command_failed`. El status408 existe, pero HTTP_STATUS_TEXTS carece de408: `_build_http_response` serializa razón `Unknown`; preservar esa particularidad o registrar su corrección explícita.

### Administración y repetidores

Fuentes router `_dispatch_repeater`:586; RepeaterController execute_admin:27, execute_repeater:40, login:62, logout:87, config:102, action:124, ping:146, trace:164, neighbours:182, owner:201, regions:213, clock:225, acl:237. Todas POST/P; CF remoto/global500 heredados.

| Método | Ruta | Entrada/default/coerción | Respuesta/status además CF | Efecto; consumidor |
|---|---|---|---|---|
| POST | `/api/admin` |diccionario completo a handle_admin; action sólo leído para log |200 OK result,response,message (dos textos de result.result OR result.message); validación delegada |serial/RF/MQTT según acción; app.js:568/580,settings.js:781 |
| POST | `/api/admin/repeater` |target_node > repeater str.strip; action > command defaultstats-radio str; params={},password="",request_id defaultweb_rep_<s> |400 missing_target_node;200 OK data |RF remoto |
| POST | `/api/repeater/remote/login` |target_node > repeater; password str excepto null⇒vacío; no trim password |400 missing_target_node/empty_password;401 auth_failed con data;200 OK data autenticado |RF login; repeater.js:1020 |
| POST | `/api/repeater/remote/logout` |target_node > repeater |400 missing_target_node;200 OK data |RF logout; repeater.js:192 |
| POST | `/api/repeater/remote/config` |target_node > repeater; password null⇒vacío/string; params default{} |400 missing_target_node;200 OK data, action=remote_repeater_set_config |RF configuración; repeater.js:811 |
| POST | `/api/repeater/remote/action` |target_node > repeater; action str.strip;password como config;params{} |400 missing_fields;200 OK data |RF acción; repeater.js:1060/1622 |
| POST | `/api/repeater/remote/neighbours` |target_node > repeater;count255,offset0,password"" sin coerción de esos3 en controller |400 missing_target_node;200 OK data;action=req_neighbours |RF consulta; repeater.js:1699 |
| POST | `/api/repeater/remote/owner` |target_node > repeater;password"" |400 missing_target_node;200 OK data;action=req_owner |RF consulta; repeater.js:1778 |
| POST | `/api/repeater/remote/regions` |target_node > repeater;password"" |400 missing_target_node;200 OK data;action=req_regions |RF consulta; repeater.js:1810 |
| POST | `/api/repeater/remote/clock` |target_node > repeater;password"" |400 missing_target_node;200 OK data;action=req_clock |RF consulta |
| POST | `/api/repeater/remote/acl` |target_node > repeater;password"" |400 missing_target_node;200 OK data;action=req_acl |RF consulta; repeater.js:1837 |
| POST | `/api/node/ping_zero` |target_node > repeater > target, str.strip |400 missing_target_node;200 OK data |RF ping; nodes.js:1337 |
| POST | `/api/repeater/ping_zero` |igual node/ping_zero |igual |RF ping; repeater.js:1506 |
| POST | `/api/traceroute` |target_node > target > repeater > to, str.strip |400 missing_target_node;200 OK data |RF trace |
| POST | `/api/repeater/traceroute` |igual traceroute |igual |RF trace; map.js:498 |

`>` aquí representa `dict.get(primary, fallback)`: null/vacío presente en primary **no** activa fallback. Ausencia target tras str/strip se valida; null puede convertirse en `"None"`, quedando validación al dominio. Solo admin/repeater remite request_id explícito/default; las rutas simplificadas construyen nuevo cmd y no copian campos desconocidos/request_id. Params no tiene validación de dict en esta capa. Respuestas `data/result` tienen shape de acción/ejecutor, no DTO cerrado: fuente [AdminCommandHandler.handle/_handle](../../src/admin_handler.py), líneas 320–450, y [ejecutores](../../src/admin/). Entradas admin action/command/cmd: si action cmd/exec/terminal/cli/run y command presente se usa command; sin action usa command/cmd; request_id > id; target_node > repeater. Destino remoto se separa del local por identidad. Local get_config/list_nodes puede publicar resultado MQTT; set_config/set_local_config delega executor. La lista CLI y capacidades firmware no se convierten en nuevas rutas REST. Refactorizar esa gramática o nuevas políticas es otra tarea; catálogo conserva passthrough y códigos CF/422/503/400 del handler.

### Configuración del transceptor y host

Fuente router `_dispatch_config`:636; ConfigController métodos/líneas en tabla. `refresh`: string trim/lower true o1, bool sin cambio, cualquier otro tipo false. GET config/radio/refresh usa consulta local Companion al refresh; no inicia automáticamente consultas RF a nodos remotos. Valores response/data redactados donde explícitamente se indica.

| Método | Ruta | Auth | Entrada | Respuesta/status; fuente | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/config` | U |refresh false |200 OK data config enriquecida/redactada;get_device_config:22 |pasivo o serial refresh; settings.js:1480 |
| POST | `/api/config` | P |diccionario parámetros LC abajo |200 OK data redactada;422 invalid_parameter/CF;set_local_config:113 |serial+host/disco/RF según parámetro |
| GET | `/api/config/radio` | P |refresh false |igual GET config |pasivo/serial |
| POST | `/api/config/radio` | P |igual POST config, no subset impuesto |igual POST config |serial/modifica radio; settings.js:1992 kind=radio |
| GET | `/api/config/identity` | U |ignora refresh, get_device_config() |200 OK data config completa redactada |pasivo |
| POST | `/api/config/identity` | P |igual POST config, no subset impuesto |igual POST config |serial; settings.js:1992 kind=identity |
| GET | `/api/config/custom_vars` | U |ninguna |200 OK custom_vars,data iguales;admin ausente{};get_custom_vars:290 |serial si admin disponible; settings.js:2130 |
| POST | `/api/config/custom_vars` | P |key/value(val fallback) OR vars dict no vacío;KV str/null⇒"";separadores : , NUL CR LF prohibidos |200 OK custom_vars,data fresh;400 invalid_schema;422 empty_key/invalid_vars_object/empty_key_in_vars/invalid_custom_var;503 admin_unavailable;CF;set_custom_vars:299 |serial;batch puede ser parcial; settings.js:2183 |
| DELETE | `/api/config/custom_vars` | P |key str,trim |200 OK custom_vars,data;400 missing_key;503 admin_unavailable;CF;delete_custom_var:358 |serial; settings.js:2217 |
| GET | `/api/config/path_hash_mode` | U |ninguna |200 OK path_hash_mode,data{path_hash_mode};503 admin_unavailable/read_unconfirmed;get:374 |serial |
| POST | `/api/config/path_hash_mode` | P |mode > path_hash_mode requerido;int o string trim0/1/2;bool/float prohibidos |200 OK path_hash_mode,data resultado;422 invalid_mode;503 admin_unavailable;CF;set:385 |serial |
| GET | `/api/config/autoadd` | U |ninguna |200 OK autoadd_config,data iguales;fallback{};get:410 |serial; settings.js:2315 |
| POST | `/api/config/autoadd` | P |flags > config > autoadd default0;max_hops opcional;int/string signed digits SIN trim;bool/float prohibidos;flags0..255,hops0..64 |200 OK data;422 invalid_flags/invalid_max_hops/invalid_autoadd o unsupported_parameter con código delegado;503 admin_unavailable;CF;set:416 |serial; settings.js:2356 |
| GET | `/api/config/flood_scope` | U |ninguna |200 OK flood_scope,data iguales;fallback{};get:460 |serial; settings.js:2237 |
| POST | `/api/config/flood_scope` | P |scope > scope_name;null/string;global */0/global/none permitidos;otra string prefijo#≤30bytes y sin control |200 OK data;422 invalid_scope;503 admin_unavailable;CF;set:466 |serial; settings.js:2258/2289 |
| POST | `/api/node/advert` | P |flood to_bool false |200 OK data;400 admin_handler_unavailable;CF;broadcast_advert:183 |RF advert hop0/flood; settings.js:996/1021 |
| POST | `/api/node/reboot` | P |ninguna |200 OK data;CF;reboot_local:280 |serial reinicio; settings.js:1081 usa alias config/reboot |
| POST | `/api/config/sync-clock` | P |epoch > timestamp;ausente/null⇒hora host;int positivo ostring signed trim;bool/float prohibidos |200 OK data;422 invalid_epoch;503 admin_handler_unavailable;CF;sync_clock:197 |serial RTC;WS clock_synced; settings.js:966 |
| POST | `/api/config/clear-stats` | P |ninguna |200 OK data;503 admin_handler_unavailable;CF;clear_stats:218 |serial+contadores host;WS metrics_reset; settings.js:1115 |
| GET | `/api/config/refresh` | U |ninguna;refresh forzado |200 OK data;refresh_hardware_config:248 |serial;WS self_info |
| POST | `/api/config/refresh` | P |igual GET |igual GET |serial |
| POST | `/api/config/reconnect` | P |ninguna |200 OK message si reconnect serial,200 OK data fallbackadmin;503 serial_reconnect_failed;500 {status:error,message} para excepción reconnect;CF;reconnect_serial:259 |serial reapertura; settings.js:1046 |

**LC:** controlador valida cinco campos numéricos si presentes: duty_cycle_limit_pct,warn_threshold_pct,airtime_cutoff_threshold_pct,airtime_cutoff_resume_pct∈[0,100]; repeater_pre_send_delay_s≥0. Bool rechazado; float(value) finito exigido ⇒422 invalid_parameter. Resto se reenvía entero a handle_admin `{action:set_local_config,params}`. Tras CF exitoso se actualiza airtime_tracker, se guarda history sync=True cuando cambia y se actualizan flags/delay host mediante to_bool/float. Response data redactada; WS self_info sólo si resultado contiene config.

Validación profunda de parámetros pertenece a [LocalConfigExecutor](../../src/admin/local_config_executor.py), `_prevalidate_local_params`:531 y `set_local_config`:721. Campos admitidos: name; latitude/lat, longitude/lon; pin/devicepin; tx_power/power; frequency/radio_freq; bandwidth/bw; spreading_factor/sf; coding_rate/cr; repeat/repeat_enabled; rx_delay/rx_dly; airtime_factor/af; path_hash_mode; custom_vars; seis campos empaquetados OTHER_PARAM_FIELDS (telemetry_mode_base/loc/env, multi_acks, adv_loc_policy, manual_add_contacts); siete campos host/airtime documentados arriba. Campos desconocidos fallan; telemetry_interval/beacon_interval/advert_interval/hop_limit/hops/owner_info/owner/altitude/alt/altitude_m/fixed_position/pos_fixed se rechazan como no soportados. Alias contradictorios fallan antes de escribir. Cambiar uno de los seis campos empaquetados exige baseline de los restantes.

Prevalidación concreta: name string ≤31 bytes sin control; lat/lon finitos en -90..90 y -180..180, completa faltante desde baseline o falla; path_hash_mode entero0/1/2; PIN0 o100000..999999; TX power -9..30dBm; radio completo provisto o baseline (frequency entre constantes LORA_MIN_FREQ_MHZ y LORA_MAX_FREQ_MHZ, bandwidth7..500kHz, SF5..12, CR5..8 o4/5..4/8); telemetry modes0/1/2; tuning finito rx_delay0..20 y airtime_factor0..9, exige baseline del par no cambiado. Integer keys rechazan bool y float no integral/no finito; boolean fields admiten bool, int0/1 o strings true/false/1/0/yes/no/on/off. Custom_vars valida separadores reservados. Esto describe las restricciones existentes, no límites nuevos. El handler traduce ValueError/TypeError a422 y las fallas de comando conservan CF/applied/config; no reducir DTO a los cinco campos validados en el controlador ni suponer que otros ajustes no listados están soportados.

GET config agrega uptime,uptime_str,device_uptime,bridge_uptime,airtime_ms,duty_cycle_pct,hourly_limit_pct,warn_threshold_pct,is_warning,is_critical,status_level,channel_stats,airtime completo,airtime_cutoff_* y repeater_pre_send_delay_*,tx_count,rx_count,duplicate_packets,packet_errors,noise_floor_dbm,clock,serial_connected,radio_connected,serial_port. Proyecta device_epoch_time/device_time_drift con timestamp de muestra; `clock` es texto hora local de host. Redact_sensitive_dict se aplica; no filtrar todo lo demás con un response_model reducido inadvertidamente.

### Servicios de red y presets

Fuentes router `_dispatch_services`:746; ServicesController get:32,set:47,save_preset:147,delete_preset:256,test_external_mqtt:286; [services_config.py](../../src/services_config.py) define dataclasses/defaults/redacción.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/services/config` | U |ninguna |200 OK data configuración redactada +external_mqtt_connected |pasivo/disco fallbackload; settings.js:2522 |
| POST | `/api/services/config` | P |objeto; external_mqtt/local_mqtt/tcp_server parciales |200 OK message,reloaded,data redactada;400 invalid_json;422 invalid_host/invalid_port/invalid_transport/invalid_auth_type/invalid_location_privacy;500 reload_failed |red+disco,hotreload; settings.js:2768 |
| GET | `/api/services/presets` | U |ninguna |200 OK presets =get_services_config.data.all_presets |pasivo |
| POST | `/api/services/presets` | P |presets S abajo |200 OK message,preset redactado;422 missing_name/missing_host/invalid_port;400 system_preset_protected;500 bridge_unavailable/global |local+disco; settings.js:2860 |
| DELETE | `/api/services/presets/{id:path}` | P |todo suffix tras prefijo, .strip, admite slash interno |200 OK message;400 system_preset_protected;404 preset_not_found;500 bridge_unavailable/global |local+disco; settings.js:2915 |
| POST | `/api/services/mqtt-external/test` | P |host requerido;port1883 int1..65535;credenciales+tls/transport/auth;timeoutfloat(value OR5) clamp1..10 |200 {status:ok\|error,data:test_result} según data.ok;400 invalid_json;422 missing_host/invalid_port;500 global conversión/ejecución |red conexión efímera MQTT; settings.js:2808 |

Config: validación de secciones sólo si dict y `enabled` truthy. External exige host,port opcional1..65535,transport tcp/websockets,auth_type anonymous/user_pass/token,location_privacy exact/fuzzed/hidden si valor truthy; local port opcional1..65535;TCP opcional1024..65535. Int acepta bool/float; una sección no-dict o disabled no se rechaza con esa validación. Bridge reload_services/body aplica merge/persistencia; ausencia reload_services permite200 sin recarga, data delcfg actual. No extrapolar esquema estricto de Pydantic.

**S:** name/host str(value OR "").strip obligatorios;port1883 int1..65535;id stringstrip o IDcustom_slug20_uuid6, no sobrescribe SYSTEM_PRESETS. String default: description/username/password/token vacío; transport tcp;auth_type anonymous;location_privacy fuzzed;topic_mode standard;topic_prefix meshcore/remote;region_iata XXX mayúsculas;payload_format json_canonical. Bool nativo:tls_enabled false,tls_verify true,downlink_enabled false,filter_observer_mode false,filter_public true,filter_channels true,filter_direct false,filter_telemetry true,filter_nodes true,filter_raw false. keepalive=int(value OR60),qos=int(value OR0), sin rango explícito encontroller; valores malos⇒500global. No validación enums comparable a config para esos campos de preset. Password/token en máscara mantienen valor anterior sólo si preset id existente. Response has_password/has_token y máscaras. Test MQTT preserva máscara desde config actual y crea ExternalMqttConfig enabled true; bool nativo para TLS. No publica RF directamente; habilitar downlink/reconfigurar servicios puede tener efecto indirecto y requiere conservar guards existentes.

### Paquetes

Fuentes router `_dispatch_packets`:449; PacketsController get:18/export:55/clear:105.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/packets` | P |limit100[1..500],offset0[0..100000];direction/type str default"";order str asc odesc |200 OK data[],count,total_count,limit,offset,order,session_id,capture_enabled;400 coerción/bounds/invalid_order;503 packet_buffer_unavailable |pasivo; sniffer.js:319 |
| DELETE | `/api/packets` | P |ninguna |204 aun sin buffer |local; sniffer.js:393 |
| GET | `/api/packets/export` | P |format str lower defaultjson, controllerstrip;pcap/csv especiales, cualquier otro⇒json |200 OK format,filename,mime_type,size_bytes +base64_data PCAP otext_data JSON/CSV;503 packet_buffer_unavailable |local; sniffer.js:427 |

JSON/CSV/PCAP son representaciones **dentro de JSON HTTP**. mime_type describe archivo contenido, no Content-Type de la respuesta ni descarga binaria. Filename UTC meshcore_packets_YYYYMMDD_HHMMSS.<ext>. El campo type filtra buffer, no diccionario de tipos validado aquí. Export no aplica paginación del GET.

### Mapas e historiales adicionales

Fuentes router `_dispatch_misc`:779; LogsController route_logs:18/rawdownload:122; servidor tiles:503/553 y MapTileService get_tile:94.

| Método | Ruta | Auth | Entrada | Respuesta/status | Efecto; consumidor |
|---|---|---|---|---|---|
| GET | `/api/map/status` | U |ninguna |200 OK data status map |local; thread get_status |
| POST | `/api/map/reload` | P |ninguna |200 OK message,data status map;500 map_reload_failed |local reindex/disco/thread; settings.js:891 |
| GET | `/api/messages` | U |sólo query limit100/offset0,primer valor,isDigit;sin rango/techo;inválido⇒default |200 OK data[],count,total_count,limit,offset |pasivo deque200 |
| GET | `/api/telemetry` | U |igual messages |200 OK data[],count,total_count,limit,offset |pasivo deque200 |
| GET | `/api/logs/download` | P |ninguna (limit/offset parseados no usados) |200 OK raw_logs,log_file,line_count |local tail2000 líneas o deque fallback; sniffer.js:920 |
| GET | `/api/logs/raw` | P |igual download |igual download |local |

Para logs, query repetida elige **primer** valor, body se ignora; negativos no isdigit y vuelven a default, cero permitido; offset no limita logs de sistema. `limit=0` en mensajes/telemetría produce página vacía; en sistema significa no recorte en fallback y depende del handler para diagnóstico. Content de downloads JSON, log_file puede ser path del host o null.

| Método/patrón | Auth | Entrada y matching real | Respuesta/status/headers | Efecto |
|---|---|---|---|---|
| GET `/api/map/tiles/{z}/{x}/{y}[.<suffix>][/{extra...}]` | T |prefijo exacto; al menos3 segmentos; int z/x, int de y antes del primer punto; ignora suffix y segmentos extra; query ignorada;z0..22,x/y0..2^z-1 |200 bytes cuando dato existe, MIME detectado;Cache-Control public,max-age86400;404 vacío image/png si inválida/inexistente |local async.to_thread tile_service |
| cualquier método excepto GET mismo prefijo | T |no valida coordenadas antes de rechazar |405 {error:"Method Not Allowed",detail:"Only GET is supported for map tiles"};application/json;HEAD omisión no aplicada a esta rama |ninguno |

Extensión solicitada no selecciona formato. Servicio prueba loose png,jpg,jpeg,webp,pbf y después MBTiles; detecta magic PNG/JPEG/WebP/gzip(PBF); XYZ/TMS según metadata. gzip vector se responde MIME application/x-protobuf sin Content-Encoding agregado. GET `/api/map/tiles/` mal formado404; HEAD tiles405, aunque helper tile tenga parámetro head_only. Map status data:has_local_maps,maps_directory,tiles_directory,mbtiles_count,mbtiles_files[],has_loose_tiles; file entry:filename,size_mb,name,format,min_zoom,max_zoom,description. Status/reload usa router.map_tile_service; tiles usa servidor.tile_service, **actualmente alias del mismo objeto** asignado en MeshCoreWebServer.__init__. La migración debe conservar esa instancia compartida y su propietario de cierre.

## Aliases declarados y auth por path original

Fuente ROUTE_ALIASES api_router.py:35–80. Alias se aplica a todos métodos; la tabla enumera sólo métodos funcionales del destino. Método ajeno conserva405/404 de familia, auth previa según original. `P/U` GET indica diferencias frente al destino; toda mutación es P con clave configurada.

| Alias | Destino | Métodos funcionales | Particularidad auth lectura |
|---|---|---|---|
| `/api/node/ping` | `/api/node/ping_zero` | POST |P |
| `/api/nodes/ping` | `/api/node/ping_zero` | POST |P |
| `/api/nodes/ping_zero` | `/api/node/ping_zero` | POST |P |
| `/api/ping_zero` | `/api/node/ping_zero` | POST |P |
| `/api/trace` | `/api/traceroute` | POST |P |
| `/api/node/traceroute` | `/api/repeater/traceroute` | POST |P |
| `/api/node/trace` | `/api/repeater/traceroute` | POST |P |
| `/api/nodes/traceroute` | `/api/repeater/traceroute` | POST |P |
| `/api/nodes/trace` | `/api/repeater/traceroute` | POST |P |
| `/api/link_quality` | `/api/lqi` | GET |U |
| `/api/metrics/analytics` | `/api/analytics` | GET |U |
| `/api/metrics/reset` | `/api/analytics/reset` | POST,DELETE |P |
| `/api/repeater/neighbours` | `/api/repeater/remote/neighbours` | POST |P |
| `/api/repeater/neighbors` | `/api/repeater/remote/neighbours` | POST |P |
| `/api/repeater/remote/neighbors` | `/api/repeater/remote/neighbours` | POST |P |
| `/api/repeater/owner` | `/api/repeater/remote/owner` | POST |P |
| `/api/repeater/regions` | `/api/repeater/remote/regions` | POST |P |
| `/api/repeater/clock` | `/api/repeater/remote/clock` | POST |P |
| `/api/repeater/acl` | `/api/repeater/remote/acl` | POST |P |
| `/api/repeater/logout` | `/api/repeater/remote/logout` | POST |P |
| `/api/admin/command` | `/api/admin` | POST |P |
| `/api/node/settings` | `/api/config` | GET,POST |GET U |
| `/api/node/config` | `/api/config` | GET,POST |GET U |
| `/api/node/custom_vars` | `/api/config/custom_vars` | GET,POST,DELETE |GET U |
| `/api/node/path_hash_mode` | `/api/config/path_hash_mode` | GET,POST |GET U |
| `/api/node/autoadd` | `/api/config/autoadd` | GET,POST |GET U |
| `/api/node/flood_scope` | `/api/config/flood_scope` | GET,POST |GET U |
| `/api/node/config/radio` | `/api/config/radio` | GET,POST |GET P |
| `/api/node/config/identity` | `/api/config/identity` | GET,POST |GET U |
| `/api/config/advert` | `/api/node/advert` | POST |P |
| `/api/config/reboot` | `/api/node/reboot` | POST |P |
| `/api/node/sync-clock` | `/api/config/sync-clock` | POST |P |
| `/api/config/sync_clock` | `/api/config/sync-clock` | POST |P |
| `/api/node/clear-stats` | `/api/config/clear-stats` | POST |P |
| `/api/config/clear_stats` | `/api/config/clear-stats` | POST |P |
| `/api/node/refresh` | `/api/config/refresh` | GET,POST |GET U |
| `/api/node/reconnect` | `/api/config/reconnect` | POST |P |
| `/api/config/reconnect-serial` | `/api/config/reconnect` | POST |P |
| `/api/map/refresh` | `/api/map/reload` | POST |P |

La expansión suma 50 combinaciones: 39 métodos iniciales +1 adicional de metrics/reset +2 de node/settings y node/config +2 de custom_vars +5 de hash/autoadd/flood/radio/identity +1 de node/refresh. Se comprobó contando métodos separados por comas en las 39 filas, sin importar la aplicación.

## Rutas rechazadas, prefijos y fallbacks

- Recursos conocidos sistema, nodos, canales, contactos, config, services, packets y TX/repeater normalmente devuelven405 PD `method_not_allowed` para método ajeno; **no Allow**. GET map/status con otro método ⇒404 PD `not_found`; messages, telemetry, logs/download/raw con otro método también404 `not_found`. Map/reload con otro método405. `GET /api/logs` ⇒404 PD `log_not_found`; método ajeno ⇒404 `not_found`.
- Prefijos `/api/analytics/`, `/api/system/logs...`, `/api/admin...`, `/api/repeater...`, `/api/traceroute...`, `/api/node...`, `/api/config...`, `/api/services...`, `/api/packets...`, `/api/map...` sólo seleccionan dispatcher. Suffix desconocido ⇒404 de familia (`route_not_found`, `services_route_not_found` o `not_found`), no wildcard de endpoints implementados. `/api/nodes/unknown` entra config por prefijo `/api/node` después de comprobar rutas exactas y retorna404. No registrar esos prefijos como rutas exitosas nuevas.
- Contacts/{key} exige64hex y DELETE; otro método a clave válida405; clave inválida/suffix extra404. Presets/{id} es suffix libre con slash interno; métodos ajenos405. Barra final se elimina antes del router; variantes con barra final no son aliases adicionales contados.
- Tiles se intercepta sólo por HTTP antes del router: invocar router.handle_request para tile no prueba su contrato. SecurityTrafficInspector/traversal puede producir403 antes de cualquiera de esas operaciones; ver matriz web.
- Estáticos: `_serve_static_file`:1073, raíz y chat/map/nodes/contacts/settings/telemetry/logs/analytics sirven index; recurso inexistente sin extensión ⇒index; con extensión ⇒404 texto; pertenencia/root/traversal ⇒403. No hay restricción explícita de método en ese helper: GET/HEAD son comportamiento usado; otros pueden servir asset tras validaciones previas. OPTIONS ya se ha capturado. HTML: no-cache/no-store/must-revalidate; assets: max-age300; ETag SHA256 primeros16,304,Vary:Accept-Encoding,gzip textual>256bytes si menor. Estáticos no entran en las91 operaciones API ni justifican responder HTML200 a una API desconocida.

## Ejemplos sanitizados y discrepancias para la migración

```json
{"request":{"method":"GET","path":"/api/nodes?limit=100&offset=0"},"response":{"status":"ok","data":[],"count":0,"total_count":0,"limit":100,"offset":0}}
{"request":{"method":"POST","path":"/api/tx","body":{"text":"Mensaje de ejemplo","to":"broadcast","channel_index":0,"request_id":"demo-1"}},"response_shape":{"status":"ok","data":"<resultado actual de cola/SDK; no ejecutar este ejemplo>"}}
{"request":{"method":"GET","path":"/api/channels/export?index=1"},"response_shape":{"status":"ok","uri":"meshcore://channel/add?name=Demo&secret=<redactado>&index=1","qr_uri":"<URI redactada>","data":{"type":"channel","index":1,"name":"Demo","secret":"<redactado>","is_encrypted":true,"is_public":false}}}
{"request":{"method":"POST","path":"/api/services/presets","body":{"name":"Demo","host":"broker.example.invalid","password":"<redactado>"}},"response_shape":{"status":"ok","message":"<texto>","preset":{"password":"<máscara>","token":"<máscara>","has_password":true,"has_token":false}}}
{"error_shape":{"type":"urn:meshcore:error:missing_text_field","title":"Bad Request","status":400,"detail":"El campo 'text' no puede estar vacío","error":"missing_text_field","message":"El campo 'text' no puede estar vacío","timestamp":0.0}}
```

Estos shapes son ejemplos documentales, no capturas ni fixtures ejecutadas; `<resultado>`/`<máscara>` indica valor variable. No pegar ejemplos RF contra una estación operativa. Consumidores identificados por lectura respaldan presencia de rutas, **no** paridad de payload/método bajo runtime. [n8n_workflow_meshcore.json](../../n8n_workflow_meshcore.json) y [guía n8n](../N8N_WORKFLOW_GUIDE.md) usan MQTT para TX/admin; no se identificó literal `/api/` allí. Los contratos MQTT siguen propios y no deben migrarse automáticamente a REST.

Discrepancias concretas:

1. chat.js:622 consulta GET channels/export sin index; controller default0 ⇒400 cannot_export_public_channel. No corregido como parte de paridad.
2. `/api/logs` se reconoce en router, pero no se implementa en LogsController; cualquier éxito nuevo necesita decisión explícita.
3. Auth de GET config/radio difiere de config/identity/config/refresh; aliases raw son autoridad actual. Normalizar auth es cambio de seguridad, no paridad automática.
4. Creación/import admite ROOM/SENSOR mientras listado de contactos es CLIENT; share/binario/accept validan por otras vías. Revisar invariantes en dominio/adaptador sin atribuir garantías globales a un DTO.
5. Paginación de mensajes/telemetría usa query cruda y permite0/sin techo; nodos/packets usan body fusionado/int acotado. Esquema estricto uniforme rompería aceptaciones y defaults actuales.
6. Descargas/reportes son envelopes JSON; existen200 status:error y204 vacío; reconexión500 no PD; tiles404 vacío. No normalizar sin registrar cambio.
7. Rutas admin/config delegan esquemas/resultados variables a dominio/firmware; un response_model cerrado requiere congelar campos por acción con QA autorizado, no suprimir campos observados.

## Verificación y pendientes

Se leyó cada dispatcher y controlador, se inventariaron variantes/aliases por fuente y se contrastaron literales de consumidores. Conteo textual comprobado:90 filas de operaciones JSON,69 paths distintos,39 aliases y50 métodos expandidos, más un patrón GET de tiles. No se ejecutó helper regex, pytest, Ruff, mypy, Playwright, preflight ni endpoints. QA futura por lote deberá cubrir request/response/status/auth/errores y sus variantes en un entorno temporal; este catálogo sirve de lista de evidencia, no sustituye fixtures observables. Shapes de registro, analytics, servicios y admin son diccionarios vivos: para un OpenAPI exacto faltan muestras sanitizadas/fixtures aprobadas por acción y capacidades, pruebas de coerción y caminos fallidos con adaptador virtual. Cierre de fase0 es decisión del líder y propietario después de revisar catálogo/matriz, destinos/presupuestos y esas lagunas.
