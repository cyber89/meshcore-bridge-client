# FastAPI: línea base del contrato interno y propiedad de recursos

Fecha: 2026-10-08. Estado: **fase 0, inventario y diseño**, sin migración de producción.

Este inventario conserva la base previa a fase 1, identificada por
[SOURCE_SNAPSHOT.json](SOURCE_SNAPSHOT.json). Los imports y el seam preparados
después se registran en [PHASE_1_REPORT.md](PHASE_1_REPORT.md); las líneas y el
lenguaje de «actual» siguientes describen la base inspeccionada, no sustituyen
esa evolución ni afirman que ASGI sea el servidor predeterminado.

La autorización del usuario permite comenzar las fases sucesivas. La respuesta
«no importa» a la pregunta sobre equipos no elimina Python 3.10 ni acredita
compatibilidad o rendimiento en cualquier plataforma. Este documento separa el
comportamiento leído del diseño pendiente de implementación y verificación.

Referencias: [plan](../../PROYECTO.md), [dominio](../../CONTEXT.md),
[reglas](../../AGENTS.md), [índice](../README.md),
[ADR 0009](../adr/0009-official-companion-protocol-layers.md) y
[ADR 0010](../adr/0010-duty-cycle-configurable-budget.md).
Skills aplicadas: `async-concurrency-engineering`,
`software-architecture-patterns`, `domain-adr-keeper`.

## 1. Frontera actual: sustituir transporte no sustituye estado

`MeshCoreWebServer` (servidor nativo original en `src/web/http_server.py`), líneas 61–86, creaba un
[WebAPIRouter](../../src/web/api_router.py), líneas 119–152. El router crea
estado mutable, servicio cartográfico, contexto y diez controladores; el servidor
lo retiene y expone `tile_service` como alias. Borrar ambos archivos antes de
extraer sus responsabilidades perdería datos y rompería consumidores internos.

| Objeto actual | Propietario/alias | Contrato que hay que conservar |
|---|---|---|
| `recent_messages` | Router; `ApiContext.recent_messages` | `deque(maxlen=200)`; mensajes de chat filtrados por `is_common_chat_message` |
| `recent_telemetry` | Router; `ApiContext.recent_telemetry` | `deque(maxlen=200)`; formatos y extracción de telemetría existentes |
| `recent_system_logs` | Router; `ApiContext.system_logs` | `deque(maxlen=300)`; campos timestamp/iso_time/level/source/message |
| `map_tile_service` | Router; servidor `tile_service` | Instancia única con conexiones MBTiles readonly y `threading.RLock`; cierre coordinado |
| `channels_ctrl.channels` | ChannelsController; Router `channels` | Diccionario mutable compartido de índices enteros; secretos, borrados y persistencia pertenecen al controlador |
| `api_ctx` | Router; referencia desde diez controladores | Bridge existente, buffers por referencia, packet_buffer existente, callback logs y difusión, start_time |
| `_background_tasks` del router | Router `_notify_web_clients` | Tareas de difusión separadas de las tareas del bridge; actualmente sólo se descartan al finalizar |
| `_client_tasks`, `_metrics_task`, `active_websockets` | Servidor | Recursos de transporte; clientes y bucle de métricas se cierran en stop |
| `_static_cache` | Servidor | Cache raw/gzip/ETag/MIME; estado sólo de transporte, recreable |
| Registro/ACK/cola/airtime/cooldowns | Bridge y sus servicios | Permanecen fuera de FastAPI; nunca recrearlos por request o lifespan web |

Evidencia: router 121–152, 167–305;
[ApiContext](../../src/web/controllers/base.py), 18–29;
[ChannelsController](../../src/web/controllers/channels_controller.py), 28–103;
[MapTileService](../../src/web/map_tile_service.py), 21–98.

`broadcast_event` registra el evento **antes** de consultar si hay clientes
(servidor 206–209). La extracción debe registrar exactamente una vez, también con
cero WebSockets. `record_incoming_event` descarta eventos de transporte/métricas,
clasifica chat y telemetría y puede añadir logs. No es sólo `deque.append`.
`log_system_event` además entrega un `LogRecord` al handler de diagnósticos
(router 177–199). No duplicar esa entrega en middleware.

