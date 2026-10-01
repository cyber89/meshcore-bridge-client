# Auditoría de compatibilidad y actualización — 2026-09-30

Solicitud: comprobar secuencialmente `src/serial/`, `src/admin/` y el resto de
módulos Python de `src/`, ejecutar todas las pruebas, reproducir/corregir fallos,
publicar en GitHub y actualizar la estación autorizada por MCP SSH.

## Autoridad y método

Base Git inicial: `dbd185ef64129ee980deb6994d13b59d08d46b62`, rama `main`.
El checkout contiene migraciones QA y otros cambios anteriores no publicados.
Se revisan e integran únicamente las dependencias necesarias de la suite y los
archivos dentro del alcance; el resto se conserva separado. Las referencias no
se modifican. Credenciales SSH y datos operativos no se incluyen en Git.

| Referencia | Revisión local usada |
| --- | --- |
| Firmware | `d92964352441e53b93e8667b802e04f6e072b39e`, companion-v1.17.1 |
| SDK | `c487efbe187f4b000020afdfc0349c4cdf503c5a`, v2.3.8 |
| CLI | `0856c723cdea3438811c62c190bbec3059e2dc48` |

SDK instalado: MeshCore 2.3.8. Sus 19 módulos Python coinciden con la referencia
normalizando saltos de línea, según el agente de protocolo. Entorno local Python
3.12.14; la compatibilidad sintáctica 3.10 y la ejecución 3.10 son evidencias
distintas. Pruebas con temporales, mocks/radio virtual y servicios loopback propios.

Una prueba aprobada acredita su escenario. No permite afirmar compatibilidad
100% con todo firmware, hardware, transporte o versión futura. El framing raw del
bridge es un formato propio en memoria, no un transporte Companion alternativo.
Las limitaciones de hardware y proxy concurrente se registran expresamente.

## Línea base

| Comprobación inicial | Resultado |
| --- | --- |
| Backend | 353 pruebas aprobadas. |
| Navegador | 17 pruebas aprobadas con permisos de ejecución fuera del sandbox. |
| Total suite mantenida | 370 aprobadas; cero fallos de expectativas y cero skips. |
| Cobertura backend inicial | 60,6%: 7229 de 11930 líneas; no cobertura final. |
| Mypy strict | Aprobado, 58 archivos fuente. |
| Ruff | Dos imports desordenados en test_skill_helpers reproducidos y corregidos. |
| Documentación | 47 archivos, cero incidencias estructurales. |

La primera ejecución falló por permisos del directorio temporal de Windows;
la segunda pasó backend pero Chromium encontró `spawn EPERM`. Se conservaron
ambos resultados y se repitió navegador con permisos adecuados, sin cambiar
expectativas. Evidencia nueva: `tests/artifacts/audit-20260930-baseline/`.
Esos artefactos se mantienen localmente ignorados; este documento conserva el resumen.

## Fase 1 — Serial

Revisión de `__init__.py`, `serial_base.py`, `sdk_adapter.py`, `raw_framing.py`
y `watchdog.py`, con las skills de inspección oficial, tipado Python y concurrencia.
Reproducciones anteriores al arreglo: 18 fallos iniciales y lotes adicionales
de 2, 4, 2 y 2 fallos. Nueva suite: 32 casos. Verificación combinada de serie,
watchdog y sanitización: **88 aprobados en 1,28 s**, Ruff y mypy strict de cinco
archivos aprobados. No se modificó el SDK ni las referencias.

Cambios en `sdk_adapter.py`, `raw_framing.py`, `watchdog.py`; base/exportaciones
inspeccionadas sin cambios en esta fase. Corregidos identidad DM dict/local/rol,
SELF_INFO como payload, probes falsamente vivos, TCP desconectado, limpieza tras
init fallido, cachés pese rechazo SDK, falta de respuesta TX, PSK derivada de
`#nombre`, truncación UTF-8 y contacto reescrito/claves completadas con ceros.
Se exige identidad real de 32 bytes para añadir un contacto, y se conservan
prefijos que el SDK resuelve contra contactos existentes.

