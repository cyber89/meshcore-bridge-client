# Auditoría por capas: transporte, runtime, recepción y registro

Fecha local: 2026-10-04, America/New_York. Revisión de producción de solo lectura sobre el checkout posterior a `c9b2d3c`. Este anexo registra defectos que **siguen presentes**; no aplica correcciones.

Skills consultadas: `async-concurrency-engineering`, `asyncio-profiler-leak-detector`, `clean-code-solid` y `meshcore-source-inspector`. Las señales de longitud o complejidad orientan la revisión; no certifican rendimiento ni convierten un método largo en un error por sí solas.

## Alcance y evidencia

Se analizaron estructuralmente con `ast.parse` los 22 archivos del inventario inferior, y manualmente los flujos indicados. El harness aislado usa objetos reales del dominio y adaptador, mocks del SDK, tareas del loop propio y JSON temporal. No se conectó a UART, radio, broker ni puerto de estación operativa; `tests/conftest.py` bloquea la carga de `.env` y redirige persistencia a temporales.

Comando reproducible desde la raíz:

```powershell
.venv/Scripts/python.exe -m pytest tests/audit_layer_runtime_2026_10_04.py -q -s --no-cov -p no:cacheprovider --basetemp tests/artifacts/audit-runtime-replay-tmp
```

Última ejecución: **12 passed in 1.25s**, código de salida 0. Python 3.12.14, Windows 11, AMD64. Ruff del harness: `All checks passed!`. Estos casos **afirman el comportamiento defectuoso observado** para documentarlo; no son regresiones que acrediten una solución. El archivo no tiene prefijo `test_`, por lo que exige ejecución explícita y no entra en la suite mantenida por defecto. Tras corregir cada problema, convertir su caso en una regresión con la expectativa correcta.

## Problemas confirmados

### RUNTIME-01 — P1: rutas pasivas y cambios de path absorbidos por handlers genéricos

- **Fuentes:** `src/rx_router.py:339`, `:349`, `:354`, `:657`, `:716`; `src/routers/system_handler.py:33`; `src/routers/telemetry_handler.py:22`.
- **Requisito:** un `PATH_UPDATE` debe sincronizar la ruta de salida y un log RF identificado debe conservar su observación de ruta. Las funciones específicas ya implementan ambos comportamientos.
- **Reproducción:** `test_path_update_shadowed_by_system_strategy` inyecta `EventType.PATH_UPDATE` con una clave válida y observa el callback específico; `test_rx_log_route_shadowed_but_direct_control_updates` inyecta `EventType.RX_LOG_DATA`, `adv_key`, path `0102`, count 2 y ruta FLOOD. Después llama directamente al helper como control.
- **Esperado:** ejecución del sincronizador de path y `last_rx_route.count == 2` para el log.
- **Observado:** cero llamadas al sincronizador; el path sólo se publica como sistema. `last_rx_route` permanece `None` por la ruta normal, mientras el helper directo produce count 2.
- **Causa:** el bucle de estrategias crea una tarea y retorna antes de las ramas específicas. `SystemHandler` declara `PATH_UPDATE`; `TelemetryHandler` acepta cualquier LOG y devuelve `True` sin invocar `_handle_rf_log_observation`.
- **Impacto:** mapa y administración pueden mostrar rutas antiguas o desconocidas aunque el firmware entregue información válida. Los helpers y las ramas posteriores aparentan funcionalidad que no se alcanza normalmente.
- **Solución propuesta:** llevar ambas operaciones a los handlers que poseen esos eventos, o ejecutarlas explícitamente antes del despacho y asegurar que no se dupliquen. `GET_CONTACT` es consulta local Companion, no una solicitud RF a la malla. Mantener la serialización existente del adaptador y probar el flujo desde `handle_event`, no sólo el helper.

### RUNTIME-02 — P1: el semáforo limita ejecución, pero no el backlog de tareas RX

