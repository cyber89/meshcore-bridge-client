# Auditoría por capas del sistema MeshCore Bridge

Fecha: 2026-10-04. Base de producción: `c9b2d3c`.
Solicitud: investigar lógica, errores, contradicciones, código en desuso y
calidad de clases/métodos; reproducir y documentar problemas a corregir.

## Plan y contrato de la auditoría

1. Inventariar recursivamente módulos, clases, funciones/métodos y dependencias.
2. Revisar las cinco capas canónicas de `ARCHITECTURE.md`, con persistencia,
   instalación y herramientas QA como aspectos transversales.
3. Trazar entradas, validación, permisos, estado, colas, SDK, ACK, persistencia,
   publicación y render; contrastar con firmware y SDK de referencia.
4. Reproducir fallos en harness explícitos, datos temporales, mocks y servidores
   virtuales propios. No conectar radio, broker operativo o servicios existentes.
5. Distinguir error reproducido, discrepancia estática, riesgo no reproducido,
   deuda técnica y falso positivo descartado. Priorizar por impacto observable.
6. Consolidar resultados, evidencias y plan de corrección; revisar links/diff y
   publicar sólo artefactos propios. Esta tarea no corrige producción ni elimina
   código antes de decidir sobre los hallazgos.

Roles: principal (integración, inventario/métricas y QA); especialista runtime
(async, transporte, colas, registro/persistencia); especialista web (SPA, API,
WS y seguridad); especialista protocolo/integración (admin, SDK, MQTT,
instalación y referencias). Se asignan archivos de evidencia distintos.

Skills: `clean-code-solid`, `refactoring-clean-architecture`, `bridge-test-runner`
y las skills especializadas indicadas en cada anexo. Los umbrales de tamaño o
complejidad son orientativos; no prueban por sí solos que una clase sea incorrecta
o que un método esté optimizado. Una auditoría no acredita optimalidad universal.

No se añaden transmisiones, timers, reintentos ni límites RF; las reproducciones
usan fixtures aisladas. Los cambios de configuración operativa que una solución
futura necesite deben respetar el checklist LoRa de `AGENTS.md`.

## Resultado y alcance real

Auditoría finalizada sobre `c9b2d3ce4c1776f2d0603f57481df2395d84ea2e`.
Se documentan **39 hallazgos reproducidos**: 31 problemas de funcionamiento o
contrato (7 runtime, 11 web y 13 protocolo/integración), más seis observaciones
de métricas, herramientas QA y aislamiento de la demo, y dos del simulador.
Las seis observaciones de calidad incluyen
contradicciones medidas y una semántica de gráfico que necesita aclaración;
no todas son fallos críticos. Además hay un índice redundante demostrado,
candidatos de desuso y riesgos estáticos separados. **No se corrigió producción
en esta tarea**: cada hallazgo sigue abierto y tiene una solución propuesta.

Los seis hallazgos P1 de los anexos funcionales son RUNTIME-01/02/04/05,
WEB-01 y PI-02. La exposición de credenciales de WEB-01/PI-02 merece atenderse
primero; la prioridad no acredita explotación de una instalación real.
Las reproducciones usan secretos ficticios y adaptadores simulados.

Inventario completo estructural: **63 archivos Python, 113 clases y 946
funciones/métodos, incluidos internos**, más 23 assets JS/CSS/HTML. Cada símbolo
Python tiene archivo, línea, tamaño, parámetros y señal de decisiones en
[inventory.json](audits/layers-2026-10-04/inventory.json) y
[methods.csv](audits/layers-2026-10-04/methods.csv).
El anexo web inventaría léxicamente 11 clases JS propias y 263 métodos;
no se presenta esa extracción como un parser JS completo. QR e iconos reciben
inventario/búsqueda, sin certificación semántica de todo su código de terceros.

La revisión manual sigue flujos y puntos de riesgo en todas las capas; los
anexos identifican qué archivos recibieron lectura dirigida y cuáles sólo
inventario. Ni el inventario ni una suite verde demuestran que cada combinación
de cada método sea correcta u óptima. No se midió throughput del servicio real,
SBC, airtime físico, broker real ni interoperabilidad con radios instaladas.

## Informes y evidencia navegable