Límites oficiales de texto: 160 bytes DM; canal descuenta el nombre del remitente
y `: `; nombres de canal 31 bytes más NUL. NUL en texto se rechaza. Gateway
`run_sdk_command` y wrapper de `commands.send` sobre la instancia propia serializan
respuestas locales incluso en auto-fetch del SDK, con cancelación y reinstalación
probadas. El watchdog respeta su máximo finito configurado; 0 sigue indefinido.

Dos pruebas usan el serializador SDK instalado y contrastan opcode, timestamp LE,
prefijo de seis bytes, texto UTF-8 y ACK normalizado. El proxy, capacidad de canales y callbacks desde hilos se corrigieron y verificaron
en la fase3; la evidencia queda limitada a escenarios finitos. BLE no implementado. La evidencia no prueba recepción RF por otro nodo.

## Herramienta de inspección de referencias

El inspector se reparó como herramienta de esta auditoría: su entrada por archivo
individual llamaba un método inexistente y el regex de `#define` contaba líneas
en blanco previas. Tres regresiones fallaron antes y pasaron después (JUnit en
`tests/artifacts/audit-20260930-inspector-*.xml`). La salida declara que usa regex
y que la suma de tamaños de campos no acredita ABI, padding, endianness ni layout
wire; la fuente/parser oficial sigue siendo la autoridad. No se modificaron
referencias.

## Fase 2 — Administración

Se revisaron los seis módulos, incluido el gateway nuevo `sdk_commands.py`.
33 casos nuevos pasan; conjunto dirigido de administración/sanitización: 102
aprobados en 13.24 s, seguido de 33/33 tras la última normalización de batería.
Ruff y mypy estricto de los seis módulos aprobados. Reproducciones anteriores
conservadas en JUnit y `scratch/admin_phase2_reproduction_summary.json`.

Las escrituras sólo actualizan caché tras confirmación; ERROR/None no anuncian
éxito. Batería usa `level` oficial; tuning usa `get_tuning`; `max_hops` de autoadd
se rechaza porque la API oficial no lo ofrece. CLI preserva mayúsculas del nombre,
propaga errores y muestra datos desconocidos sin inventar mediciones. El reboot
es una orden despachada sin respuesta, no una confirmación de reinicio.

Administración remota utiliza CLI cifrado y login binario confirmado, respeta el
cooldown existente y no cae a chat ni emite otra consulta tras un timeout binario.
Verifica identidad/permisos del login cuando aparecen, rechaza claves fabricadas
y nodos locales/clientes. Ping Hop 0 conserva flags y restaura la ruta del contacto
en `finally`; broadcasts se esperan en el ciclo de la petición. Traceroute espera
TRACE_DATA correlacionado, conserva hashes de un byte y no fabrica ruta/RTT tras
fallo. Los hashes de ruta de tres bytes no se convierten a otro tamaño de TRACE.

Límites: el SDK oficial `send_login_sync` se suscribe después de enviar; validar
su retorno no elimina esa carrera upstream. Respuestas antiguas sin identidad ni
permiso no acreditan esos campos. Caché válida retenida no garantiza frescura.
La integración de wrappers en `admin_handler.py` se revisó en la fase3.

## Fase 3 — Resto de src

Se inventarían los **59 módulos Python** en la [matriz por fichero](SOURCE_COMPATIBILITY_MATRIX_2026-10-01.json), con hash, autoridad, revisión y límites. La fase incluye19regresiones de ciclo de vida/TCP,18de núcleo,42de dominio,16de MQTT,2de persistencia de nodos,16de simulador y contratos HTTP/WebSocket/TCP. Los conteos dirigidos se solapan; no se suman como si fueran pruebas distintas.

Corregidos: clasificación por tipo oficial y resolución sin claves fabricadas/colisiones; ACK de cuatro bytes y endian LE para entradas enteras; secretos estructurados y PRIVATE_KEY fuera de sinks públicos; LPP gyro y corte seguro ante tipos desconocidos; tamaños exactos del formato custom. Persistencia de nodos conserva cambios durante escritura concurrente y elimina correctamente nodos. El airtime se guarda mediante snapshots y escritor fuera del loop; shutdown espera el último guardado, con la misma política existente.