- **Fuentes:** `src/rx_router.py:239`, `:342`, `:1194`; `src/serial/sdk_adapter.py:514`; `src/bridge_core.py:209`.
- **Requisito:** colas y trabajo pendiente deben acotarse; un consumidor lento no debe retener trabajo proporcional a toda entrada sin backpressure.
- **Reproducción:** `test_rx_semaphore_does_not_bound_pending_tasks` introduce 1000 eventos válidos en el router con un handler detenido por un `asyncio.Event`, y permite un tick del loop. El `finally` abre la compuerta y drena todas las tareas.
- **Esperado:** política explícita de admisión/cola acotada o coalescencia que limite trabajo pendiente, conservando eventos críticos.
- **Observado:** 1000 tareas propias retenidas, 20 handlers activos. Tras liberar la compuerta se drena correctamente: **no se acredita una fuga permanente**.
- **Causa:** `create_task` ocurre antes de adquirir el semáforo; cada evento mantiene su payload y una tarea esperando. La suscripción del SDK añade otra capa de tareas sin límite de admisión.
- **Impacto:** ráfagas, handlers lentos o clientes WebSocket lentos pueden aumentar memoria y latencia; `MAX_RX_CONCURRENCY=20` no es un límite de cola. El escenario es sintético y no mide un SBC ni 24 horas de operación.
- **Solución propuesta:** cola de recepción acotada con workers propios y política por clase de evento; coalescer observaciones repetidas por nodo cuando sea válido. Definir la capacidad con el usuario y medidas de carga; no inventar intervalos ni pérdida silenciosa de ACK/respuestas.

### RUNTIME-03 — P2: ACKs antiguos siguen correlacionados y la tabla no tiene máximo duro

- **Fuentes:** `src/bridge_core.py:137`, `:154`; `src/routers/repeater_handler.py:98`.
- **Requisito:** una correlación de entrega debe tener vigencia definida y estado pendiente acotado. El comentario actual anuncia poda de registros de más de una hora.
- **Reproducción:** `test_expired_ack_still_publishes_old_delivery` registra ACK a t=100 y recibe el mismo a t=7300. `test_recent_pending_ack_table_not_capped_at_prune_threshold` registra 1000 códigos distintos a la misma hora, sin enviar paquetes.
- **Esperado:** una entrada vencida no correlaciona un request antiguo; la capacidad real debe estar documentada y respetarse.
- **Observado:** se publica `message_delivered` con `msg_id=expired-request`, 7200 segundos después; la entrada no se consume. Se retienen 1000 registros recientes pese al umbral de poda 200.
- **Causa:** `resolve_pending_ack` usa `dict.get` sin comprobar edad ni retirar entrada; la poda sólo sucede al registrar otro mensaje y únicamente cuando el tamaño ya supera 200. El número 200 es un disparador de poda, no un máximo.
- **Impacto:** asociaciones antiguas y trabajo/estado retenido innecesariamente. No se demostró una colisión criptográfica ni entrega falsificada por un atacante.
- **Solución propuesta:** expiración coherente en registro y resolución, limpieza determinista, máximo duro y tratamiento definido de duplicados/reenvíos. Acordar TTL/capacidad; no elegirlos unilateralmente. Probar ACK dentro/fuera de vigencia, repetido y cierre.

### RUNTIME-04 — P1: defaults visuales se convierten en estado persistente del nodo

- **Fuentes:** `src/contact_manager.py:685`, `:686`, `:689`, `:1639`, `:1658`, `:1661`, `:1780`, `:1895`, `:1896`.
- **Requisito:** mantener diferenciados datos recibidos, capacidades confirmadas, desconocidos y defaults para la presentación. Persistencia no debe inventar valores de firmware.
- **Reproducción:** `test_registry_persists_presentation_defaults_as_observed_fields` crea un repetidor sin `hop_limit`, `max_tx_power` ni `repeat_enabled`, guarda JSON temporal y restaura otro registro. `test_analytics_invents_unknown_repeater_measurements` añade un cliente remoto y consulta analítica.
- **Esperado:** esos tres campos siguen `None` después de restaurar; la analítica conserva desconocidos y no atribuye vecinos no observados.
- **Observado:** después del roundtrip aparecen `hop_limit=3`, `max_tx_power=22`, `repeat_enabled=True`. La analítica además muestra `tx_power=20` y `connected_clients_count=2`, aunque no existe medición TX ni lista de vecinos.
- **Causa:** `save_to_file` usa `_list_nodes_snapshot`, que llama al DTO visual `NodeContactInfo.to_dict`. Ese DTO introduce defaults; `_deserialize_node_contact` los toma como valores del dominio. El ranking sustituye otra ausencia con el total de nodos remotos directos, incluyendo los de saltos desconocidos.
- **Impacto:** después de reiniciar, capacidades y configuración aparentan confirmarse sin lectura del dispositivo. El límite TX inventado puede influir en validaciones posteriores, y el ranking atribuye conectividad no demostrada.
- **Solución propuesta:** separar serialización de persistencia, datos públicos observados y hints visuales. Guardar campos crudos y procedencia, conservar `None`, presentar defaults como `suggested_*` cuando corresponda. Para archivos históricos, migrar sólo lo que pueda distinguirse de una medición, documentando las ambigüedades.