| Especialidad | Informe con pasos, esperado/observado, causa y solución | Evidencia estructurada | Harness explícito |
|---|---|---|---|
| Transporte, concurrencia, recepción, registro | [runtime.md](audits/layers-2026-10-04/runtime.md) | [runtime.json](audits/layers-2026-10-04/runtime.json) | [runtime](../tests/audit_layer_runtime_2026_10_04.py) |
| SPA, REST/WS, autenticación y privacidad | [web.md](audits/layers-2026-10-04/web.md) | [web.json](audits/layers-2026-10-04/web.json) | [web](../tests/audit_layer_web_2026_10_04.py) |
| Firmware/SDK, admin local/remoto, MQTT, sensores, instaladores | [protocol-integration.md](audits/layers-2026-10-04/protocol-integration.md) | [protocol-integration.json](audits/layers-2026-10-04/protocol-integration.json) | [protocolo](../tests/audit_layer_protocol_2026_10_04.py) |
| Métricas, verificación y demo | [quality.md](audits/layers-2026-10-04/quality.md) | JSON `quality-*` del mismo directorio | [calidad](../tests/audit_layer_quality_2026_10_04.py) |

Los harness no tienen prefijo `test_`: se ejecutan expresamente y **afirman el
defecto actual**, no la solución deseada. Su aprobación acredita la réplica;
no deben incorporarse sin cambiar expectativas a la suite de aceptación.
Los anexos y JSON se versionan; XML, cobertura y temporales de QA permanecen
en `tests/artifacts/layers-2026-10-04/`, excluidos por las reglas del proyecto.

## Capas canónicas y lógica end-to-end

Se usa la clasificación de [ARCHITECTURE.md](ARCHITECTURE.md), no la numeración
distinta de auditorías históricas. Los módulos de adaptadores públicos pueden
cruzar una frontera de transporte; la tabla clasifica responsabilidades.

| Capa | Responsabilidad / módulos | Hallazgos principales |
|---|---|---|
| L1 Presentación y exposición | SPA, HTTP/WS, controllers, entrada/salida MQTT | WEB-01…11; PI-02/03/04/09/10/11/12 |
| L2 Aplicación y orquestación | BridgeCore, AdminHandler, executors, diagnóstico y lifecycle | RUNTIME-01/02/03/06; PI-01/04/05/06/13; Q-06 |
| L3 Dominio y políticas de malla | NodeRegistry, RepeaterManager, colas TX, deduplicación, LQI, métricas | RUNTIME-03/04/07; PI-06/07; Q-03/04/05 |
| L4 Protocolo y modelos puros | Enums/dataclasses, layouts, parsing LPP y conversiones | PI-01/07/08/11/13; RUNTIME-05/06 |
| L5 Infraestructura | SDK/serial/raw, TCP Companion, MQTT transporte, JSON, MBTiles, IndexedDB | RUNTIME-04/05/06; WEB-07; Q-06; riesgos de despliegue |

Flujo de escritura inspeccionado: entrada HTTP/MQTT/CLI → autenticación y
validación → capacidad y rol → comando de SDK/CLI → prueba de despacho →
respuesta real → estado confirmado → publicación pública y persistencia → UI.
Los fallos PI-03/04/05/12/13 y RUNTIME-05 muestran saltos entre esos estados:
conversión antes de validar, cambios parciales ocultos, despacho confundido con
éxito, error textual con envelope ok y precisión no serializable confirmada.

Flujo de recepción inspeccionado: SDK → normalización y guarda de origen →
captura → dispatch → waiter administrativo/registro → eventos públicos →
snapshots REST y stream WS → render/persistencia del navegador. WEB-01 está
en un sink anterior a la redacción semántica; RUNTIME-01 en el dispatch;
RUNTIME-06 en normalización; WEB-06/08/10/11 en conciliación de estado.
Una corrección de sólo el controller o sólo el DOM no cierra esos recorridos.

## Registro consolidado de problemas reproducidos

P1: pérdida importante de garantías o privacidad; P2: resultado/contrato
incorrecto; P3: deuda, orden o presentación. Se conserva la prioridad del
especialista; las condiciones de cada reproducción se encuentran en el anexo.

### Recepción, transporte y persistencia