Las referencias de canales se pueden sustituir en `_load_channels`; el router
repara su alias en `_load_channels` y `_dispatch_channels` (154–157, 572–576).
Una propiedad delegada al controlador evita alias obsoleto; no copiar el dict a
`app.state` ni crear canales por petición. `_save_channels` del router es wrapper
síncrono que captura errores; las rutas del controlador usan `to_thread` y locks.
La carga inicial de canales y mapas actualmente hace I/O síncrono en constructores.
Extraer estado no debe convertir ese I/O en ejecución recurrente por dependencia.

## 2. Consumidores de producción fuera del dispatcher

La tabla cubre los consumidores Python encontrados bajo `src/` mediante búsqueda
de `web_server`, `broadcast_event`, `.router.`, `MeshCoreWebServer` y `WebAPIRouter`.
Las líneas son del checkout leído y deben revisarse tras cualquier extracción.

| Consumidor y evidencia | Interfaz observada | Adaptación necesaria |
|---|---|---|
| [bridge_core.py](../../src/bridge_core.py), 45, 214, 364–372 | Import eager, factory, campo opcional `web_server` | Import de implementación dentro de factory habilitada; tipo Protocol liviano |
| Core 219–223 | Callback logs programa `broadcast_event` | Retener scheduling/guardas del bridge; sink único de historial |
| Core 406, 424 | Inyección en RX/AdminContext | Conservar referencias o actualizar todos los contextos de forma conjunta |
| Core 631–632, 684–696 | `await start()`, `await stop()` | Adaptador lifecycle embebido; readiness y error de bind visibles |
| Core 739–745 | Bootstrap escribe `web_server.router.channels[idx]` | Alias de compatibilidad o servicio de canales compartido |
| Core 874, 1067–1069, 1094–1096 | Eventos TX/RF/duty-cycle por difusión programada | Conservar payload, conteo/ACK y propietario de tareas |
| [rx_router.py](../../src/rx_router.py), 206, 323, 378, 419–426, 513–524 | Contexto, RF/RX, actualización canales y difusión | Mismo sink, tabla de canales y scheduler; no duplicar suscripción RX |
| [system_handler.py](../../src/routers/system_handler.py), 63–72, 85–87 | Canales desde evento SDK; self-info/clock y demás difusión | Tabla actualizada aun sin clientes; mantener normalización existente |
| [repeater_handler.py](../../src/routers/repeater_handler.py), 122–123, 147–155, 191–199 | ACK, contacto y respuesta/telemetría | Emitir mismos eventos después del procesamiento actual |
| [repeater_executor.py](../../src/admin/repeater_executor.py), 589–602, 884–892 | Contactos y telemetría; compatibilidad coroutine/mock | No crear otra fachada admin ni lock por request |
| [traceroute_executor.py](../../src/admin/traceroute_executor.py), 137–139 | `trace_data` | Mantener nombres/payload y efecto actual |
| [cli_command_executor.py](../../src/admin/cli_command_executor.py), 860–870 | Busca `system_logs` en web; fallback `web.bridge.diagnostics` | Preservar fallback; `system_logs` no es atributo actual del servidor |
| [admin_handler.py](../../src/admin_handler.py), 45 | Campo `web_server: Any` | Sustituir tipo gradualmente; conservar opcionalidad |
| [src/__init__.py](../../src/__init__.py), 43–49; [web/__init__.py](../../src/web/__init__.py), 7–9 | Reexports públicos eager | Evitar importar ASGI al importar paquete headless; compatibilidad de imports legados |

Consumidores dentro de web: `MeshCoreWebServer._dispatch_client_request` termina
en `router.handle_request` (525); `_serve_map_tile` utiliza `tile_service`;
`broadcast_event` llama `record_incoming_event`; el bucle de métricas emite por el
mismo método (177). `_notify_web_clients` del router obtiene `bridge.web_server`
y registra tareas locales (167–175). Todos pertenecen al cambio de adaptador.

