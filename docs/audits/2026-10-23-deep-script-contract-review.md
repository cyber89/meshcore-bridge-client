# Segunda revisión: scripts y contratos funcionales — 2026-10-23

## Alcance y criterio de evidencia

Base revisada: `bbeccd5b63cba4b4d8e8404efe00d987bc8b4bef`, rama `main`.
Solicitud: buscar más profundamente errores omitidos en la primera pasada.
Se contrastaron llamadores, propiedad de locks, validación, persistencia,
resolución de identidades, códigos de salida y rutas de instalación.

Esta entrega identifica **15 hallazgos nuevos: 3 P1, 10 P2 y 2 P3**. No repite
los pendientes ya recogidos en la [primera revisión](2026-10-23-documentation-scripts-review.md):
fallback/permisos del password file de Mosquitto, recuperación de credenciales,
deduplicación administrativa incompleta, empaquetado mínimo y capacidades ausentes
del catálogo OpenAPI.

La evidencia es **trazado estático del código**, con condiciones de activación
explícitas. No son reproducciones dinámicas ni resultados de pruebas. P1 indica
riesgo alto de seguridad/disponibilidad; P2, error funcional; P3, limitación de una
herramienta de verificación. Las prioridades expresan impacto y condiciones, no
mediciones de frecuencia en una estación real.

No se ejecutaron suites, harnesses ad hoc, navegador, servicios, instaladores,
generadores de diagramas/mapas, exportadores contra una estación, RF ni broker.
No se modificó código de producción ni se leyeron configuración activa, logs o
datos operativos. Los archivos locales ajenos sin seguimiento quedan excluidos.
La tarea distribuyó lecturas de instalación, contratos y herramientas entre tres
agentes; el principal contrastó los hallazgos y las fuentes antes de integrarlos.

## Hallazgos de prioridad alta

### D01 — P1: sincronizar canales se autobloquea

- **Activación:** `POST /api/channels/sync` con el servidor en funcionamiento.
- **Traza:** [ChannelsController](../../src/web/controllers/channels_controller.py),
  líneas 72–73 y 93–99, adquiere el lock que pertenece al servicio. `_sync_channels`
  llama a `_sync_from_serial` (134, 139), que invoca
  [ChannelService.sync_from_radio](../../src/application/channels.py), línea 192:
  vuelve a adquirir **el mismo** `asyncio.Lock` antes de consultar la radio.
- **Consecuencia:** la petición espera un lock que ella misma retiene. Las demás
  lecturas/ediciones de canales también esperan mientras no se cancele esa tarea.
  El bloqueo no depende de latencia de radio ni de una configuración particular.
- **Corrección propuesta:** asignar una única capa propietaria del lock y evitar
  llamar desde una sección bloqueada a otra API que adquiere ese mismo lock.

### D02 — P1: la instalación Linux puede exponer la contraseña MQTT en `.env`

- **Activación:** instalación inicial con directorio nuevo, plantilla normal del
  checkout y `umask 022`.
- **Traza:** [install.sh](../../install.sh), 419 y 453–456, crea el directorio,
  copia la plantilla y escribe la contraseña generada. La plantilla tiene modo Git
  `100644`. La línea 475 aplica `chown`, pero la rama no establece `umask`
  restringido ni `chmod 600` sobre `.env`.
- **Consecuencia:** en esas condiciones `.env` queda `0644` bajo un directorio
  recorrible por otros usuarios locales. Pueden leer la credencial del servicio
  MQTT, cuya ACL del propio instalador permite publicar órdenes del bridge. Este
  hallazgo no afirma cuáles son los permisos de una instalación operativa actual.
- **Corrección propuesta:** crear el archivo con modo restringido y comprobar
  explícitamente propietario/permisos antes de insertar credenciales o arrancar.
  Es un problema distinto del permiso del password file del broker ya detectado.

### D03 — P1: repetir la instalación normal puede sustituir una estación activa sin rollback

- **Activación:** ejecutar `sudo bash install.sh` desde otro checkout sobre un
  destino existente y un servicio activo, sin `--update`.
- **Traza:** [install.sh](../../install.sh), 111–118, rechaza el origen dentro del
  destino, pero admite otro checkout aunque ya exista instalación. La rama normal
  elimina `src` en 437, copia archivos y modifica el venv en 468–471. El reinicio
  del servicio llega después, en 495; esta rama no lo detiene antes ni usa el
  staging transaccional de `--update`.
