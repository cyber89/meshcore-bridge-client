# Explicación técnica del código de MeshCore Bridge

Guía conciliada el 2026-10-09 mediante lectura del código y actualizada el 2026-10-10 para el baseline CPython 3.14.8+ de [ADR 0015](adr/0015-python-3-14-8-baseline.md). No acredita medidas de rendimiento ni resultados de QA. Las decisiones de runtime y las verificaciones ejecutadas se registran por separado. Para fuentes, contratos y snapshots, consultar el [índice documental](README.md).

## 1. Entrada, configuración y composición

`meshcore_bridge.py` y `python -m src` arrancan el servicio. `config.py` carga `.env` sin sobrescribir variables ya presentes en el entorno, convierte valores y valida parámetros seleccionados. El puerto por defecto es `AUTO` en Windows y `/dev/ttyACM0` en otros sistemas; también se admite `tcp://host:port` en el adaptador SDK.

`src/bridge_core.py::MeshCoreBridge` compone registro de nodos, cola TX, adaptador serial, watchdog, MQTT, router RX, administración, salud, diagnósticos, Web y Companion TCP. Conserva métodos públicos de delegación para compatibilidad; el procesamiento especializado vive en los componentes descritos abajo.

## 2. Transporte de radio y formatos

`src/serial_driver.py` reexporta las clases de `src/serial/` como fachada de compatibilidad:

| Componente | Implementación | Función |
| --- | --- | --- |
| `BaseSerialAdapter` | `serial/serial_base.py` | Contrato de conexión, envío, heartbeat y acceso a hardware. |
| `MeshcoreSDKAdapter` | `serial/sdk_adapter.py` | Envuelve el SDK `meshcore`, conecta serial/TCP y normaliza callbacks del Companion. |
| `RawSerialFramingAdapter` | `serial/raw_framing.py` | Parser en memoria del framing propio y validación de longitud/CRC; actualmente no abre puerto físico ni transmite UART. |
| `SerialWatchdog` | `serial/watchdog.py` | Supervisa presencia y vivacidad del transceptor local, reconecta y aplica backoff. |
| `VirtualMeshAdapter` | `virtual_mesh_adapter.py` | Sustituye la radio por una simulación; no prueba compatibilidad de hardware real. |

El Companion oficial usa marcador `<` para comandos, `>` para respuestas y longitud `uint16` little-endian. `MeshcoreFrame`, en `protocol_types.py`, es un formato propio distinto: cabecera little-endian, CRC-16 big-endian y delimitadores `0xAA/0x55` con escape `0x1B` y XOR `0x20`. No se debe presentar este último como framing oficial de UART ni como layout universal del paquete RF. Véase [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md).

El servidor `MeshCoreCompanionServer` de `tcp_companion_server.py` recibe comandos de aplicaciones IP y reenvía payloads al Companion conectado; difunde las respuestas/eventos binarios hacia sus clientes. Esta función difiere de conectar el SDK a una radio Companion remota por `tcp://...`.

## 3. Recepción y normalización

`MeshCoreBridge.on_mesh_event` delega en `RxEventRouter.handle_event`. `src/routers/` separa anuncios/contactos, mensajes de canal, DM, repetidores, sistema y telemetría. Los contextos inyectados entregan dependencias compartidas a los handlers.

Los eventos normalizados preservan identidad, texto y, cuando están disponibles, RSSI, SNR y recorrido. El registro se actualiza con `NodeContactUpdate`/`PacketRecord`; LQI estima calidad de enlace. `PacketDeduplicator` evita procesar ecos dentro de su ventana de RAM. El decodificador CayenneLPP de `sensor_decoder.py` es nativo y usa la biblioteca estándar, sin dependencia de `pycayennelpp`.

MQTT publica en el stream unificado `meshcore/rx/all` y los tópicos de dominio: público, canales, DM, telemetría, nodos o logs RF. El subsistema Web recibe eventos para actualizar sus buffers y difundirlos por WebSocket.

La clasificación canónica deriva de `FirmwareAdvertType`: 0/1 CLIENT, 2 REPEATER, 3 ROOM, 4 SENSOR. Los repetidores son infraestructura administrativa; no contactos de chat. La clave local se excluye de contactos y de destinatarios de mensajería. Las invariantes se describen en [CONTEXT.md](../CONTEXT.md), y no equivalen a una certificación automática de cada ruta de entrada.

## 4. TX y administración

`MqttInboundDispatcher` procesa entradas `meshcore/tx`, `meshcore/admin/cmd` y `meshcore/admin/repeater/+/cmd`. REST llega a los controladores equivalentes. Los payloads TX admiten `to`/`target` y `channel_index`/`channel_idx`, y el dispatcher mantiene un fallback para texto plano.

`TargetResolver` resuelve claves públicas, prefijos y alias. La resolución de identidad no autoriza chat a repetidores ni al nodo local. El envío usa `TxRateLimiter`, `CustomTxQueue` y `AirtimeTracker`: prioridades, espaciado y estimación de airtime. Cuando la estimación alcanza el estado crítico, el worker puede descartar `LOW`; las prioridades superiores pueden continuar. La saturación de cola también puede producir rechazo o expulsión de elementos de baja prioridad.

El resultado de envío se publica en `meshcore/tx/status`, correlacionado mediante `request_id`. `sent` no prueba entrega a todos los receptores; el seguimiento de ACK de DM es un evento posterior y separado.

`AdminCommandHandler` delega en `src/admin/`: configuración local, repetidores, traceroute y CLI. Las operaciones remotas pueden consumir airtime; la comprobación de vivacidad del watchdog SDK consulta el transceptor local (`get_time`, `get_bat` o consulta de dispositivo), no es un ping RF periódico a cada vecino.