MQTT conserva action/params/request_id, rechaza JSON estructurado inválido sin fallback a texto RF y resuelve prefijos multi-segmento. Publicación Paho comprueba rc; salud exige serie y MQTT conectados. API mutaciones confirma transceptor antes de cache, rechaza texto/nombre/clave inválidos y no evita la cola TX ante un fallo. WebSocket valida máscara, RSV y control frames; export de secretos mantiene autenticación; mapas usan contención de rutas y lock de lectura. Logs toman IP del socket y omiten credenciales conocidas. CSV neutraliza fórmulas sin mutar el paquete almacenado.

Inicio/cierre serializado, rollback de startup fallido/cancelado, preflight fuera del loop, tareas desde threads owned y canceladas al cierre, excepciones consumidas y logs de fallo sin feedback WebSocket. El logger SDK no permite DEBUG con hexdumps de secretos. Proxy Companion mantiene un dueño por respuesta, pushes difundidos, GET_CONTACTS hasta END, lock común con SDK/auto-fetch; ERROR no se confirma ni se duplica. Chat raw usa la cola TX existente y solicitudes canceladas no llegan a transmitir.

Métricas no finitas se normalizan a null/None; latitud y longitud respetan sus rangos y aceptan ecuador/meridiano, conservando(0,0)como ausencia de GPS del advert. Deduplicación usa reloj monotónico con la misma ventana configurada. Se reprodujeron23fallos de29casos nuevos y el gate afectado114/114 aprobó. El constructor SDK fallido ya no selecciona el parser raw en memoria como si fuera hardware; una regresión falló antes y pasó después.

El simulador distingue roles, desconexión, ACK/dispatch y serializa su subconjunto con el lector SDK real; conserva su naturaleza sintética. El SDK consulta la capacidad anunciada de canales (fallback16 cuando firmware antiguo no la anuncia), admite slots>15 y callbacks de threads en tareas propias.

Reproducciones nuevas están conservadas antes de los parches en JUnit locales. La integración intermedia terminó557pass/15fail/1skip y luego615pass/1fail/1skip; sus fallos y fixtures corregidas se mantienen como historia, no como resultados finales. La suite final del árbol seleccionado de publicación aprobó **661pruebas,1skip,0fallos** en83.29s, con17casos de navegador. Mypy estricto59archivos, Ruff y documentación44/0 aprobados. Cobertura: **67.07%**, 8460/12613líneas. [Resultado machine-readable](QA_RESULTS_2026-10-01.json). Bandit src -ll -ii sin hallazgos a esos umbrales; no equivale a seguridad completa. Se comprobó ausencia de mensajes de tareas sin consumir.

Limitaciones materiales: no BLE, no transporte UART físico para raw propio, no certificación universal RF, LPP extendido soportado parcialmente, LQI heurístico y PCAP custom. Cooldowns admin manuales están en memoria y se reinician con proceso; no se añadieron timers ni una política de persistencia nueva. SDK send_login_sync conserva su carrera upstream; respuestas antiguas sin identidad no acreditan correlación. La redacción de secretos es específica/heurística, no un detector universal. Python3.10 AST/mypy no sustituye ejecutar suite3.10.

## Impacto RF de las correcciones

1. **Airtime**: Las regresiones son virtuales. Las reparaciones deben reutilizar
   comandos/configuración existentes, rechazar envíos inválidos y evitar repetir
   contactos ya presentes. No se introducen sondeos RF ni nuevos timers.
2. **Spam/feedback**: Preservar guardas de origen local, roles de infraestructura,
   deduplicación y límites configurados. La serialización de respuestas no crea
   un retry adicional. Un límite finito existente debe respetarse sin cambiar su
   valor; límites de bytes se derivan del firmware, no de una política elegida.
3. **Guardado/rearme**: No elegir intervalos nuevos ni rearmar timestamps. Si una
   reparación exige cambiar la política RF o un intervalo, se consulta al usuario
   conforme a AGENTS.md. La actualización arranca el servicio ya configurado;
   la verificación posterior usa logs y snapshots HTTP, sin TX/ping/traceroute.

## MCP SSH y despliegue