- **Consecuencia:** el proceso puede seguir vivo mientras se sustituyen sus
  archivos. Un fallo de copia, creación del entorno o pip deja código/entorno
  parcialmente actualizados sin restauración automática de esa rama.
- **Corrección propuesta:** rechazar una instalación normal sobre un destino ya
  instalado o conducirla al mismo flujo transaccional de actualización.

## Errores funcionales adicionales

### D04 — P2: un único puerto COM se convierte en `C`

- **Activación:** primera configuración Windows con exactamente un puerto, por
  ejemplo `COM3`, y sin `.env` anterior.
- **Traza:** [install.ps1](../../install.ps1), 276, asigna el resultado del pipeline
  sin `@(...)`: con un elemento recibe un string. La condición de 280 acepta su
  `Count=1`, pero la indexación de 282 obtiene el primer carácter. La línea 296
  escribe ese valor en `SERIAL_PORT`.
- **Consecuencia:** guarda `SERIAL_PORT=C`; la radio no se selecciona correctamente.
- **Corrección propuesta:** conservar un array al capturar el resultado ordenado.

### D05 — P2: un error de escritura deja los canales inutilizables aun después de recuperarse el disco

- **Activación:** falla un guardado de canales por permisos, disco lleno o error
  SQLite; posteriormente se recupera el almacenamiento.
- **Traza:** [ChannelService](../../src/application/channels.py), 117–125, conserva
  la tarea fallida y vuelve a esperarla antes de poder sustituirla. Además,
  [ChannelsController](../../src/web/controllers/channels_controller.py), 97–98,
  espera esa misma tarea antes de cualquier ruta, incluso `GET /api/channels`.
- **Consecuencia:** las siguientes operaciones vuelven a lanzar la excepción
  antigua; no llegan a intentar un nuevo guardado ni a devolver los canales.
- **Corrección propuesta:** observar y liberar tareas completadas en `finally`,
  conservando el error para quien solicitó la escritura y permitiendo reintentar.
  `ServicesManager._await_configuration_write` ya contiene un patrón comparable.

### D06 — P2: un preset inválido contamina la configuración compartida

- **Activación:** `POST /api/services/presets` con nombre/host válidos y, por
  ejemplo, `qos: 9` o `transport: "bogus"`.
- **Traza:** [ServicesController](../../src/web/controllers/services_controller.py),
  319–354, construye el preset y sustituye `cfg.custom_presets` antes de persistir
  en 356. [save_services_config](../../src/services_config.py), 434, valida y
  rechaza sus dominios, pero la mutación en memoria no se revierte.
- **Consecuencia:** falla la solicitud y queda un preset inválido dentro de la
  configuración compartida. Una recarga posterior aparentemente válida también
  falla porque [ServicesManager](../../src/services_manager.py), 377, valida el
  documento completo. No se afirma que el preset inválido llegue a SQLite.
- **Corrección propuesta:** validar una copia, persistirla y publicar el estado
  nuevo sólo al completar la operación; mapear datos inválidos a un error 4xx.

### D07 — P2: los DMs se persisten antes de resolver el destinatario canónico

- **Activación:** enviar `hola` a un CLIENT conocido por nombre (`Alice`) o por
  un prefijo hexadecimal único de 12 caracteres.
- **Traza:** [MessageService](../../src/application/messaging.py), 151–175 y 201,
  comprueba el rol pero conserva el destino literal. El
  [core](../../src/bridge_core.py), 1288–1289, persiste el mensaje antes de llamar
  al SDK en 1302; `_outgoing_chat`, 1400, conserva ese literal como `dm_target`.
  [StationDatabase](../../src/station_database.py), 257–259, construye
  `dm_<destino>` y sólo admite hexadecimal de 8–64 caracteres. La resolución real
  de nombres/prefijos llega después en [sdk_adapter.py](../../src/serial/sdk_adapter.py),
  1567, mediante `TargetResolver`.
- **Consecuencia:** `Alice` produce `Invalid conversation key` antes de RF. Un
  prefijo válido puede transmitir, pero se guarda bajo `dm_<prefijo>`, separado
  del feed con clave completa que abre la SPA. La consulta SQL filtra por igualdad
  de feed; ese mensaje saliente no aparece en la conversación canónica.