| ID | Prioridad | Error reproducido | Corrección propuesta |
|---|---|---|---|
| RUNTIME-01 | P1 | Estrategias genéricas absorben PATH_UPDATE y RX_LOG antes de sincronizar rutas; helper directo sí funciona. | Propietario único de cada evento; probar desde dispatch SDK hasta registro. |
| RUNTIME-02 | P1 | 1000 entradas retienen 1000 tareas aunque sólo 20 handlers estén activos. Drenan al liberar el consumidor. | Admisión acotada y workers; acordar capacidad y política por evento. No se demostró fuga permanente. |
| RUNTIME-03 | P2 | ACK de 7200 s correlaciona request antiguo; 1000 entradas recientes sobreviven al disparador de poda 200. | Comprobar vigencia y consumo; capacidad/duplicados explícitos, TTL acordado. |
| RUNTIME-04 | P1 | JSON convierte desconocidos en hop=3, maxTX=22, repeat=true; analítica inventa TX=20 y vecinos. | Serializer de persistencia separado del DTO visual, procedencia y desconocidos conservados. |
| RUNTIME-05 | P1 | Setter raw SET_NAME acepta respuesta BATTERY como confirmación. | Correlación por respuesta admitida del opcode y manejo explícito de timeout/desconexión. |
| RUNTIME-06 | P2 | SELF_INFO en vivo convierte -9 dBm previamente normalizados en 247. | Conversión signed en frontera canónica común a evento y lectura. |
| RUNTIME-07 | P3 | Retroceso del reloj de pared invierte FIFO con igual prioridad. | Prioridad+secuencia para ordenar; tiempo de pared sólo como metadato. |

### Web y contratos externos

| ID | Prioridad | Error reproducido | Corrección propuesta |
|---|---|---|---|
| WEB-01 | P1 | Credencial CLI aparece en búfer, WS RF, JSON/CSV/PCAP/hex; GET capturas no exige clave configurada. | Entrega privada separada antes del primer sink; redacción/exclusión contextual y auth de capturas. |
| WEB-02 | P2 | API key con símbolos funciona REST pero su forma URL-encoded falla WS. | Parser de credenciales común y comparación constante. |
| WEB-03 | P2 | GET recarga mapas sin autorización; POST equivalente se rechaza. | Mutación sólo POST y política uniforme de alias. |
| WEB-04 | P2 | POST subruta de canales inexistente crea canal con 201 y escritura SDK. | Recursos/métodos exactos y 404 antes de cualquier efecto. |
| WEB-05 | P2 | Chat HTTP 503 borra texto y queda queued sin aviso. | Estado failed persistido, error visible y recuperación de borrador sin reenvío automático. |
| WEB-06 | P2 | Historial antiguo resuelto tarde se dibuja en otro canal activo. | Generación/feed después de await y caché separada del render. |
| WEB-07 | P2 | Envío confirmado cambia memoria a sent pero IndexedDB queda queued. | Persistencia ordenada del estado y ACK concurrente no degradado. |
| WEB-08 | P2 | Snapshot vacío válido no retira nodos anteriores. | Reconciliar vacío completo; diferenciar error o paginación parcial. |
| WEB-09 | P2 | Potencia observada 27/-9 se muestra en slider como 22/2. | Capacidad real/unknown separada y lectura sin clamp. |
| WEB-10 | P2 | Sniffer pide 200 iniciales y recibe los más antiguos, omitiendo los últimos 50 de 250. | Contrato tail/orden/cursor coherente con listado reciente. |
| WEB-11 | P2 | Snapshot HTTP demorado elimina evento RF recibido por WS. | Merge por identidad/sesión y generación frente a clear/reconnect. |

### Protocolo, administración e integración