## 3. Métodos y operaciones del dispatcher que sobreviven a la extracción

La interfaz actual devuelve `tuple[int, dict[str, Any]]`, acepta diccionarios y
resuelve query/coerciones dentro del router/controladores. La fase de DTO debe
conservar ese comportamiento primero; no filtrar campos de respuesta ni imponer
strict/extras global. Esta lista inventaría el llamado interno, no sustituye el
catálogo REST de métodos/aliases y auth.

| Fachada actual | Operaciones llamadas | Evidencia en router |
|---|---|---|
| SystemController | `get_status`, `get_health`, `run_preflight`, `clear_logs` | 395–443 |
| NodesController | `list_nodes`, `get_lqi`, `reset_metrics`, `get_analytics`, `get_rf_heatmap`, `get_airtime_stats` | 480–549 |
| ContactsController | `handle_contacts_route`; conserva sync/share/export/import/create/update/delete y locks del controlador | 553–570 |
| ChannelsController | `handle_channels_route`; sync/export/create/update/delete y máscara de secretos | 572–576, wrapper 810–811 |
| TxController | `send_tx`, `get_recent_messages` | 578–584 |
| RepeaterController | `execute_admin_command`, `execute_repeater_command`, `login`, `logout`, `set_remote_config`, `execute_remote_action`, `get_neighbours`, `get_owner`, `get_regions`, `get_clock`, `get_acl`, `ping_zero`, `traceroute` | 586–613 |
| ConfigController | `get_device_config`, `set_local_config`, get/set/delete custom vars; get/set path hash mode, autoadd, flood scope; `broadcast_advert`, `reboot_local`, `sync_clock`, `clear_stats`, `refresh_hardware_config`, `reconnect_serial` | 636–742 |
| PacketsController | `export_packets`, `clear_packets`, `get_packets` | 449–477 |
| LogsController | `route_logs`, indirectamente lectura/descarga/report/historiales | 813–814; 401–404, 430–432, 798–807 |
| ServicesController | `get_services_config`, `set_services_config`, `save_preset`, `delete_preset`, `test_external_mqtt` | 746–775 |
| MapTileService | `get_status`, `reload_mbtiles` vía `to_thread` | 779–796 |
| DiagnosticManager directo | export bundle, get/set log level | 405–426 |
| NodeRegistry directo | `list_discovered`, `accept_discovered_contact`; RF noise usa `list_nodes` y compone matrix | 553–568, 531–545 |

El dispatcher también lee/modifica datos directamente para ciertas variantes;
extraer sólo los diez controladores omite responsabilidad. Revisar completos
`_dispatch_nodes` y `_dispatch_contacts`, además de diagnósticos y mapas. Los
wrappers `_route_channels`, `_route_logs`, `_load_channels`, `_save_channels` se
usan en compatibilidad/pruebas; mantener durante transición o sustituir cobertura
observable antes de retirarlos.

## 4. Ciclo de vida y concurrencia observados

### Arranque, rollback y señales

[Core.start](../../src/bridge_core.py), 565–587, serializa con `_lifecycle_lock`,
es idempotente mientras `_started`, captura el loop real y actualiza RX/MQTT.
Ante `BaseException` llama `_stop_subsystems` sin reentrar el lock y propaga error.
Orden actual: cargar cooldowns; admitir MQTT; preflight en hilo; rate limiter;
ServicesManager/MQTT/TCP; conectar serial; watchdog; web; bootstrap hardware;
health reporter y cleanup (589–642). Un fallo web ocurre después de abrir recursos
de radio/red: `start()` del adaptador nuevo debe fallar/terminar, nunca retornar
éxito tras sólo programar una tarea Uvicorn.

`stop` cancela tareas propias del bridge y cierra servicios, web, health, watchdog,
rate limiter y serial; persiste registro/cooldowns y retira handler (644–725).
No poner `bridge.start/stop` en lifespan de FastAPI además de ese propietario.