- **Corrección propuesta:** resolver y validar la clave completa antes de encolar,
  construir el feed y persistir. Mantener las guardas LOCAL/REPEATER.

### D08 — P2: el ledger MQTT ejecuta SQLite síncrono en el event loop

- **Activación:** llega una orden MQTT identificada mientras hay contención de BD
  o una operación de disco lenta.
- **Traza:** las corutinas de [mqtt_dispatcher.py](../../src/mqtt_dispatcher.py),
  268, 307, 337 y 383–405, llaman directamente a `reserve`, `mark_dispatching` y
  `record_result`. [CommandLedgerPolicy](../../src/application/command_policy.py),
  109 y métodos de actualización, ejecuta llamadas SQLite síncronas.
  [StationDatabase._connection](../../src/station_database.py), 106–113, adquiere
  un `threading.RLock` y abre conexiones con timeout de 30 segundos.
- **Consecuencia:** el hilo del loop espera el lock y/o SQLite; durante esa espera
  no atiende REST, WebSocket, RX ni temporizadores. No se ha medido un lag concreto.
  Es independiente del fallo de deduplicación documentado en la primera pasada.
- **Corrección propuesta:** ejecutar esas operaciones en workers con propiedad y
  cancelación definidas, conservando la reserva anterior al despacho RF.

### D09 — P2: readiness permanece falsa después de arrancar

- **Activación:** arranque normal seguido de `GET /api/capabilities`.
- **Traza:** [CapabilityRegistry](../../src/application/capabilities.py), 91–100,
  crea core con `started=False`, `operational=False`, estado `starting`. La
  búsqueda de productores en `src/` no encuentra una transición operativa de core;
  el arranque marca web y ServicesManager marca MQTT/Companion. Las líneas 294–319
  derivan salud/readiness del core no actualizado.
- **Consecuencia:** el snapshot informa `healthy=false`, `ready=false` y
  `core_ready=false` incluso con una estación que ha completado el arranque.
- **Corrección propuesta:** conectar el estado core con las transiciones reales
  de arranque, pérdida de radio y apagado, sin inferir disponibilidad de sólo
  la existencia del proceso.

### D10 — P2: REST trunca un índice fraccionario y puede transmitir por otro canal

- **Activación:** radio disponible, canal 1 válido y un `POST /api/tx` con
  `{"to":"broadcast","text":"hola","channel_index":1.9}`.
- **Traza:** [TxController](../../src/web/controllers/tx_controller.py), 45 y
  49–52, pasa el valor sin normalizar; [MessageService](../../src/application/messaging.py),
  117–123, excluye booleanos pero ejecuta `int(channel_idx)` sin rechazar floats.
  Los DTO OpenAPI no validan la solicitud en runtime.
- **Consecuencia:** acepta el valor como canal 1 en lugar de rechazarlo. El
  ingreso MQTT y el CRUD de canales sí rechazan este tipo de número.
- **Corrección propuesta:** validar tipo y representación entera antes de encolar
  RF; no usar la conversión truncante como validación de dominio.

### D11 — P2: exportar diagnósticos JSON puede anunciar éxito sin diagnósticos

- **Activación:** `export_logs.py --json --output <archivo>` con servidor ausente,
  autenticación rechazada o error HTTP.
- **Traza:** [export_logs.py](../../scripts/export_logs.py), 114–125, sustituye el
  resultado por un objeto `error`, lo guarda con mensaje de reporte guardado y
  retorna normalmente. La entrada en 144 no propaga un estado de fallo.
- **Consecuencia:** una automatización obtiene exit 0 y un archivo JSON, aunque no
  exportó el snapshot solicitado. No se ejecutó este comando contra una estación.
- **Corrección propuesta:** distinguir respuesta diagnóstica de error y devolver
  código no cero, sin presentar el objeto de error como exportación conseguida.

### D12 — P2: el inspector visual puede dar PASS a una página sin estación

- **Activación:** URL que devuelve una pantalla de login o una página HTTP 200
  sin componentes de la estación y sin excepciones JavaScript.
- **Traza:** [inspect_web.py](../../scripts/inspect_web.py), 121–133, recoge
  componentes, pero en 165–166 decide PASS sólo por excepciones y respuestas HTTP
  fallidas del contexto desktop. No incorpora los componentes ni los errores de
  consola al criterio. El contexto móvil no registra esos listeners y su error de
  navegación se silencia en 148–151.