| ID | Prioridad | Error reproducido | Corrección propuesta |
|---|---|---|---|
| PI-01 | P2 | Reloj remoto usa tag del solicitante (2024) en vez de RTC remoto (2026). | Parsear data LE validada según layout SDK; tag sólo correlación. |
| PI-02 | P1 | get_config publica PIN BLE sintético sin redacción por MQTT. | Sanitización única de salidas públicas admin/CLI; conservar dato privado interno. |
| PI-03 | P2 | bool flags y modo 1.9 se convierten en 1 y se escriben. | Validación compartida de tipos originales antes de int(). |
| PI-04 | P2 | Variables custom escriben gps antes de rechazar segunda clave; error no indica applied. | Prevalidación de todo el lote y partial para fallos posteriores de confirmación. |
| PI-05 | P2 | refresh_telemetry devuelve ok con 0/5 respuestas. | Separar dispatched, partial, timeout y datos históricos. |
| PI-06 | P2 | Lote CLI de repetidor despacha cinco comandos a CLIENT conocido. | Rol/capacidad antes de cualquier branch; clasificación sólo por fuente canónica. |
| PI-07 | P2 | solar_mv=100 se trata como 100 V; cadena false se convierte en true. | Unidades de clave explícitas y booleanos estrictos. |
| PI-08 | P2 | Corriente LPP oficial 117 interrumpe decodificación y pierde temperatura posterior. | Tabla oficial de tamaños, signedness y escala por tipo. |
| PI-09 | P2 | ERROR get_time termina en Hora del Nodo con hora del host y status ok. | Estado no confirmado/error; host identificado por separado. |
| PI-10 | P2 | CLI ACL local afirma PIN activo y ADMIN/OPERATOR sin evidencia. | Capacidad real o unsupported; separar BLE PIN de ACL repeater. |
| PI-11 | P2 | Terminal tuning etiqueta rx_delay como segundos aunque la vista ya dice factor. | Unidad adimensional coherente en todas las salidas. |
| PI-12 | P2 | set tx abc retorna advertencia con status ok. | Error estructurado de validación/uso CLI. |
| PI-13 | P2 | applied/cache RF mantienen .0009 que el SDK trunca en wire. | Cuantizar antes de enviar o rechazar precisión no representable. |

### Calidad, métricas y aislamiento

| ID | Categoría | Observación reproducida | Trabajo propuesto |
|---|---|---|---|
| Q-01 | Herramienta QA | Helper de refactoring anuncia 100% limpio y omite src/admin/unsafe.py por glob no recursivo. | Inventario recursivo y alcance verificable en salida. |
| Q-02 | Definición de métrica | Helper suma with sin decisión y ramas de función anidada al padre. | Métrica documentada por scope o herramienta estándar; no atribuir McCabe certificado. |
| Q-03 | Contradicción medida | Docstring promete <100 KB; 1440 buckets retienen ~670 KB de asignaciones Python aisladas. | Corregir afirmación y medir presupuesto sobre plataforma/carga definidos. No es RSS ni fuga. |
| Q-04 | Presentación/contrato | RX actual suma al contador, pero no a ninguna serie hasta cerrar minuto. | Incluir bucket en curso o identificar claramente ventana de minutos cerrados. |
| Q-05 | Estadística incorrecta | Paquete anterior a retención se suma al bucket más antiguo disponible, con otro timestamp. | Excluirlo de serie retenida o política de atrasados explícita; conservar totales según contrato. |
| Q-06 | Aislamiento de demo | db_path legado se ignora y el guardado usa config.NODE_REGISTRY_STORAGE_PATH. | Entorno de demo con rutas propias explícitas y lifecycle sin archivos de estación. |

Q-06 se reprodujo interceptando start y guardando exclusivamente datos de la
fixture temporal. No se arrancó la demo real ni se sobrescribió una estación;
el riesgo de ejecutarla con configuración operativa deriva del path comprobado.

Dos reproducciones complementarias del [anexo de integración](audits/layers-2026-10-04/protocol-integration.md)
usan el simulador sin connect/escena ni radio: **PI-C01**, alias `channel_999`
elude la validación del índice original; **PI-C02**, set_time confirma un valor
que get_time no conserva. Ambas P2, con disconnect y cero tareas pendientes.
Resolver destino antes de validar y mantener RTC virtual común a SDK/raw.
No se atribuyen estos fallos al dispositivo físico ni se mezclan con los 13
casos del harness principal de integración.

## Código en desuso y deuda: decisiones con evidencia

No se eliminó código por ausencia de referencias textuales. El índice AST usa
nombres sin tipos: homónimos, reflection, callbacks, herencia y APIs externas
generan falsos candidatos. Los anexos detallan las búsquedas de callers.