| Presupuesto existente | Ubicación | Implicación |
|---|---|---|
| MQTT ingress 1.5 s; cleanup 0.5 s; background 1.5 s | Core 653–680 | Esperas secuenciales; no son presupuesto global |
| Cada subsistema, incluido web, 1.5 s | Core 684–699 | Graceful shutdown de Uvicorn debe caber o acordarse conjuntamente |
| Registry 1 s; MQTT fallback 1.5 s; cooldowns 1.5 s | Core 702–723 | Cancelar await de `to_thread` no detiene necesariamente escritura/hilo |
| Señal global 5 s; finally stop 3 s y pending 2 s | Core 1126, 1150–1162 | Restricciones acumuladas actuales, no promesa de parada completa |
| Web metrics 0.5 s, listener 1 s, clients 1 s y cada writer 0.3 s | Servidor 95–149 | Puede superar límite externo; hay discrepancia previa |
| Difusión 2 s por cliente, secuencial | Servidor 218–230 | Coste O(n) y orden concurrente no protegido por un lock de emisión |

No se elige nuevo valor. Antes de implementar cambiar presupuestos requiere
acuerdo explícito conforme reglas del proyecto. La entrada principal conserva
su loop y señales; Uvicorn embebido no puede tomar las señales ni usar otro loop,
workers o reload. `run()` hace cancelación global al cerrar su loop (1155–1162);
esa lógica es del entrypoint completo y no debe copiarse al stop del adaptador web.

### Propietarios de tareas y locks

| Componente | Recursos actuales | Regla para ASGI |
|---|---|---|
| Core | `_background_tasks`, `_health_task`, `_cleanup_task`; lifecycle/tasks/TX metrics locks | Retener un propietario; `_add_background_task` consume excepciones (328–339) |
| RX | Worker/deque/capacidad; semaphore; registro en core | No crear listener RX por conexión WS; mantener admisión actual |
| MQTT client/dispatcher | Hilo Paho; callback/ingress a loop vía `call_soon_threadsafe` | Ninguna asyncio.Queue desde hilo; managers existentes conservan lifecycle |
| Serial SDK | `_command_lock`, `_initial_sync_task`, set background | Una sesión y una serialización de respuesta Companion; no `Depends` constructor serial |
| Watchdog | `_task`, reconexión coordinada en adaptador | No añadir reconexión ASGI ni polling RF |
| Contacts/ChannelsController | `_mutation_lock`; canales `_save_lock` en thread | Una instancia compartida preserva exclusión; otro controller por request rompe lock |
| Repeater executor | `_request_locks` por destino | Conservar correlación/transacciones; no reemplazar con HTTP concurrency |
| RepeaterManager | load/flush locks, writer shielded, monotonic + epoch maps | No reconstruir al recargar web/services ni perder últimos disparos |
| TxRateLimiter/AirtimeTracker | Worker, queue, futures y tareas de persistencia | No volver a admitir submit por request retry; conservar resolución/fallo de futures en stop |
| MapTileService | SQLite `check_same_thread=False` protegido por RLock | `to_thread` de get/status/reload y cierre coordinado; no usar dependencias SQLite request-scoped |
| Router/server | tasks de callback y clientes/métricas | Nuevo runtime retiene/consume/cancela/espera sólo tareas propias |

Evidencia: [mqtt_client.py](../../src/mqtt_client.py), 135–180, 277–295;
[mqtt_dispatcher.py](../../src/mqtt_dispatcher.py), 44–127;
[sdk_adapter.py](../../src/serial/sdk_adapter.py), 170–172, 236–267, 406–437,
574–590; [watchdog.py](../../src/serial/watchdog.py), 47–101;
[repeater_executor.py](../../src/admin/repeater_executor.py), 154–166;
[ContactsController](../../src/web/controllers/contacts_controller.py), 27–62;
[RepeaterManager](../../src/repeater_manager.py), 58–161.
El worker y finalización de futures TX están en
[rate_limiter.py](../../src/rate_limiter.py), 617–781; la persistencia de airtime
retiene snapshots/tarea propios (358–380). FastAPI no posee esas tareas.