`RepeaterAdminExecutor` exige `LOGIN_SUCCESS` o confirmación explícita del handler de autenticación cuando se solicita login o prelogin con contraseña. `MSG_SENT`, ACK o texto genérico no acreditan autenticación. Si falta el método binario del SDK, falla sin enviar la contraseña como comando CLI/chat. Los lotes con contraseña abortan ante un login no confirmado; las consultas anónimas y sesiones existentes sin contraseña conservan su flujo.

## 5. Concurrencia y ciclo de vida

El trabajo principal vive en el event loop `asyncio`. Paho MQTT ejecuta su loop de red en un hilo; `AsyncBridgeMQTTClient._on_message` entrega callbacks con `loop.call_soon_threadsafe`. Las corrutinas se agendan desde el dispatcher en el loop. El componente MQTT inicia con `connect_async()`/`loop_start()`, backoff y LWT retained.

El apagado detiene tareas, servidor Web, conexiones Companion, watchdog, adaptador y MQTT, y guarda estado local. El estado MQTT offline se intenta publicar de forma explícita; el LWT cubre desconexiones inesperadas. No existe una cola MQTT durable SQLite que garantice recuperar todas las publicaciones después de una caída.

## 6. Persistencia real

| Estado | Ubicación | Alcance |
| --- | --- | --- |
| Registro de nodos | `NODE_REGISTRY_STORAGE_PATH`, normalmente `data/node_registry.json` | JSON mediante archivo temporal/reemplazo; escritura async disponible con `asyncio.to_thread`. |
| Canales | `CHANNELS_JSON_PATH`, normalmente `data/channels.json` | JSON local y sincronización con el Companion. |
| Contactos de radio | Memoria/flash del Companion | Sincronizados con el registro del host; capacidad depende del firmware. |
| Airtime estimado | `AIRTIME_HISTORY_FILE`, normalmente `data/airtime_history.json` | Historial JSON restaurado al arrancar; no mide directamente ocupación real del espectro. |
| Capturas RX/TX | `PacketBuffer` en RAM | Buffer circular; exporta JSON, CSV y PCAP. Se pierde al reiniciar. |
| Deduplicación, ACKs y buffers Web | RAM del proceso | No son un almacenamiento durable. |
| Chat del navegador | IndexedDB | Persistencia del cliente, independiente de otros navegadores y del servidor. |
| Logs del servicio | `LOG_DIR` y rutas configuradas | Archivos rotados; distintos del buffer Web de logs en RAM. |

No hay backend SQLite para nodos, mensajes o colas MQTT. `MapTileService` sí usa SQLite para lectura de mapas MBTiles; las referencias a otras bases SQLite en informes antiguos son históricas.

## 7. Web, MQTT y mantenimiento

`AsgiWebServer` es el servidor de producción basado en FastAPI / Uvicorn (ASGI) (`src/web/asgi_server.py`). `WebAPIRouter` normaliza alias y delega en controladores por dominio. La SPA organiza WebSocket, eventos y almacenamiento en `core/` y chat, nodos, repetidores, mapa, ajustes, analítica y sniffer en `modules/`.

El core selecciona ASGI y el servidor HTTP nativo está retirado; no hay selector de backend ni fallback automático. `asgi_routes.py` registra rutas con entrada `Request`, conserva el mapping JSON y llama una vez al dispatcher. Los controladores reciben datos de negocio y devuelven `tuple[int, dict[str, Any]]`; los DTO Pydantic son metadatos OpenAPI abiertos, sin validación de solicitudes en ejecución.

`asgi_docs.py` publica un visor propio offline en `/docs` y su alias `/redoc`, además de `/openapi.json`. No incorpora Swagger UI/ReDoc ni ejecuta acciones del catálogo. El esquema usa autenticación por `X-Api-Key` cuando hay clave configurada; el visor conserva esa clave sólo en memoria. La política Origin REST/WS de compatibilidad admite también loopback y LAN privada.

Las proyecciones REST de configuración de servicios enmascaran password/token en ambas listas de presets. Los logs y errores de los controladores revisados evitan valores de excepciones; el mapa escapa SNR/RSSI/RTT antes de insertar HTML. Son correcciones acotadas, no una certificación global de seguridad.

Los rechazos de configuración local por campos no soportados o baselines incompletos
conservan HTTP 422 antes de escribir; el rechazo remoto de `hop_limit`/`hops` conserva
HTTP 400 antes de login o comandos. Los ejecutores identifican esos casos con
`validation_reason` y `validation_fields`; `BaseController` reconstruye el detalle
usando motivos y nombres del esquema en listas cerradas. Los valores de la solicitud,
los nombres desconocidos y el texto de excepciones SDK no se reflejan en ese detalle.
Las respuestas parciales siguen informando sólo los cambios confirmados.

`BRIDGE_API_KEY` protege operaciones sensibles y handshake WebSocket cuando está configurada. Companion TCP tiene controles independientes (`COMPANION_ALLOWED_IPS`, `COMPANION_TOKEN`, límite de clientes). La política HTTP no autentica las conexiones MQTT; éstas dependen del broker.

El workflow n8n se describe en su [guía vigente](N8N_WORKFLOW_GUIDE.md). Las pruebas se ejecutan bajo autorización del usuario, con las herramientas del [protocolo de agentes](../AGENTS.md). Para cualquier cambio que emita RF, notifique automáticamente, cree timers o modifique radio, responder y documentar el checklist de impacto en malla antes de implementar.