- **Consecuencia:** puede devolver exit 0 y PASS de inspección funcional sin haber
  accedido a las vistas autenticadas ni validado móvil.
- **Corrección propuesta:** comprobar el estado esperado/autenticación y los
  componentes obligatorios; emitir resultados independientes para cada contexto.

### D13 — P2: el compilador de diagramas da éxito con fuentes requeridas ausentes

- **Activación:** motor Archify disponible y uno o varios JSON de `DIAGRAMS`
  ausentes.
- **Traza:** [build_diagrams.py](../../scripts/build_diagrams.py), 59–64, omite
  el archivo sin modificar `all_ok`. Las líneas 80–85 imprimen éxito y finalizan
  con código 0 si no hubo otro fallo, incluso si no se compiló ningún diagrama.
- **Consecuencia:** se conserva o publica un HTML anterior mientras la herramienta
  afirma haber compilado y verificado todos los diagramas.
- **Corrección propuesta:** fallar por cualquier entrada requerida ausente y
  comprobar el número de entregas realmente completadas.

## Limitaciones adicionales de herramientas

### D14 — P3: el chequeo de salud frontend no sirve como gate por su código de salida

[check_frontend_health.py](../../scripts/check_frontend_health.py), 64–95, imprime
excepciones, peticiones fallidas y elementos ausentes, pero termina normalmente.
Una inspección completada puede devolver exit 0 aun con errores recogidos. Además,
`requestfailed` no cubre por sí solo las respuestas HTTP 4xx/5xx. El script sirve
para lectura manual, pero no debe interpretarse su exit 0 como salud aprobada.
Si se pretende usar como gate, necesita resultado y criterio de fallo explícitos.

### D15 — P3: el gate de imports omite descendientes no alcanzables desde el paquete

El contrato de `pyproject.toml`, 168–176, declara como origen `src.application`.
[check_layer_contracts.py](../../scripts/check_layer_contracts.py), 49–66,
comienza sólo en ese nodo y sigue imports: no expande todos los módulos hijos del
paquete. Un módulo dentro de `src/application/` no importado por `__init__.py`
puede depender de `src.web` sin ser revisado desde ese origen.

En el checkout actual los módulos existentes se exportan desde el paquete; **no
se afirma una infracción presente de arquitectura**. Es una brecha del detector
para el contrato que pretende cubrir. Debe expandir los orígenes de paquete a sus
descendientes, además de conservar el recorrido transitivo.

## Verificación y límites de la entrega

Las fuentes y números de línea se cotejaron directamente con el commit de base.
Se inspeccionaron también los patrones equivalentes de limpieza de tareas y
validación para distinguir fallos de comportamientos intencionales.

Comandos ejecutados y salida contrastada tras integrar el informe:

| Comprobación | Resultado |
| --- | --- |
| `python scripts/validate_project_docs.py` | 131 documentos/skills; 0 incidencias estructurales o de enlaces locales. |
| `python scripts/check_layer_contracts.py` | 2 contratos; 0 infracciones detectadas. Conserva la limitación D15. |
| SHA-256 del manifest frontend frente a disco | 33 activos, 99 comparaciones de fuente/servido/gzip; 0 discrepancias. No acredita funcionamiento de la SPA. |
| `git diff --check` | 0 incidencias de espacios en el diff documental. |
| `git diff --name-only -- src scripts install.sh install.ps1` | Sin cambios de código o instaladores. |

Se descartaron hipótesis sin evidencia suficiente: por ejemplo, `_cleanup_task`
sí se inicializa en `MeshCoreBridge.__init__`, línea 149; no se registra un fallo
de rollback basado en una supuesta ausencia de ese atributo.

**No se han corregido estos fallos en esta entrega de investigación.** Las
reproducciones y regresiones aisladas quedan pendientes de una petición explícita
de pruebas. Una futura corrección que altere admisión o despacho RF deberá preservar
las restricciones de roles, airtime y reintentos y cumplir el checklist vigente.
El snapshot `PROJECT_INVENTORY.json` conserva la fecha de la primera revisión;
esta entrega no vuelve a inventariar archivos locales ajenos creados en paralelo.