### Configuración y timestamps

[ServicesManager](../../src/services_manager.py), 173–291, conserva la instancia
del manager pero reemplaza MQTT/TCP cuando cambia configuración, propaga referencias
al bridge/contexts y persiste configuración. No reinicia web ni RepeaterManager.
El contexto ASGI debe referenciar **bridge**, no capturar MQTT/TCP como snapshots
que se vuelven obsoletos. La recarga de servicios no es una transacción de rollback
completo: registra fallos de algunos arranques y continúa. Migración no debe
presentar atomicidad de datos como atomicidad de lifecycle.

Core construye `RepeaterManager` con `DATA_DIR/repeater_cooldowns.json` (105), carga
antes de arrancar y flush en stop. Maps de command/telemetry/ping/traceroute/neighbours
persisten epochs y restauran edades monotónicas (`load_state`, 77–94); escritor
atómico con flush/fsync/reemplazo y `shield` (119–156). Es un recurso de bridge.
Mantener mismo objeto, intervalos y ruta durante guardado/reinicio del transporte.
No añadir timers ni retry RF por el hecho de instalar FastAPI.

## 5. Diseño mínimo propuesto para fase 1

Este código es **especificación**, no módulo añadido ni decisión de versiones ASGI.
El seam liviano no importa FastAPI/Uvicorn/Pydantic y es compatible con Python 3.10.