| Candidato / duplicación | Evidencia y decisión necesaria |
|---|---|
| NodeRegistry._nodes_by_name | Se mantiene en mutaciones pero las búsquedas usan _nodes_by_key. Control vaciando índice conserva lookup. Retirar estado o diseñar índice multivalor coherente; no usar el actual para nombres ambiguos. |
| api_router._safe_int | Helper privado sustituido por _parse_bounded_int, sin consumidor conocido en ese módulo. Candidato a eliminación tras verificar imports/compatibilidad. |
| SystemController.get_logs / LogsController report | Tests llaman primero, tráfico usa otro controller; rutas report se interceptan antes. Unificar contrato y probar endpoint efectivo, evitando mantener sólo tests de ruta inactiva. |
| Sniffer.toggleSnifferPause / EventBus.once y constantes | Sin consumidor léxico productivo conocido; posibles API legadas. Decidir soporte/deprecación, no borrar eventos homónimos del SDK. |
| RepeaterManager.transmit_callback | Argumento almacenado no consumido. Diferente del callback TX real del limiter, que sí se usa. Revisar contrato externo antes de retirarlo. |
| MQTT publish_safe(ttl_seconds) | Aceptado e ignorado, sin consumidor interno encontrado. Deprecar o definir semántica; no prometer caducidad. |
| Normalizadores de telemetría y reseteo local de stats | Duplicación de unidades/parsers/cache. Unificar con modelos y alcance explícitos después de cerrar contratos defectuosos. |
| _route_channels / shutdown / on_mqtt_message / apply_time_decay | Señales sin uso productivo estático no equivalen a basura: existen callers de tests/APIs/callbacks. Clasificar compatibilidad y revisar integración antes de suprimir. |

No se clasifican como basura serial_driver (fachada usada), dataclass hooks,
__getattr__, logging.emit, callbacks registrados por dispatch, wrappers CLI,
aliases deprecados con regresiones ni el parser raw sin UART declarado.
`scratch/` tiene artefactos históricos ajenos; no se añadió a producción ni se
borró como parte de esta auditoría.

## Clases/métodos: mantenibilidad y optimización verificable

El inventario raíz parsea cada Python con gramática objetivo 3.10 sin importarlo.
Calcula una **señal de decisiones AST**, excluye funciones/clases/lambdas
anidadas y with; incluye short-circuit, loops, except y comprehensions.
No es complejidad McCabe/Radon certificada. Los conteos `branch_nodes` de los
anexos usan otra definición y **no se comparan numéricamente** con esa señal.
`span_lines` cuenta rango físico, incluidos comentarios y docstrings.

| Clase | Rango físico | Métodos directos | Motivo de revisión / propuesta |
|---|---:|---:|---|
| MeshcoreSDKAdapter | 1532 | 55 | Transporte, callbacks, raw y cache; centralizar correlación/normalización. |
| RepeaterAdminExecutor | 1334 | 25 | Validación, compilación, dispatch y confirmación; catálogo de operaciones con estados explícitos. |
| MeshCoreWebServer | 1155 | 29 | Parser HTTP/WS, auth y distribución; límites comunes sin romper compatibilidad. |
| LocalConfigExecutor | 1108 | 35 | Validadores, SDK y cache; esquema compartido para todos los ingresos. |
| NodeRegistry | 1076 | 43 | Dominio, analítica y JSON; separar serializer y presentación. |
| RepeaterManager | 1072 | 36 | Auth, cooldown, commands y heurísticas; parsers/políticas por responsabilidad. |
| RxEventRouter | 1032 | 17 | Normalización, captura y dispatch; admisión acotada y sinks privados/públicos. |
| CliCommandExecutor | 1012 | 51 | Presentación y estado de dispositivo mezclados; respuestas tipadas con procedencia. |
| MeshCoreBridge | 1004 | 51 | Ownership/lifecycle; conservar capa de orquestación sin añadir parsers. |
| WebAPIRouter | 661 | 18 | Rutas/alias/normalización; tabla exacta y controllers activos. |

Puntos con más señal de decisiones en este checkout:

| Método | Rango de líneas | Señal AST | Implicación |
|---|---:|---:|---|
| ContactsController._import_contact | 223 | 111 | Muchos formatos/guardas; preservar invariantes y dividir parse/validate/execute. |
| RxEventRouter._handle_mesh_telemetry_msg | 240 | 99 | Conversiones/alias/contexto; modelo tipado fuente-específico. |
| LocalConfigExecutor._prevalidate_local_params | 189 | 93 | Frontera de validación que otras entradas eluden; reutilizar, no duplicar. |
| RepeaterAdminExecutor._execute_batch_config | 281 | 90 | Catálogo de parámetros y confirmación independiente. |
| RxEventRouter._extract_normalized_meta | 149 | 68 | Procedencia de ruta/señal debe conservarse al normalizar. |
| RepeaterAdminExecutor._execute_batch_telemetry_query | 179 | 64 | Estado del lote y datos recibidos explícitos. |

Son candidatos de mantenibilidad, no evidencia de CPU excesiva. En JS merecen
perfilado las lecturas IndexedDB getAll/cursors completos y reconstrucción de
200 filas Sniffer por evento. Definir dataset virtual, volumen de mensajes,
clientes y objetivo de latencia antes de comparar índices/DOM incremental.
No inventar políticas de retención, límites de cola o mínimos RF unilateralmente.

Lectura complementaria del principal: LinkQualityEngine limita NaN/inf en señal
y EMA; su LQI es una **estimación heurística**, no calidad física medida ni
garantía de ruta óptima. Revisar validación de alpha/hops/timestamps si se abre
esa API a valores externos; no se reprodujo fallo de ese flujo productivo.
SharedUtils distingue saneamiento de claves de secretos frente a contenido
contextual, precisamente la limitación de WEB-01. Diagnostics usa deque
acotado y callback de logs; Preflight emplea sockets síncronos y se debe evaluar
su contexto de ejecución, descrito en el complemento del anexo de integración.

## Contradicciones y riesgos no convertidos en defectos confirmados

1. **Autoridad de capas:** AUDIT_REPORT_LAYER_BY_LAYER.md asigna responsabilidades
   distintas de ARCHITECTURE.md y contiene afirmaciones históricas de optimalidad/
   verificación. Se conserva como historial; esta auditoría no hereda esas garantías.
2. **Privacidad por sink:** REST config/evento CLI redactados no implican MQTT y
   capturas redactados (PI-02, WEB-01). AGENT_ACTIVITY_REPORT declara capturas
   protegidas, contradicción con el GET actual demostrado.
3. **Hecho vs default/host:** RUNTIME-04, PI-01/09/10 y WEB-09 muestran datos
   sugeridos, del host o del solicitante presentados como estado del dispositivo.
4. **Éxito vs despacho:** PI-05/12, RUNTIME-05 y WEB-05/07 requieren vocabulario
   común accepted/dispatched/confirmed/partial/failed/unknown sin inferirlo del texto.
5. **Paridad de ingresos:** endurecer REST no protege MQTT/CLI si sus conversiones
   preceden al executor (PI-03/04). Las unidades y precisión deben coincidir en UI,
   terminal, cache y wire (PI-07/11/13, RUNTIME-06).
6. **QA y rendimiento:** Q-01/02/03 contradicen afirmaciones de alcance/métrica/
   memoria; chart_engine no acredita WCAG completo por su comentario. Lint/tipos,
   complejidad aproximada y cobertura no prueban seguridad o optimalidad universal.

Los anexos separan otras hipótesis: durabilidad fsync/corte eléctrico; threads
de disco en shutdown; memoria bajo carga prolongada; reloj watchdog; snapshots
SDK cacheados; load_history repetido; logs query URL-encoded; WS fragmentado;
orígenes LAN; interpolaciones de mapa; retención IndexedDB; MQTT TLS;
cooldown RAM; carrera de admisión desde otro hilo; instalación parcial;
actualización destructiva ante fallo de copia; servicio root/KillMode.
No se ejecutaron instaladores ni se simuló fallo de alimentación o explotación
RF. Cada propuesta requiere su escenario y requisito antes de llamarla defecto.

Controles descartados: el import HTTP de repetidor conocido ya rechaza con 400
y no escribe, incluso si cliente omite rol. Traceroute sí retorna los tres campos
consumidos por el mapa. Disconnect resuelve el waiter raw con False. Los fallos
de fixture/bas temp y permisos Chromium se registran como entorno, no producto.

## Plan de corrección con criterios de aceptación