MCP stdio local en [tools/ssh_mcp](../tools/ssh_mcp/README.md), separado del runtime
de producción. SDK MCP 1.30.0 y Paramiko 4.0.0 instalados exclusivamente en
`scratch/maintenance/ssh_mcp_runtime/` para esta tarea. La sesión MCP real lista
`ssh_host_key`, `ssh_execute` y `ssh_upload_file`; no requiere registro global.
La contraseña sólo se inyecta en memoria del proceso. Se fija el fingerprint
negociado antes de autenticar; no existe known_hosts local previo para este host.

Host `192.168.0.242`: la unidad activa usa **`/opt/meshcore-bridge`**;
`/opt/meshcore-brdige/` era un error de escritura. Se desplegó, tras publicar,
el commit **36539f60c64c6a292efa9f595c3fe7011e7a3c5e** mediante archivo verificado
SHA256. Los **86 archivos** instalados coinciden con el archivo publicado.
Se conserva Python3.13.5/SDK2.3.8, unidad, venv, `.env`, datos, mapas, logs y broker;
no se ejecutó el instalador raíz. Backup privado:
`/opt/meshcore-backup-20261001T215535Z-36539f60c64c`, permisos0700 y copia de
configuración0600; contenido de configuración y unidad comprobados sin cambios.

Comprobación a850segundos: PID62404 estable, active/running, reinicios0,
serial y MQTT conectados, salud healthy, error_count0, GET `/api/status`,
`/api/health` y `/`200. RX32; TX1 es actividad operativa existente, no prueba
RF iniciada por mantenimiento. Linux ejecutó la regresión de contención de
symlink omitida en Windows usando el módulo desplegado y almacenamiento temporal:
aprobada. No se ejecutó la suite completa contra datos operativos.

Se revisaron cinco logs y las últimas5000líneas del journal antes de actualizar.
Los históricos contienen529tracebacks en error.log y440 en el log principal
(incluyen duplicados entre sinks y versiones anteriores). Destacan el campo
NodeContactUpdate.out_path_hash_mode, atributos de contextos antiguos, nombres
no definidos y mutación de dataclass frozen; se contrastaron con código y
regresiones actuales. No se atribuyen todos los históricos a una única versión.

Tras el cambio, hasta22:09:49UTC, no se observaron tracebacks, tareas sin consumir
ni entradas de nivel ERROR. Hay un WARNING: una solicitud operativa broadcast
de196bytes fue rechazada por superar el límite oficial160bytes. El marcador
TX-ERROR de ese mensaje no es su nivel de log. La regresión virtual verifica
que los mensajes demasiado largos no llegan al comando SDK. Se mantiene el límite
oficial; el emisor operativo debe reducir el contenido.

[Evidencia de despliegue y logs](DEPLOYMENT_VERIFICATION_2026-10-01.json).
Estos resultados acreditan el alcance comprobado, no compatibilidad universal100%.

## Verificación adicional en GitHub CI

La primera publicación aprobó Ruff, mypy, documentación, Bandit y scripts de
integridad, REST y asyncio. Linux Python3.10 y3.12 aprobaron661casos cada uno
y detectaron un fallo móvil390×844 en `test_playwright_responsive_layout`.
El runner instaló SDK2.3.14 y Playwright1.63.0. La prueba local Windows no
reprodujo ese desbordamiento; observó una transición activa del sidebar después
de retirar su clase. No se atribuye causalidad al cambio de versión sin prueba.

La prueba de seguimiento espera fuentes listas, ausencia de animación y panel
fuera del viewport antes de medir; conserva la exigencia exacta de ausencia de
desbordamiento y añade diagnóstico geométrico para identificar un defecto real
si persiste. La nueva ejecución Linux determinará el resultado; estos cambios
son de pruebas y documentación y no alteran el código desplegado.

Gate local de seguimiento del árbol seleccionado: **662aprobadas,1skipWindows,0fallos**, con18casos de navegador;111.59s. Cobertura **67.11%** (8465/12613líneas), mypy59/Ruff/documentación44/0 aprobados. El skip de symlink fue aprobado separado enLinux con almacenamiento temporal. Fuente de producción intacta.