```python
from typing import Any, Protocol

class WebEventSink(Protocol):
    async def broadcast_event(self, event_data: dict[str, Any]) -> None: ...

class WebServerPort(WebEventSink, Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

Los tres métodos son el núcleo de transporte. Son insuficientes para los
consumidores legados de canales/logs/fixtures: durante transición preservar
`router` como fachada de compatibilidad con `channels` delegada, métodos de registro
y wrappers. Host/port/tile_service/server son atributos actuales de montaje/QA,
no deben contaminar el Protocol final. El candidato podrá exponer `bound_address`
para fixtures y lifecycle; no inventar `uvicorn.server.sockets` como equivalente.

Contexto único propuesto: `WebApplicationState` reúne buffers por referencia,
MapTileService y métodos `record_incoming_event`/`log_system_event` extraídos sin
reescribir semántica. `WebControllerBundle` construye los diez controladores una
vez con `ApiContext` apuntando a ese estado y bridge existente; retiene sus locks,
canales y cachés. `WebRuntime` posee callbacks/tasks web y hub. `app.state` recibe
estos mismos objetos y `Depends` sólo devuelve referencias existentes.

Estado/controladores no se crean por lifespan ni por petición. Lifespan ASGI
gestiona recursos exclusivos del adaptador web; no crea bridge/radio/MQTT/cooldowns.
El adaptador embebido recibe app/context, usa loop existente y un worker; conserva
la tarea serve, readiness y errores, cierra listener/WS/tareas propias. La fábrica
headless comprueba `WEB_ENABLED` antes de importar implementación ASGI; revisar
también reexports de `src` y `src.web` y imports de tipos (`TYPE_CHECKING`).

La elección de backend/versiones y la manera de desactivar señales/readiness se
verifican contra el candidato concreto en fase 1. No escribir una subclase Uvicorn
genérica suponiendo un hook de señal estable. Rollback conserva backend nativo y
mismo estado sin abrir ambos listeners/radios.

### Orden de extracción y puertas

1. Registrar ADR por el líder; fijar seam/lifecycle y propiedad de objetos.
2. Extraer estado/registro manteniendo router nativo y referencias; ningún cambio
   de rutas, límites, datos, frecuencia o política RF. Asegurar alias de canales.
3. Separar construcción única del bundle de controladores; conservar locks y
   acceso dinámico a bridge/services tras reload.
4. Integrar runtime de tareas/event sink y compatibilidad; corregir explícitamente
   drenaje de tareas del router como cambio de lifecycle, sin esconderlo en paridad.
5. Añadir adaptador ASGI y lazy factory con readiness/rollback y shutdown acordado;
   permitir elección de transporte sólo al montar, evitando swaps a mitad de TX.
6. Migrar rutas/WS/assets por lotes del plan; retirar fachadas/helpers sólo tras
   adaptar consumidores y acreditar cobertura observable autorizada.

Puerta de extracción: deques y controller instances conservan identidad; cada
evento se registra una vez; canales/secretos/dirty/deleted conservan dueño; services
reload no produce snapshot stale ni resetea cooldowns; headless no exige ASGI;
fallo bind propaga y cierra recursos; stop no deja tareas/map connections. Estas
son condiciones futuras a comprobar, **no resultados de esta fase documental**.

## 6. Invariantes y discrepancias anteriores

| Invariante/observación | Fuente | Tratamiento |
|---|---|---|
| Advert NONE/CHAT→CLIENT, REPEATER/ROOM/SENSOR 2/3/4 | [AdvertDataHelpers.h](../../reference/meshcore/src/helpers/AdvertDataHelpers.h), 7–11; [protocol_types.py](../../src/protocol_types.py), 115–122 | Rol por protocolo; LOCAL por identidad propia, no nombre |
| REPEATER/ROUTER y LOCAL excluidos de contactos/chat | [contact_manager.py](../../src/contact_manager.py), 962, 1594–1607; ContactsController 31–43; [TxController](../../src/web/controllers/tx_controller.py), 49–59 | Mantener guarda en dominio/SDK, incluyendo prefijos y resolución |
| Crear contactos permite ROOM/SENSOR; listado sólo CLIENT | ContactsController 42; NodeRegistry 1600–1607 | Divergencia previa; política requiere decisión expresa, no normalizar con DTO por accidente |
| Texto DM ≤160 bytes UTF-8, NUL prohibido; canal descuenta nombre y `: ` | SDK 1044–1050, 1101–1104 | `max_length=160` de caracteres no acredita bytes |
| Autoadd 0..64, raw hop_limit 0..15; path firmware buffer 64 y modos hash | [ConfigController](../../src/web/controllers/config_controller.py), 416–458; protocol_types 281–282; [MeshCore.h](../../reference/meshcore/src/MeshCore.h), 22; [Packet.h](../../reference/meshcore/src/Packet.h), 79–83 | Ningún hops 0..7 universal ni TTL común |
| TX submit/future hasta 30 s; respuesta 200 resultado, 408/429/503 según fallo | TxController 65–111 | 202/pending sería rediseño propio con consumidores y ACK |
| Admin/config usan fachadas y lock Companion, no toda llamada pasa por TxRateLimiter | SDK 236–267; Config/RepeaterController | No reenrutar/duplicar RF como parte de cambiar servidor |
| Tasks del router se descartan sin consumir excepción/drain en stop servidor | Router 167–175; servidor 95–149 | Deuda previa de lifecycle que debe resolverse explícitamente |
| Stop web acumulativo excede posible 1.5 s exterior | Tabla lifecycle | No declarar parada garantizada sin acuerdo/evidencia |
| `_cli_logs` busca `system_logs` pero servidor no expone ese atributo | CLI 860–870; servidor 61–86 | Fallback diagnóstico actual; alias nuevo sería adición deliberada |
| JSON canales atómico sin fsync; cooldown writer sí flush/fsync | Channels 64–92; RepeaterManager 119–136 | Atomicidad no equivale a misma durabilidad; no prometerla |

Checklist RF de esta fase: no se crean transmisiones, notificaciones, polling,
reintentos ni timers; airtime incremental cero por cambio documental; no hay ruta
nueva de feedback; no se rearma scheduler ni se modifica último timestamp. Si una
fase futura altera alguno, el líder documenta checklist y acuerda límites.

## 7. Adaptación de fixtures y alcance de evidencia

[conftest.py](../../tests/conftest.py), 34–64, redirige rutas y MapTileService a
temporales; `virtual_bridge` (68–105) usa radio virtual, MQTT mock, puerto loopback
del SO y cleanup. Inyecta `router.channels_ctrl.channels` mediante reemplazo;
debe comprobar/actualizar alias tras la extracción. `browser_page` (114–118) lee
`server.server.sockets[0]`; candidato necesita dirección enlazada comprobada.
Preservar `tile_service.close`, cleanup aun con fallo de setup y aislamiento de
paths; no usar estación localhost:8080 como fixture.

Lecturas directas/router: test_web_server, test_node_and_repeater_config,
test_local_config_save_roundtrip, test_diagnostics/export,
test_channels_and_contacts_controllers, test_virtual_mesh_simulation y
test_skill_helpers. Mantener wrappers durante transición y migrar expectativa a
servicio/HTTP observable sin suavizar dominio/secretos/ACK.

Transportes/helpers: test_web_official_compatibility, test_security_audit,
test_websocket_live, test_ws_key_encoding, test_packet_read_authorization,
test_http_cache_contract, test_tile_server, test_remaining_web_regressions/races,
test_fixture_isolation, test_capture_privacy y test_self_info_power_normalization.
No sustituir cobertura socket/WS por llamadas directas al router ni HTTP ASGI
en memoria. Las regresiones de lifecycle y RX/concurrencia conservan mocks de
`start/stop/broadcast_event` y aceptación/fallo de recursos.

Scripts históricos encontrados con montaje/difusión/acceso router:
audit_frontend_browser, inspect_all_views, test_ip_and_security_logging,
test_search_filters, simulate_heltec_v4_mesh, simulate_mesh_network,
simulate_concurrent_network, simulate_full_mesh_validation y
validate_all_node_parameters. No ejecutarlos para acreditar fase 0; revisar sus
efectos/paths antes de futura autorización. Índice textual adicional al final.

Se leyó código/documentación y se buscaron consumidores; no se importó aplicación,
levantó servicio, accedió a estado operativo ni se ejecutaron suites, mypy, Ruff,
Playwright, auditorías con efectos o instalación. La búsqueda inicial encontró
directorios de artifacts con acceso denegado; el inventario posterior excluyó
`**/artifacts/**`, que no contiene código mantenido del contrato. La evidencia
estática no demuestra ausencia de carreras ni funcionamiento de ASGI/SBC.

## 8. Índice textual reproducible de consumidores de montaje y difusión

Inventario por fichero de las referencias bajo `src`, `tests` y `scripts` al
montaje/puerto/event sink. Patrón usado:
`web_server|broadcast_event|MeshCoreWebServer|WebAPIRouter|\.router\.`;
extensión `.py`, excluyendo artifacts. Este índice sirve para reauditar las
adaptaciones; no afirma que cada match sea llamada runtime.

- `scripts/audit_frontend_browser.py` — líneas 31, 32, 36, 253.
- `scripts/inspect_all_views.py` — líneas 39, 40, 44, 106.
- `scripts/run_all_test_categories.py` — líneas 64.
- `scripts/simulate_complex_mesh_scenario.py` — líneas 46, 369.
- `scripts/simulate_concurrent_network.py` — líneas 94, 206, 221.
- `scripts/simulate_full_mesh_validation.py` — líneas 36, 201, 212.
- `scripts/simulate_heltec_v4_mesh.py` — líneas 178, 179, 243, 261.
- `scripts/simulate_mesh_network.py` — líneas 45, 116, 154, 169.
- `scripts/test_ip_and_security_logging.py` — líneas 53, 54, 62, 141.
- `scripts/test_search_filters.py` — líneas 23, 24, 28, 110.
- `scripts/validate_all_node_parameters.py` — líneas 38.
- `src/__init__.py` — líneas 42, 43, 49, 51.
- `src/admin_handler.py` — líneas 45.
- `src/admin/cli_command_executor.py` — líneas 862.
- `src/admin/repeater_executor.py` — líneas 589, 596, 884, 886.
- `src/admin/traceroute_executor.py` — líneas 137, 139.
- `src/bridge_core.py` — líneas 45, 214, 219, 223, 364, 368, 406, 424, 631, 632, 687, 739, 745, 874, 1067, 1069, 1094, 1096.
- `src/routers/repeater_handler.py` — líneas 122, 123, 147, 148, 191, 192.
- `src/routers/system_handler.py` — líneas 63, 64, 85, 87.
- `src/rx_router.py` — líneas 206, 323, 378, 419, 420, 513, 516.
- `src/web/__init__.py` — líneas 6, 7, 9.
- `src/web/api_router.py` — líneas 116, 169, 170, 171.
- `src/web/http_server.py` — líneas 25, 59, 73, 74, 177, 206, 208, 525.
- `tests/audit_layer_runtime_2026_10_04.py` — líneas 33, 109.
- `tests/audit_layer_web_2026_10_04.py` — líneas 30, 55, 73, 169, 181, 182, 221, 247.
- `tests/conftest.py` — líneas 76, 77, 78, 96, 97, 98, 101, 116.
- `tests/test_admin_executors.py` — líneas 93, 247, 248, 265.
- `tests/test_admin_official_compatibility.py` — líneas 270, 274.
- `tests/test_bridge_core_comprehensive.py` — líneas 24, 79, 80, 101, 178, 179.
- `tests/test_capture_privacy.py` — líneas 31, 32, 40, 52, 54, 124, 125.
- `tests/test_core_lifecycle_regressions.py` — líneas 32, 61, 96, 169, 226, 233.
- `tests/test_diagnostics_export.py` — líneas 17, 117.
- `tests/test_diagnostics.py` — líneas 13, 120.
- `tests/test_domain_official_compatibility.py` — líneas 44.
- `tests/test_fixture_isolation.py` — líneas 42, 43, 58, 59, 67.
- `tests/test_http_cache_contract.py` — líneas 16, 46, 47.
- `tests/test_local_config_save_roundtrip.py` — líneas 17, 20, 55.
- `tests/test_node_and_repeater_config.py` — líneas 17, 93, 166, 179, 186, 202, 215, 225, 245, 268, 277, 306, 309, 327, 328.
- `tests/test_numeric_clock_regressions.py` — líneas 30.
- `tests/test_packet_read_authorization.py` — líneas 17, 24, 28, 37, 70, 81, 102, 113, 122, 129, 139.
- `tests/test_passive_route_dispatch.py` — líneas 38, 66, 87, 110, 124.
- `tests/test_recent_regressions.py` — líneas 36, 42, 51, 263.
- `tests/test_remaining_ack_audit.py` — líneas 96, 106, 107.
- `tests/test_remaining_quality_audit.py` — líneas 128, 153, 175.
- `tests/test_remaining_rx_capacity.py` — líneas 21, 99, 103, 124.
- `tests/test_remaining_web_races.py` — líneas 19, 53, 55, 220, 223, 226, 248, 250, 251, 254, 259, 262, 264, 270, 277.
- `tests/test_remaining_web_regressions.py` — líneas 28, 45, 63, 162, 188.
- `tests/test_rx_routers.py` — líneas 213, 264.
- `tests/test_sanitization_fixes.py` — líneas 263, 265, 309, 311, 471, 478, 484, 510.
- `tests/test_security_audit.py` — líneas 12, 23.
- `tests/test_self_info_power_normalization.py` — líneas 28, 29, 37.
- `tests/test_skill_helpers.py` — líneas 151, 156.
- `tests/test_tile_server.py` — líneas 22.
- `tests/test_virtual_mesh_simulation.py` — líneas 58, 79.
- `tests/test_web_official_compatibility.py` — líneas 20, 168, 169.
- `tests/test_web_server.py` — líneas 11, 57, 60, 66, 71, 81, 90, 95, 98, 106, 117, 123, 131, 132, 138, 143, 149.
- `tests/test_websocket_live.py` — líneas 2, 9, 18, 31, 38, 41, 42.
- `tests/test_ws_key_encoding.py` — líneas 15, 19, 20, 29, 66, 78, 92, 100, 114, 129.