### RUNTIME-05 — P1: una respuesta Companion de otro tipo confirma un setter raw

- **Fuentes:** `src/serial/sdk_adapter.py:128`, `:143`, `:145`, `:940`; referencias `reference/meshcore_py/src/meshcore/packets.py:28`, `:93`, `reference/meshcore/examples/companion_radio/MyMesh.cpp:1212`.
- **Requisito:** confirmar un comando con la respuesta admitida para ese opcode. Firmware `CMD_SET_ADVERT_NAME=8` termina en `writeOKFrame`; BATTERY=12 responde a GET_BATT_AND_STORAGE=20.
- **Reproducción:** `test_raw_setter_accepts_unrelated_battery_response` inicia `send_raw_companion_frame(b'\x08Audit name')` y el mock de transporte devuelve una trama BATTERY `0x0C`, sin ACK de SET_NAME.
- **Esperado:** esa trama no completa el setter; conservar estado pendiente hasta OK, ERROR, timeout o desconexión.
- **Observado:** el método devuelve `True` inmediatamente.
- **Causa:** excepto GET_CONTACTS, cualquier respuesta con primer byte `<0x80` completa el future con `data[0] != 1`. El lock impide simultaneidad local, pero no valida el tipo de una respuesta atrasada.
- **Impacto:** aplicaciones TCP Companion pueden recibir confirmación positiva de comandos no confirmados. No se reprodujo en UART físico ni se afirmó que toda respuesta tardía tenga este resultado.
- **Solución propuesta:** tabla de respuestas permitidas por opcode y tratamiento de streams/pushes; distinguir respuesta inesperada. Los OK sin identificador siguen siendo ambiguos después de timeout: debe establecerse una recuperación del transporte que no marque certeza ni retransmita RF automáticamente.

### RUNTIME-06 — P2: SELF_INFO asíncrono reintroduce TX unsigned en la caché normalizada

- **Fuentes:** `src/serial/sdk_adapter.py:856`, `:864`; `src/rx_router.py:1107`; referencia `reference/meshcore_py/src/meshcore/reader.py:168`.
- **Requisito:** tratar el TX del firmware como int8 con signo de manera uniforme en lectura explícita y eventos espontáneos.
- **Reproducción:** `test_unsolicited_self_info_reintroduces_unsigned_tx_power` parte de `_local_config['tx_power']=-9`, recibe SELF_INFO con el byte SDK `247`, usa el handler real del adaptador y el router real.
- **Esperado:** el bridge mantiene -9 dBm.
- **Observado:** `_self_info` y `_local_config` acaban en 247; el log imprime `TX: 247 dBm`.
- **Causa:** la corrección de la lectura explícita de configuración no está aplicada a la ruta de evento; ambas copian el entero sin conversión signed.
- **Impacto:** lectura explícita y estado en vivo pueden contradecirse. Esto amplía la corrección anterior; no afirma que el guardado explícito vuelva a fallar.
- **Solución propuesta:** normalizar en una frontera canónica común a SELF_INFO y consultas; preservar el payload original privado sólo cuando el SDK lo necesite. Añadir regresión que alterne lectura y evento en vivo para -9, 0 y máximo observado.

### RUNTIME-07 — P3: FIFO cambia si retrocede el reloj de pared

- **Fuentes:** `src/rate_limiter.py:74`, `:78`, `:79`, `:706`.
- **Requisito:** desempate estable de solicitudes de igual prioridad en orden de admisión; `counter` se documenta como mecanismo de desempate.
- **Reproducción:** `test_priority_queue_fifo_changes_when_wall_clock_moves_back` encola prioridad 1, counter 1, created_at 100; después prioridad 1, counter 2, created_at 90, simulando ajuste de reloj.
- **Esperado:** first, second.
- **Observado:** second, first.
- **Causa:** `@dataclass(order=True)` ordena por `priority`, luego `created_at` de `time.time`, después `counter`. El reloj mutable domina la secuencia.
- **Impacto:** cambio de orden de mensajes en ajustes NTP/manuales; no hay prueba de pérdida del payload.
- **Solución propuesta:** comparar prioridad y secuencia exclusivamente, dejando tiempo de pared como metadato `compare=False`; usar monotónico para plazos relativos.