| Etapa | Trabajo | Criterio de cierre |
|---|---|---|
| 1. Privacidad | WEB-01, PI-02: límites privados/públicos, auth de capturas, redacción contextual uniforme. | Secreto sintético llega al waiter, ausente en todos los sinks públicos y exports; accesos sin clave según política explícita. |
| 2. Fuente de verdad | RUNTIME-04/06, PI-01/07/08/09/10/11/13, WEB-09 y Q-05. | Reload/SELF_INFO conservan desconocidos y valores efectivos; unidades/layout/RTC coinciden con fuente oficial. |
| 3. Operaciones confirmadas | RUNTIME-05, PI-03/04/05/06/12, WEB-02/03/04. | Ruta inválida cero escrituras; roles válidos; prevalidación completa; respuesta incorrecta nunca confirma; error/partial fiables en cada ingreso. |
| 4. Estado y carreras | WEB-05/06/07/08/10/11, RUNTIME-01. | HTTP/WS y respuestas invertidas no pierden estado, mezclan feeds ni resucitan clear; ACK no degrada delivery; rutas actualizadas desde SDK. |
| 5. Ownership y límites | RUNTIME-02/03/07, Q-06. | Backlog acotado con política acordada; vigencia ACK y orden estables; shutdown drena/cancela propios; demo completamente aislada. |
| 6. Deuda y evidencias | Q-01/02/03/04, candidatos de desuso, duplicación, instaladores y documentación. | Sólo retirar símbolos con contrato decidido y callers revisados; métricas con alcance real; benchmarks antes/después y documentación coherente. |

Dependencias: separar serialización antes de migrar archivos; conservar datos
desconocidos antes de ajustar UI; centralizar validadores antes de añadir alias;
cerrar estados de chat antes de optimizar IndexedDB/DOM. Para archivos históricos
no se puede inferir qué default fue una observación real: diseñar migración que
exponga incertidumbre y conserve copia, en vez de fabricar una lectura.

Después de cada corrección, convertir su réplica en regresión del resultado
correcto dentro de `tests/test_*`, mantener controles de roles/secretos/ACK y
ejecutar los checks de contrato y navegador pertinentes. Al final ejecutar la
suite mantenida, cobertura, mypy strict, Ruff y documentación, sin bajar
expectativas para ocultar comportamiento defectuoso.

Checklist LoRa para la fase de corrección: (1) corregir parsing/render/persistencia
no requiere paquetes adicionales; la lectura local GET_CONTACT es Companion,
no solicitud RF remota; (2) no introducir reenvíos, polling o respuestas que
formen feedback; (3) no recrear schedulers/cooldowns al guardar y conservar
timestamp persistente si se requiere continuidad. Cualquier capacidad, TTL,
retención o intervalo nuevo se acuerda con el usuario antes de implementarlo.

## Reproducción y comprobaciones

Desde la raíz, con el entorno instalado del proyecto:

```powershell
.venv/Scripts/python.exe scripts/audit_layers_inventory.py --output docs/audits/layers-2026-10-04/inventory.json --csv docs/audits/layers-2026-10-04/methods.csv
.venv/Scripts/python.exe -m pytest tests/audit_layer_runtime_2026_10_04.py tests/audit_layer_quality_2026_10_04.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/layers-audit-replay-tmp
.venv/Scripts/python.exe tests/audit_layer_protocol_2026_10_04.py
.venv/Scripts/python.exe -m pytest tests/audit_layer_web_2026_10_04.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/layers-web-replay-tmp
.venv/Scripts/python.exe -m mypy --strict src
.venv/Scripts/python.exe -m ruff check src tests scripts
.venv/Scripts/python.exe scripts/validate_project_docs.py
```

En entorno con restricción de subprocess, Chromium requiere ejecución autorizada
fuera de ese sandbox; no cambiar fixtures para usar un navegador/servidor de una
estación real. Crear previamente el padre de cualquier `--basetemp` anidado.
Las versiones, matriz y limitaciones definitivas se registran debajo y en
[verification.json](audits/layers-2026-10-04/verification.json).

### Matriz final

Entorno: Windows 11 AMD64, Python 3.12.14; pytest 9.1.1, pytest-cov 7.1.0,
Playwright 1.62.0, mypy 2.3.1, Ruff 0.16.3, Bandit 1.9.4. Se reutilizó el
entorno instalado; no se instalaron dependencias de producción ni se actualizó
una referencia oficial.