## Código en desuso, duplicación y clases/métodos

### RUNTIME-CODE-01 — P3: índice de nombres mantenido sin participar en búsquedas

`NodeRegistry._nodes_by_name` (`src/contact_manager.py:894`) se actualiza, borra y limpia en 20 sitios, pero `get_by_key_or_prefix` y `find_by_name` recorren `_nodes_by_key`. La búsqueda de referencias en `src/`, `tests/` y `meshcore_bridge.py` no encontró lector que resuelva mediante el índice; `remove_node` sólo recorre el índice para limpiar sus propios residuos. `test_unused_name_index_does_not_affect_lookup_control` vacía el índice y ambas resoluciones por nombre/alias siguen funcionando.

**Propuesta:** retirar ese estado y sus escrituras internas si no se va a usar, o implementar un índice multivalor con rechazo de ambigüedad y comprobarlo en todas las mutaciones. No usar el diccionario actual como resolución directa: colisiona con nombres/aliases repetidos. Un plugin externo podría acceder a un atributo privado, por lo que la búsqueda no certifica ausencia de consumidores fuera del checkout.

Las ramas específicas de RUNTIME-01 son código funcionalmente oculto, no helpers para borrar: primero restaurar comportamiento. `serial_driver.py` es una fachada de importación usada por el core y por tests; **no** se clasifica como basura. Los callbacks del SDK se registran dinámicamente; ausencia de una llamada textual directa no acredita método muerto. `RawSerialFramingAdapter` declara explícitamente ser un parser en memoria con transmisión NOT_SUPPORTED: esa capacidad limitada no constituye un fallo UART.

Las clases grandes `MeshcoreSDKAdapter`, `RxEventRouter`, `MeshCoreBridge` y `NodeRegistry` combinan dispatch, compatibilidad, cachés, persistencia y presentación. La longitud es una señal, no una medición de rendimiento. Refactorizar primero los puntos con defecto demostrado: persistencia separada del DTO, despacho sin ramas duplicadas y admisión RX acotada. Los getters delegados del dominio no se consideran innecesarios sólo por su tamaño. No se afirma que cada clase/método sea óptimo: tal afirmación requeriría cargas y objetivos definidos.

## Riesgos revisados sin reproducción de un defecto final

1. **Durabilidad de archivos:** escrituras temporales y replace dan atomicidad frente a lectura parcial, pero los writers JSON no realizan fsync. No se simuló corte eléctrico ni pérdida de datos; evaluar el requisito de durabilidad antes de exigir fsync y medir su coste.
2. **Apagado con I/O lento:** los límites por subsistema y `to_thread` evitan bloquear el loop, pero cancelar un await no detiene un thread de disco. No se acreditó pérdida de escritura real durante cierre. Probar con writer controlado y decidir cómo esperar threads propios sin extender el apagado arbitrariamente.
3. **Airtime:** la estimación usa tamaños de payload, no una medición RF completa de todos los hops/reintentos. No se cuantificó discrepancia física. Separar estimado y medido y revisar todos los productores de tráfico antes de cambiar política.
4. **Backoff/reloj:** watchdog usa heartbeat basado en `time.time`, sensible a ajustes del host; no se reprodujo reconexión falsa. Evaluar reloj monotónico para actividad y conservar UTC para persistencia.
5. **Contratos de capabilities:** `get_channels` retorna caché si existe, y `sync_all_contacts` puede conservar caché al fallar refresh; hace falta distinguir snapshot y lectura reciente. No se demostró en este anexo que el consumidor los presente como lectura confirmada.
6. **Excepciones background:** callbacks canónicos consumen errores; algunos handlers registran tareas con sólo `set.discard`. No se produjo una excepción no consumida en servidor real; unificar ownership y probar fallos de broadcast antes de refactorizar.
7. **Load_history repetido:** el método público agrega registros sin limpiar historial previo. Constructor sólo lo llama una vez en producción; posible riesgo si una futura recarga lo usa, no un flujo demostrado actualmente.

Control positivo ejecutado: `test_sdk_disconnect_resolves_raw_waiter_control` comprueba que disconnect completa el future raw con False y elimina `mc`. No se clasificó esa ruta como tarea huérfana.

## Inventario y profundidad real

Todos los archivos siguientes fueron parseados con AST. “Manual” significa inspección de código y traza de callers; “repro” sólo acredita los escenarios de este harness. No existe promesa de cobertura dinámica de todos los métodos.

| Archivo | Líneas | Clases | Funciones/métodos incl. internos | Revisión manual/reproducción |
|---|---:|---:|---:|---|
| src/serial/raw_framing.py | 128 | 1 | 5 | Máquina de framing completa, límites, escape y declaración sin UART; sin nueva reproducción |
| src/serial/sdk_adapter.py | 1636 | 2 | 77 | Ciclo connect/disconnect, lock, eventos, raw, TX y guardas, canales/contactos y cachés; repro raw/SELF_INFO/disconnect |
| src/serial/serial_base.py | 149 | 1 | 22 | Contrato completo y autodetección; sin autodetección real |
| src/serial/watchdog.py | 164 | 1 | 5 | Ciclo completo, backoff y propiedad de reconexión; sin tiempos reales USB |
| src/serial/__init__.py | 16 | 0 | 0 | Exports completos |
| src/routers/advert_handler.py | 175 | 1 | 5 | Clasificación completa, import vs RX y posición; sin nueva reproducción |
| src/routers/base.py | 60 | 3 | 2 | DTO/protocolo completos |
| src/routers/channel_handler.py | 67 | 1 | 2 | Estrategia completa y guarda local |
| src/routers/direct_handler.py | 64 | 1 | 2 | Estrategia completa y guarda local |
| src/routers/repeater_handler.py | 203 | 1 | 2 | ACK y trace completos; repro ACK vencido |
| src/routers/system_handler.py | 93 | 1 | 2 | Predicado/handle completos; repro PATH_UPDATE |
| src/routers/telemetry_handler.py | 79 | 1 | 2 | Predicado/handle completos; repro RX_LOG |
| src/routers/__init__.py | 22 | 0 | 0 | Exports completos |
| src/bridge_core.py | 1074 | 4 | 70 | Inicialización, ownership, lifecycle, ACK, TX y run_forever; repro ACK; límites shutdown por inspección |
| src/serial_driver.py | 22 | 0 | 0 | Fachada completa, callers verificados |
| src/rx_router.py | 1245 | 3 | 23 | Normalización, dispatch, rutas, telemetría y cache SELF_INFO; repro shadowing/backlog/SELF_INFO |
| src/rate_limiter.py | 795 | 7 | 28 | Cola, workers, futures, historial, stats y cutoff; repro FIFO |
| src/contact_manager.py | 1963 | 8 | 129 | Identidad/canonical keys, merge, contactos, analytics, DTO, writer/restore, índice; repro persistencia/analytics/índice |
| src/event_utils.py | 49 | 0 | 1 | Extracción completa de sender; sin nueva reproducción |
| src/deduplicator.py | 70 | 1 | 6 | Clase completa, monotónico y lock; sin nuevo estrés |
| src/packet_buffer.py | 294 | 3 | 8 | Record/snapshot/export completos; sin benchmark ni nuevo replay PCAP |
| src/health_reporter.py | 85 | 2 | 5 | Payload/ciclo/stop completos; sin broker |

Los números son descriptivos de este checkout, no thresholds universales. El orquestador integra las mediciones AST de complejidad y el resto de capas en el informe principal.

## Orden de corrección y aceptación

1. Separar persistencia de presentación (RUNTIME-04), con migración y regresión reload sin datos inventados.
2. Correlación raw por opcode (RUNTIME-05), con respuestas correctas/ajenas, streams, timeout y desconexión.
3. Despacho de rutas (RUNTIME-01), verificando desde el evento SDK hasta registro y WebSocket.
4. Diseño de admisión RX (RUNTIME-02), acordando capacidad/política y midiendo ráfagas más consumidor lento.
5. Vigencia/capacidad de ACK (RUNTIME-03) y normalización de SELF_INFO (RUNTIME-06).
6. FIFO monotónico/secuencia (RUNTIME-07) y simplificación segura del índice (RUNTIME-CODE-01).

No crear retransmisiones RF, timers nuevos, ni consultas periódicas para encubrir inconsistencias. El checklist LoRa y el acuerdo de límites son necesarios al implementar cualquier política nueva que produzca paquetes; las reproducciones de esta auditoría no transmiten ninguno.