| Comprobación | Resultado actual | Alcance y limitaciones |
|---|---|---|
| Suite mantenida `pytest tests` | **963 passed, 1 skipped**, 0 errores/fallos, 433.27 s | Fixtures virtuales y directorios temporales. Skip de symlink cartográfico: Windows no permite crearlo en este entorno. |
| Cobertura | **70.16 %** de líneas: 10229/14579 | XML de esta ejecución; no se midió cobertura de ramas. Las áreas sin cubrir impiden concluir ausencia de errores. |
| Reproducciones runtime | 12 passed, 1.25 s | Siete problemas y controles, incluidos índice redundante y disconnect. |
| Reproducciones web | 13 passed | Once problemas; potencia con dos casos y control positivo de roles. Chromium y servidor virtual propios. |
| Integración | 13 reproducciones, exit 0 | SDK/MQTT mocks, dispatch real; no transporte MQTT end-to-end ni RF. |
| Calidad | 6 passed, 0.20 s | Evidencias de herramientas, estadística, memoria sintética y paths de demo. |
| Simulador complementario | 2 problemas reproducidos, exit 0; 0 tareas al cerrar | Sin connect, escena, broker o radio; script completo en el anexo. |
| mypy `--strict src` | Correcto, **60 archivos** | Tipado estático; no ejecución sobre Python 3.10. |
| Ruff `check src tests scripts` | Correcto | Incluye los cuatro harness y el script nuevo; no acredita contratos de runtime. |
| Gramática/inventario | 0 errores, 113 clases/946 funciones confirmadas por ast.walk independiente | Gramática objetivo 3.10; sin imports de producción. |
| Documentación | **81 archivos, 0 incidencias** | Validator de estructura/enlaces del proyecto; no verificación semántica automática. |
| Bandit `-r src -ll -ii -f json` | Exit 1, una alerta media B104, 0 errores de análisis | Línea diagnostics.py:263 contiene default TCP_HOST para preflight; no bind en ese punto. Revisión descarta ese hit como prueba de listener inseguro. No descarta riesgos de exposición del servicio ni las fugas WEB-01/PI-02, no detectadas por el scanner. |

La suite mantenida y los harness tienen objetivos distintos: **31 casos pytest
documentales + 13 observaciones del harness de integración + 2 réplicas del
simulador** no se suman al denominador de la suite mantenida. Sus expectativas
deliberadamente reproducen errores; no prueban que estén corregidos.

Ejecución completa final preservada:

```powershell
New-Item -ItemType Directory -Force tests/artifacts/layers-2026-10-04 | Out-Null
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-tests --timeout 900 --report tests/artifacts/layers-2026-10-04/maintained-verified.json -- tests --junitxml=tests/artifacts/layers-2026-10-04/maintained-verified.xml --cov-report=xml:tests/artifacts/layers-2026-10-04/coverage-verified.xml --cov-report=term:skip-covered -q -p no:cacheprovider --basetemp tests/artifacts/layers-maintained-verified-tmp
```

Intentos previos conservados y **no atribuidos al producto**:

- Primero: 614 passed/1 skipped/349 errores de fixture, padre inexistente de un
  basetemp anidado (WinError 3). Se corrigió el directorio de QA, no el código.
- Segundo: 851 passed/1 skipped/112 errores de arranque Chromium por permisos
  subprocess del sandbox. La ejecución final autorizada fuera del sandbox usa
  los mismos fixtures virtuales y dio el resultado completo anterior.
- Las incidencias iniciales de harness propias (fixture/orden de imports)
  se repararon sin cambios productivos y no entran en el registro de defectos.

## Estado de entrega

Entregados informe principal, cuatro anexos, inventario CSV/JSON, evidencias
y cuatro harness explícitos más el generador read-only. Producción, referencias,
instaladores y datos operativos permanecen sin cambios. El índice documental
enlaza esta auditoría; las auditorías históricas se conservan.

Queda trabajo de **corrección** de los hallazgos y validación de las hipótesis
separadas según el plan anterior. Esta entrega cumple el pedido de auditar,
replicar y documentar; no declara resueltos los problemas ni optimizadas todas
las clases por el resultado de lint o la suite.
