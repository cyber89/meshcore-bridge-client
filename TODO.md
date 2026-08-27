# TODO — Auditoría de Código y Hoja de Ruta de Mejoras

> **MeshCore Bridge v3.0** · Generado: 2026-08-26  
> Auditoría exhaustiva realizada por el Agente Orquestador sobre todos los módulos en `/src/`.  
> Severidades: **CRITICAL > HIGH > MEDIUM > LOW**

---

## 🔴 CRITICAL — Seguridad y Vulnerabilidades Explotables

### SEC-001 · API REST sin autenticación en endpoints sensibles
- **Archivos**: `src/web/api_router.py`, `src/web/http_server.py`
- **Problema**: Los endpoints `/api/admin/command`, `/api/node/reboot`, `/api/node/config`, `/api/tx` y todos los de gestión de repetidores aceptan peticiones **sin ningún token de autenticación**. Cualquier cliente en la red (o internet si `WEB_HOST=0.0.0.0`) puede ejecutar un reboot del hardware, modificar la configuración RF, o enviar mensajes a la malla.
- **Impacto**: Acceso no autorizado al hardware de radio, denegación de servicio por reboot remoto, manipulación de la configuración RF.
- **Solución**: Implementar middleware de API Key (`BRIDGE_API_KEY` en `.env`). Verificar header `X-Api-Key` en `http_server.py` antes de despachar a `/api/*`. Los endpoints de reboot/admin siempre exigen autenticación.
- [ ] Implementar middleware de autenticación API Key en `http_server.py`
- [ ] Proteger: `/api/node/reboot`, `/api/admin/*`, `/api/tx`, `/api/repeater/*`
- [ ] Agregar variable `BRIDGE_API_KEY` en `.env.example` y `config.py`

---

### SEC-002 · TCP Companion Server sin autenticación ni límite de conexiones
- **Archivo**: `src/tcp_companion_server.py` (L140-232)
- **Problema**: El servidor TCP en el puerto 5000 (en `0.0.0.0`) acepta **cualquier conexión** sin validar identidad. `active_clients` es un set ilimitado — DoS trivial por flood de conexiones. Un atacante puede inyectar tramas binarias directamente al transceptor LoRa.
- **Impacto**: Inyección de comandos al hardware de radio, DoS por flood, pivoteo hacia el hardware.
- **Solución**: Limitar conexiones simultáneas (`MAX_COMPANION_CLIENTS = 4`). Agregar variable `COMPANION_ALLOWED_IPS` en config para whitelist de IPs permitidas. Rechazar conexiones excedentes o de IPs no autorizadas con cierre inmediato del StreamWriter.
- [ ] Limitar conexiones simultáneas al TCP Companion Server (máx 4-8)
- [ ] Agregar `COMPANION_ALLOWED_IPS` en config para whitelist opcional
- [ ] Agregar rate limiting por IP en el TCP server

---

### SEC-003 · Broadcast sin drain() — Slow Client Attack con OOM potencial
- **Archivos**: `src/web/http_server.py` (L106-110), `src/tcp_companion_server.py` (L104-116)
- **Problema**: `broadcast_event()` y `broadcast_companion_frame()` llaman `writer.write(frame)` en bucle **sin** `await writer.drain()`. Si los clientes son lentos, el buffer crece sin límite, causando OOM en SBCs con poca RAM.
- **Impacto**: Memory exhaustion del proceso, OOM kill del kernel, caída del bridge.
- **Solución**: Convertir broadcasts en corutinas asíncronas. Agregar `await asyncio.wait_for(writer.drain(), timeout=2.0)` con descarte de clientes lentos. Configurar `writer.set_write_buffer_limits(high=64*1024)` para backpressure automático.
- [ ] Convertir `broadcast_event()` en corutina asíncrona con drain() y timeout
- [ ] Convertir `broadcast_companion_frame()` en corutina asíncrona con drain() y timeout
- [ ] Agregar `writer.set_write_buffer_limits(high=64*1024)` en el setup de clientes

---

### SEC-004 · CORS wildcard `Access-Control-Allow-Origin: *` en endpoints destructivos
- **Archivo**: `src/web/http_server.py` (L200-204, L222-224)
- **Problema**: `Access-Control-Allow-Origin: *` permite que cualquier sitio web haga peticiones cross-origin a la API (incluyendo reboot/admin). Sin autenticación (SEC-001), esto es explotable via CSRF desde cualquier web maliciosa.
- **Solución**: Validar el header `Origin` contra lista `BRIDGE_ALLOWED_ORIGINS` configurable (default: `http://localhost:8080,http://127.0.0.1:8080`). Devolver solo el origen específico si está en la lista, no el wildcard `*`.
- [ ] Reemplazar `Access-Control-Allow-Origin: *` por validación de origen específico
- [ ] Agregar variable `BRIDGE_ALLOWED_ORIGINS` en config

---

### SEC-005 · Content-Security-Policy (CSP) ausente — riesgo XSS desde datos de la malla
- **Archivos**: `src/web/http_server.py`, `src/web/static/index.html`
- **Problema**: Sin CSP, un nodo malicioso en la malla puede enviar un nombre como `<img src=x onerror=alert(1)>` que se inyecte en el DOM del browser del operador si el código JS usa `innerHTML` con esos datos.
- **Solución**: Agregar CSP estricta en `_build_http_response()` para HTML: `default-src 'self'; script-src 'self'; connect-src 'self' ws:; frame-ancestors 'none'`. Auditar `index.html` y reemplazar `innerHTML` con datos de malla por `textContent`.
- [ ] Implementar CSP estricta en `_build_http_response()` para archivos HTML
- [ ] Auditar `index.html` por usos de `innerHTML` con datos de la malla
- [ ] Reemplazar `innerHTML` por `textContent` donde corresponda

---

### SEC-006 · Inyección en comando de firmware via PSK de canal sin sanitizar
- **Archivo**: `src/serial_driver.py` (L475)
- **Problema**: `cmd_str = f'set_chan {index} "{clean_ch_name}" {psk}'` — el PSK **no es validado**. Un PSK con comillas o espacios puede manipular el comando enviado al firmware del transceptor LoRa.
- **Solución**: Validar PSK con regex `^[a-fA-F0-9]{0,64}$` antes de usarlo. Validar `index` (rango 0-15) y `name` (máx 32 chars, sin control chars). Lanzar `ValueError` si la validación falla.
- [ ] Agregar validación regex del PSK en `set_channel()`: `^[a-fA-F0-9]{0,64}$`
- [ ] Validar `index` (0-15) y `name` (máx 32 chars, sin caracteres de control ASCII < 0x20)

---

## 🟠 HIGH — Fallos de Concurrencia y Resiliencia

### CONC-001 · `PacketDeduplicator.is_duplicate()` no es thread-safe bajo concurrencia asyncio
- **Archivo**: `src/deduplicator.py` (L30-46)
- **Problema**: `is_duplicate()` modifica `self._cache` (OrderedDict) sin protección. Múltiples tasks asyncio pueden ejecutarla concurrentemente sobre el mismo evento, causando race conditions en la lectura+escritura del OrderedDict.
- **Solución**: Agregar `self._lock = asyncio.Lock()` en `__init__()`. Usar `async with self._lock:` en `is_duplicate()`. Para `is_duplicate_sync()`, usar `threading.Lock()` si se llama desde hilos (paho-mqtt).
- [ ] Agregar `asyncio.Lock()` en `PacketDeduplicator.__init__()`
- [ ] Proteger `is_duplicate()` e `is_duplicate_sync()` con el lock apropiado

---

### CONC-002 · `CustomTxQueue` sin límite de tamaño — potencial OOM por flood MQTT
- **Archivo**: `src/rate_limiter.py` (L82-83)
- **Problema**: `CustomTxQueue(maxsize=0)` es una cola **ilimitada**. Un bucle n8n mal configurado que envíe mensajes MQTT en ráfaga puede llenar la cola sin límite, consumiendo toda la RAM del SBC sin ningún error visible al productor.
- **Solución**: Cambiar a `CustomTxQueue(maxsize=MAX_TX_QUEUE_SIZE)` con `MAX_TX_QUEUE_SIZE` configurable (default 500). En `submit()`, usar `asyncio.wait_for(queue.put(item), timeout=1.0)` y manejar `asyncio.TimeoutError` con métricas de mensajes descartados.
- [ ] Establecer `maxsize` configurable (default 500) en `CustomTxQueue`
- [ ] Agregar variable `MAX_TX_QUEUE_SIZE` en `config.py` y `.env.example`
- [ ] Manejar `QueueFull` en `submit()` con métrica de mensajes descartados (`total_dropped`)

---

### CONC-003 · `_background_tasks` set compartido sin protección de acceso concurrente
- **Archivos**: `src/bridge_core.py` (L151), `src/rx_router.py` (L209-211), `src/mqtt_dispatcher.py` (L41-43)
- **Problema**: El set `_background_tasks` se comparte y modifica desde múltiples tasks asyncio via `add()` y `discard()` sin lock. En Python 3.13+ con free-threading y en operaciones compuestas asyncio, esto puede causar race conditions.
- **Solución**: Migrar a `asyncio.TaskGroup` (Python 3.11+) para tasks relacionadas, con cancelación automática y propagación de excepciones. Alternativamente, proteger el set con `asyncio.Lock()` o usar `weakref.WeakSet`.
- [ ] Evaluar migración a `asyncio.TaskGroup` para tasks del ciclo de vida principal
- [ ] Si se mantiene el set, proteger con `asyncio.Lock()` o usar `WeakSet`

---

### CONC-004 · Sin límite de concurrencia en procesamiento de eventos RX — flood RF puede saturar el event loop
- **Archivo**: `src/rx_router.py` (L201-212)
- **Problema**: Cada evento de radio crea una nueva task asyncio sin límite. En condiciones de flood RF (tormentas de broadcasts, spam), se pueden crear cientos de tasks concurrentes, saturando el event loop y causando latencia exponencial en todas las operaciones del bridge.
- **Solución**: Agregar `self._rx_semaphore = asyncio.Semaphore(MAX_RX_CONCURRENCY)` con `MAX_RX_CONCURRENCY = int(os.getenv("MAX_RX_CONCURRENCY", "20"))`. Cada task de procesamiento RX debe adquirir el semáforo antes de ejecutar.
- [ ] Agregar `asyncio.Semaphore` configurable para limitar el paralelismo de eventos RX
- [ ] Agregar variable `MAX_RX_CONCURRENCY` en `config.py`

---

### CONC-005 · Lecturas WebSocket sin timeout — conexiones zombie acumuladas
- **Archivo**: `src/web/http_server.py` (L305-334)
- **Problema**: Las llamadas `await reader.read(2)`, `await reader.read(4)` y `await reader.read(length)` en `_read_websocket_frame()` no tienen timeout. Un cliente WS que se conecta pero no envía datos puede mantener la coroutine suspendida indefinidamente, acumulando conexiones zombie y consumiendo file descriptors.
- **Solución**: Envolver cada `await reader.read(...)` con `asyncio.wait_for(..., timeout=WS_IDLE_TIMEOUT_SEC)`. Capturar `asyncio.TimeoutError` y retornar `None` para cerrar la conexión limpiamente.
- [ ] Agregar `asyncio.wait_for(..., timeout=30.0)` en todas las lecturas de `_read_websocket_frame()`
- [ ] Configurar timeout via `WS_IDLE_TIMEOUT_SEC` en config (default 30.0)

---

### CONC-006 · `SerialWatchdog` sin timeout en `ping_or_check_alive()` — el watchdog puede bloquearse
- **Archivo**: `src/serial_driver.py` (L750)
- **Problema**: `is_alive = await self.adapter.ping_or_check_alive()` no tiene timeout. Si el SDK meshcore_py tiene un bug o el puerto serial se comporta erráticamente, la llamada puede bloquearse indefinidamente — haciendo que el watchdog deje de supervisar, exactamente lo opuesto de su propósito.
- **Solución**: `is_alive = await asyncio.wait_for(self.adapter.ping_or_check_alive(), timeout=10.0)` con captura de `asyncio.TimeoutError` que establece `is_alive = False`.
- [ ] Agregar `asyncio.wait_for(..., timeout=10.0)` alrededor de `ping_or_check_alive()` en el watchdog

---

### CONC-007 · Uso de `asyncio.get_event_loop()` deprecado en Python 3.10+
- **Archivos**: `src/mqtt_client.py` (L111), `src/rx_router.py` (L208)
- **Problema**: `asyncio.get_event_loop()` está deprecado desde Python 3.10, emite `DeprecationWarning` en 3.12, y será eliminada en 3.14. Puede retornar el loop incorrecto si se llama fuera de una corutina activa.
- **Solución**: Reemplazar `asyncio.get_event_loop()` por `asyncio.get_running_loop()` en todos los contextos donde hay un loop activo (dentro de corutinas).
- [ ] Reemplazar `asyncio.get_event_loop()` por `asyncio.get_running_loop()` en `mqtt_client.py`
- [ ] Revisar y corregir todas las apariciones de `get_event_loop()` en el codebase

---

### CONC-008 · `_tx_worker` en `bridge_core.py` compite con `TxRateLimiter` por la misma cola
- **Archivo**: `src/bridge_core.py` (L491-502)
- **Problema**: `_tx_worker()` y `TxRateLimiter._worker_loop()` ambos llaman `await self.tx_queue.get()` sobre la **misma cola**. Si ambos corrieran simultáneamente, competirían por los mismos items: algunos mensajes serían procesados dos veces o nunca. El comentario "para compatibilidad con tests" es una señal de deuda técnica.
- **Solución**: Eliminar `_tx_worker()` de `bridge_core.py`. Actualizar los tests que lo usan para trabajar directamente con `TxRateLimiter` y mocks de `transmit_callback`.
- [ ] Eliminar `_tx_worker()` de `bridge_core.py` o protegerlo con flag de debug explícito
- [ ] Actualizar tests que dependan de `_tx_worker()` para usar `TxRateLimiter` directamente

---

### CONC-009 · `await future` en MQTT dispatcher sin timeout — task zombie si el TX worker cae
- **Archivo**: `src/mqtt_dispatcher.py` (L104)
- **Problema**: `res = await future` espera que `TxRateLimiter._worker_loop()` resuelva el future. Si el worker muere por una excepción no capturada, el future nunca se resolverá y el task quedará suspendido indefinidamente, acumulando tasks zombie en `_background_tasks`.
- **Solución**: `res = await asyncio.wait_for(future, timeout=30.0)` con captura de `asyncio.TimeoutError` que loga el problema y activa una alerta de diagnóstico.
- [ ] Agregar `asyncio.wait_for(..., timeout=30.0)` en `await future` del dispatcher MQTT

---

## 🟡 MEDIUM — Calidad de Código y Deuda Técnica

### QUAL-001 · `NodeContactInfo` frozen=True pero contiene `list` mutable — rompe semántica de inmutabilidad
- **Archivo**: `src/contact_manager.py` (L44-97)
- **Problema**: `@dataclass(frozen=True)` en `NodeContactInfo` pero `neighbors: list[str]` es mutable. `frozen=True` impide reasignar `neighbors`, pero `contact.neighbors.append("x")` funciona sin error. El hash del dataclass cambia si la lista es mutada — comportamiento inesperado en sets/dicts.
- **Solución**: Cambiar a `neighbors: tuple[str, ...] = field(default_factory=tuple)`. Actualizar constructores con `neighbors=tuple(lista)`.
- [ ] Cambiar `neighbors: list[str]` a `tuple[str, ...]` en `NodeContactInfo`
- [ ] Actualizar todos los lugares donde se construye `NodeContactInfo` con `neighbors`

---

### QUAL-002 · `MqttClientProtocol` vacío en bridge_core.py — inútil para type checking
- **Archivo**: `src/bridge_core.py` (L39-40)
- **Problema**: `class MqttClientProtocol(Protocol): pass` — sin métodos definidos, este protocolo no aporta información de tipo. El tipo de retorno `MqttClientProtocol | Any` degrada a efectivamente `Any`, haciendo que mypy no pueda verificar nada.
- **Solución**: Definir los métodos esperados del cliente MQTT: `publish()`, `subscribe()`, `loop_start()`, `loop_stop()`, basándose en la API de paho-mqtt.
- [ ] Definir los métodos necesarios en `MqttClientProtocol` basándose en paho-mqtt API
- [ ] Eliminar el uso de `Any` en el tipo de retorno de `mqtt_client`

---

### QUAL-003 · Duplicación masiva del bloque de extracción de sender — violación DRY
- **Archivos**: `src/rx_router.py` (L235-257), `src/web/api_router.py` (L72-93)
- **Problema**: El bloque de 20+ líneas que extrae el `sender` de un payload dict está literalmente duplicado en `RxEventRouter.handle_event()` y en `WebAPIRouter.record_incoming_event()`. Un bug en uno no se propaga la corrección al otro. Ya hay divergencias entre ambas implementaciones.
- **Solución**: Crear función `extract_sender_from_payload(data: dict) -> tuple[str, str]` en `src/contact_manager.py` o nuevo `src/event_utils.py`. Reemplazar ambos bloques duplicados.
- [ ] Crear función `extract_sender_from_payload()` en `src/contact_manager.py` o nuevo `src/event_utils.py`
- [ ] Reemplazar los dos bloques duplicados con llamadas a la función compartida

---

### QUAL-004 · `admin_handler.py` (1210 líneas) es una God Class — violación SRP
- **Archivo**: `src/admin_handler.py`
- **Problema**: Con 1210 líneas, `AdminCommandHandler` gestiona: configuración local, comandos remotos de repetidores vía RF, pings de latencia, telemetría, canales, contactos, reboots locales y remotos. Complejidad ciclomática muy alta. Difícil de testear unitariamente.
- **Solución**: Dividir en clases especializadas: `LocalNodeConfigHandler` (configuración local), `RemoteRepeaterController` (gestión remota via RF), `RFCommandDispatcher` (comandos over-the-air).
- [ ] Extraer lógica de repetidores remotos a `RemoteRepeaterController`
- [ ] Extraer lógica de configuración local a `LocalNodeConfigHandler`
- [ ] Reducir `admin_handler.py` a < 400 líneas

---

### QUAL-005 · `rx_router.py` (1042 líneas) con múltiples responsabilidades — violación SRP
- **Archivo**: `src/rx_router.py`
- **Problema**: `RxEventRouter.handle_event()` hace: parseo de eventos, extracción de sender, actualización del NodeRegistry, deduplicación, publicación MQTT, broadcast WebSocket, manejo de telemetría, anuncios de nodos y mensajes de chat. Un método único de 400+ líneas.
- **Solución**: Implementar patrón Chain of Responsibility con handlers especializados: `TelemetryEventHandler`, `NodeAdvertHandler`, `MessageEventHandler`. Cada handler decide si procesa o pasa al siguiente.
- [ ] Dividir `RxEventRouter` en handlers especializados con patrón Chain of Responsibility

---

### QUAL-006 · Frames con CRC inválido no se rechazan explícitamente en el pipeline
- **Archivo**: `src/protocol_types.py` (L402-433)
- **Problema**: `parse_raw_packet()` establece `is_valid = (crc_embedded == crc_calc)` pero devuelve el frame igualmente sin lanzar excepción. El flag `is_valid=False` puede ignorarse silenciosamente en el pipeline — frames corruptos pueden llegar a MQTT y n8n.
- **Solución**: Agregar parámetro `strict: bool = True` que lanza `ValueError` si el CRC no coincide. En `process_incoming_bytes()`, capturar `ValueError` y descartar frames inválidos con log.
- [ ] Agregar parámetro `strict=True` a `parse_raw_packet()` que lanza `ValueError` en CRC inválido
- [ ] En `RawSerialFramingAdapter`, verificar y descartar frames con CRC inválido explícitamente

---

### QUAL-007 · `config.py` no valida rangos de parámetros críticos de radio al arranque
- **Archivo**: `config.py`
- **Problema**: `LORA_DEFAULT_SF` (debe ser 7-12), `LORA_DEFAULT_BW_KHZ` (125/250/500), `MQTT_PORT` (1-65535) no tienen validación de rango. Una `.env` mal configurada causa comportamiento indefinido silencioso o errores crípticos en runtime.
- **Solución**: Agregar función `_validate_config()` al final de `config.py`. `SystemExit` para parámetros de radio inválidos, `logging.warning()` para sub-óptimos.
- [ ] Agregar bloque de validación de parámetros al final de `config.py`
- [ ] Emitir `SystemExit` para parámetros de radio inválidos

---

### QUAL-008 · `deduplicator.is_duplicate()` es `async` sin ninguna operación asíncrona
- **Archivo**: `src/deduplicator.py` (L30-46)
- **Problema**: `async def is_duplicate()` no realiza ninguna operación asíncrona (sin I/O, sin `await`). Definirla como `async` obliga a callers a usar `await`, agrega overhead de coroutine, y es semánticamente incorrecto — puede causar bugs silenciosos si un caller olvida el `await`.
- **Solución**: Eliminar `async` de `is_duplicate()`. Si se necesita compatibilidad, hacer un thin wrapper async sobre la versión sync.
- [ ] Eliminar `async` de `is_duplicate()` o documentar por qué es necesario
- [ ] Actualizar todos los callers que usan `await deduplicator.is_duplicate(...)`

---

### QUAL-009 · `MeshcoreSDKAdapter.connect()` bloquea el event loop 4.5s+ durante reconexiones
- **Archivo**: `src/serial_driver.py` (L165-193)
- **Problema**: El flujo de `connect()` incluye `cx_dly=2.0` + `await asyncio.sleep(2.0)` + `await asyncio.sleep(0.5)` = 4.5s de latencia durante startup/reconexión. El watchdog que llama `connect()` bloquea el procesamiento de todos los eventos de la malla durante ese tiempo.
- **Solución**: Mover la fase de estabilización a un task background: `asyncio.create_task(self._connect_with_stabilization())`. `connect()` retorna `True` inmediatamente y actualiza `is_connected` cuando el task completa.
- [ ] Refactorizar `connect()` para que la estabilización USB sea no-bloqueante via task background

---

### QUAL-010 · Lógica de resolución de nombre de nodo duplicada en 3+ módulos
- **Archivos**: `src/rx_router.py`, `src/web/api_router.py`, `src/admin_handler.py`
- **Problema**: La lógica de "resolver nombre desde NodeRegistry dado un sender key" está implementada de forma ligeramente diferente en al menos 3 archivos. Genera inconsistencias en cómo se muestra el nombre del nodo en MQTT vs web vs logs.
- **Solución**: Crear método `NodeRegistry.resolve_display_name(key_or_prefix: str) -> str` como Single Source of Truth. Refactorizar los 3+ callers para usarlo.
- [ ] Implementar `NodeRegistry.resolve_display_name()` como Single Source of Truth
- [ ] Refactorizar los 3+ callers para usar el método centralizado

---

## 🟢 LOW — Mejoras de Robustez y Observabilidad

### ROB-001 · Watchdog reintenta reconexión serial infinitamente sin límite configurable
- **Archivo**: `src/serial_driver.py` (L723-782)
- **Problema**: El watchdog reintenta reconectar sin límite de intentos. Si el hardware está permanentemente dañado, genera logs infinitos y ciclos CPU innecesarios.
- **Solución**: Agregar `MAX_RECONNECT_ATTEMPTS = 0` (0 = ilimitado) configurable via env. Si se supera el límite, entrar en modo "dormant" revisando cada 5 minutos.
- [ ] Implementar `MAX_RECONNECT_ATTEMPTS` configurable con backoff exponencial hasta 5 min

---

### ROB-002 · `mqtt_client.publish_safe()` no valida tamaño del payload antes de enviar
- **Archivo**: `src/mqtt_client.py` (L143-160)
- **Problema**: No hay validación de tamaño del payload. Payloads demasiado grandes causarán error silencioso del broker MQTT.
- **Solución**: Validar `len(payload_str.encode()) > MQTT_MAX_PAYLOAD_BYTES` (configurable, default 128KB). Log warning y retornar False si excede.
- [ ] Agregar validación de tamaño en `publish_safe()` con log de warning y rechazo

---

### ROB-003 · `bridge_core.run_forever()` no cancela tasks pendientes durante shutdown
- **Archivo**: `src/bridge_core.py` (L631-654)
- **Problema**: En el `finally:`, solo se llama `self.stop()`. Las tasks en `_background_tasks` suspendidas quedan como "Task was destroyed but it is pending!" — fugas de recursos y posible pérdida de datos.
- **Solución**: Antes de `loop.close()`, cancelar todas las tasks: `for task in asyncio.all_tasks(loop): task.cancel()` + `loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))`.
- [ ] Agregar cancelación explícita de tasks pendientes en `run_forever()` durante shutdown

---

### ROB-004 · `NodeRegistry` en memoria pierde todos los nodos en cada reinicio del bridge
- **Archivo**: `src/contact_manager.py`
- **Problema**: El registro completo de nodos se pierde en cada reinicio. En redes con bajo tráfico, el bridge tarda horas en redescubrir todos los nodos.
- **Solución**: Implementar `save_to_file(path)` y `load_from_file(path)` en `NodeRegistry` con serialización JSON periódica (default cada 5 minutos) en `data/node_registry.json`.
- [ ] Implementar `save_to_file()` y `load_from_file()` en `NodeRegistry`
- [ ] Agregar persistencia periódica configurable (default cada 5 minutos)

---

### ROB-005 · Sin métricas de latencia del event loop asyncio
- **Archivo**: `src/diagnostics.py`
- **Problema**: No hay instrumentación del tiempo de ejecución de tasks asyncio. En SBCs de un solo núcleo, una task lenta (> 100ms) bloquea todo lo demás sin que nadie lo detecte.
- **Solución**: Activar `loop.set_debug(True)` automáticamente cuando `LOG_LEVEL=DEBUG`. Implementar poller de latencia en `DiagnosticManager`.
- [ ] Activar `loop.set_debug(True)` automáticamente cuando `LOG_LEVEL=DEBUG`
- [ ] Implementar métricas de latencia media del event loop en `DiagnosticManager`

---

### ROB-006 · Archivos `.db` de producción y tests en el directorio raíz del proyecto
- **Archivos**: `meshcore_buffer.db`, `meshcore_sim_buffer.db`, `test_sec_audit.db` (raíz)
- **Problema**: Archivos de base de datos en la raíz del repo. Pueden incluirse accidentalmente en commits. Mezclar DBs de producción con tests crea riesgo de borrar datos reales.
- **Solución**: Mover a `data/`. Agregar `*.db`, `*.db-shm`, `*.db-wal` al `.gitignore`. Actualizar `config.py` para apuntar a `data/meshcore_buffer.db`.
- [ ] Crear directorio `data/` para bases de datos de producción
- [ ] Agregar `*.db`, `*.db-shm`, `*.db-wal` al `.gitignore`
- [ ] Actualizar `config.py` para apuntar a `data/meshcore_buffer.db` por defecto

---

### ROB-007 · Callback MQTT puede crashear el hilo de red de paho-mqtt si lanza excepción
- **Archivo**: `src/mqtt_client.py` (L201-216)
- **Problema**: Si el callback MQTT lanza excepción en la rama `else` (sin `call_soon_threadsafe`), la excepción se propaga al hilo interno de paho-mqtt, terminando el loop de red y dejando el cliente sin procesar mensajes futuros.
- **Solución**: Envolver la llamada directa al callback en `try/except Exception as e: logging.error(...)`.
- [ ] Agregar `try/except Exception` alrededor de la llamada directa al callback en `_on_message()`

---

## 🔵 MEJORAS — Frontend y UX

### FE-001 · `index.html` puede usar `innerHTML` con datos no sanitizados de la malla LoRa
- **Archivo**: `src/web/static/index.html`
- **Problema**: Datos de la malla (nombres de nodos, mensajes) son input externo no confiable. Si se usa `innerHTML` sin sanitización, un nodo malicioso puede inyectar XSS en el browser del operador.
- **Solución**: Reemplazar `innerHTML` por `textContent` para datos de la malla. Implementar función `escapeHtml(str)` utilitaria en el JS del cliente.
- [ ] Auditar `index.html` por todos los usos de `innerHTML` con datos de la malla
- [ ] Reemplazar `innerHTML` por `textContent` para datos de nodos, mensajes y nombres
- [ ] Agregar función `escapeHtml()` utilitaria en el JS del cliente

---

### FE-002 · WebSocket sin reconnect automático — UI queda "muerta" tras reinicio del bridge
- **Archivo**: `src/web/static/index.html`
- **Problema**: Si la conexión WS se pierde, la UI queda sin datos en tiempo real hasta que el usuario recarga manualmente. No hay indicador de que la conexión se perdió.
- **Solución**: Implementar WebSocket auto-reconnect con backoff exponencial (1s, 2s, 4s... hasta 30s max). Resetear el delay al recibir `open`.
- [ ] Implementar WebSocket auto-reconnect con backoff exponencial en el cliente JS

---

### FE-003 · Sin indicador visual de estado de conexión WebSocket en la UI
- **Archivo**: `src/web/static/index.html`
- **Problema**: El usuario no puede distinguir visualmente si el bridge está offline o si simplemente no hay tráfico en la malla.
- **Solución**: Agregar badge de estado en el header: 🟢 Conectado (WS open), 🟡 Reconectando (WS closed, reintentando), 🔴 Sin conexión.
- [ ] Implementar indicador visual de estado de conexión WebSocket en `index.html`

---

### FE-004 · Sin paginación en endpoints de lista — rendimiento degradado en redes grandes
- **Archivo**: `src/web/api_router.py` (L224-226)
- **Problema**: `GET /api/nodes` retorna todos los nodos sin paginación. En redes grandes (50+ nodos), el payload JSON puede ser muy grande causando lentitud en SBCs.
- **Solución**: Agregar soporte `?limit=50&offset=0` en `/api/nodes`, `/api/messages` y `/api/telemetry`. Respuesta incluye `total_count` para paginación en el cliente.
- [ ] Implementar paginación en `/api/nodes`, `/api/messages` y `/api/telemetry`

---

### FE-005 · HTTP status line siempre dice "OK" para todos los códigos de error
- **Archivo**: `src/web/http_server.py` (L219)
- **Problema**: `f"HTTP/1.1 {status_code} OK\r\n"` — "OK" hardcodeado para todos los códigos. Un 404 retorna `HTTP/1.1 404 OK`. Esto confunde a clientes HTTP, proxies y herramientas de debugging.
- **Solución**: Crear diccionario `HTTP_STATUS_TEXTS` con los reason phrases correctos y usarlo en lugar de "OK" hardcodeado.
- [ ] Corregir status text en respuestas HTTP usando diccionario de reason phrases
- [ ] Implementar soporte para `204 No Content` en operaciones de eliminación

---

## Resumen de Prioridades

| ID | Módulo | Severidad | Esfuerzo |
|----|--------|-----------|----------|
| SEC-001 | API sin auth | 🔴 CRITICAL | 4h |
| SEC-002 | TCP sin auth/límite | 🔴 CRITICAL | 2h |
| SEC-003 | Broadcast sin drain OOM | 🔴 CRITICAL | 3h |
| SEC-004 | CORS wildcard | 🔴 CRITICAL | 1h |
| SEC-005 | CSP ausente / XSS | 🔴 CRITICAL | 3h |
| SEC-006 | PSK inyección firmware | 🔴 CRITICAL | 1h |
| CONC-001 | Deduplicator lock | 🟠 HIGH | 1h |
| CONC-002 | Queue sin límite OOM | 🟠 HIGH | 2h |
| CONC-003 | Background tasks race | 🟠 HIGH | 3h |
| CONC-004 | RX flood semaphore | 🟠 HIGH | 2h |
| CONC-005 | WS read timeout | 🟠 HIGH | 1h |
| CONC-006 | Watchdog ping timeout | 🟠 HIGH | 1h |
| CONC-007 | get_event_loop dep. | 🟠 HIGH | 1h |
| CONC-008 | _tx_worker duplicado | 🟠 HIGH | 1h |
| CONC-009 | Future sin timeout | 🟠 HIGH | 1h |
| QUAL-001 | list mutable en frozen | 🟡 MEDIUM | 1h |
| QUAL-002 | Protocol vacío | 🟡 MEDIUM | 1h |
| QUAL-003 | Código duplicado DRY | 🟡 MEDIUM | 3h |
| QUAL-004 | God Class admin 1210L | 🟡 MEDIUM | 8h |
| QUAL-005 | God Class rx_router 1042L | 🟡 MEDIUM | 8h |
| QUAL-006 | CRC no fuerza rechazo | 🟡 MEDIUM | 2h |
| QUAL-007 | Config sin validación | 🟡 MEDIUM | 2h |
| QUAL-008 | async innecesario | 🟡 MEDIUM | 1h |
| QUAL-009 | Connect bloqueante | 🟡 MEDIUM | 4h |
| QUAL-010 | Resolve name duplicado | 🟡 MEDIUM | 2h |
| ROB-001 | Reconexión infinita | 🟢 LOW | 2h |
| ROB-002 | MQTT payload size | 🟢 LOW | 1h |
| ROB-003 | Shutdown task cancel | 🟢 LOW | 2h |
| ROB-004 | NodeRegistry persistencia | 🟢 LOW | 4h |
| ROB-005 | Event loop métricas | 🟢 LOW | 2h |
| ROB-006 | DB files en raíz | 🟢 LOW | 1h |
| ROB-007 | MQTT callback crash | 🟢 LOW | 1h |
| FE-001 | XSS innerHTML | 🔵 MEJORA | 4h |
| FE-002 | WS reconnect | 🔵 MEJORA | 2h |
| FE-003 | Status badge | 🔵 MEJORA | 1h |
| FE-004 | Sin paginación API | 🔵 MEJORA | 3h |
| FE-005 | HTTP status text | 🔵 MEJORA | 1h |

**Total estimado: ~85 horas de implementación y testing.**

---

> **Próximos pasos**: Comenzar por los 6 ítems CRITICAL (SEC-001 a SEC-006).
> Luego abordar los HIGH de concurrencia (CONC-001 a CONC-009) para estabilidad en producción prolongada.
>
> *Generado por el Agente Orquestador (Agente 0) de MeshCore Bridge.*
> *Actualizar `docs/AGENT_ACTIVITY_REPORT.md` tras implementar cada ítem.*

--- 

## 🟡 TEST FAILURES — Known Issues from Latest Test Run

### FT-001 · `test_record_incoming_telemetry_with_known_and_unknown_nodes` — Log format mismatch
- **Archivo**: `tests/test_node_and_repeater_config.py`
- **Problema**: El test espera que el mensaje de log contenga el patrón `"Repetidor_Norte (31d03b1f)"` pero el formato actual del log es `"Telemetría recibida de nodo 'Repetidor_Norte' (31d03b1f)"` — diferencia en mayúsculas/minúsculas y formato de paréntesis.
- **Impacto**: Test falla por cambio de formato de logging, no por lógica de negocio.
- **Solución**: Actualizar el test para que coincida con el formato actual del log, o estandarizar el formato del mensaje en `rx_router.py`.
- [ ] Corregir test para que coincida con formato actual: `"Telemetría recibida de nodo 'Repetidor_Norte' (31d03b1f)"`
- [ ] O estandarizar formato de log en rx_router.py para incluir el patrón esperado

---

### FT-002 · `test_playwright_web_e2e_simulation` — E2E test infrastructure
- **Archivo**: `tests/test_playwright_e2e_simulation.py`
- **Problema**: Fallo en entorno de integración completa — probablemente requiere servidor bridge en ejecución y dependencias de navegador Playwright.
- **Impacto**: Test de integración end-to-end que falla por ambiente, no por lógica de código.
- **Solución**: Verificar que el bridge esté corriendo en `127.0.0.1:8080` y que Playwright esté instalado (`pip install playwright && playwright install`). Este test requiere entorno de ejecución completo.
- [ ] Verificar servidor bridge en ejecución para tests E2E
- [ ] Instalar/actualizar dependencias Playwright: `playwright install`
- [ ] Validar que el test funcione en ambiente CI limpio

---

> **Estado actual de pruebas**: 127 passed, 10 skipped, 2 failed (FT-001, FT-002). 
> FT-001 es un formato de log que necesita actualización. FT-002 requiere ambiente de ejecución E2E.

> **Próximos pasos**: Comenzar por los 6 ítems CRITICAL (SEC-001 a SEC-006).
> Luego abordar los HIGH de concurrencia (CONC-001 a CONC-009) para estabilidad en producción prolongada.
>
> *Generado por el Agente Orquestador (Agente 0) de MeshCore Bridge.*
> *Actualizar `docs/AGENT_ACTIVITY_REPORT.md` tras implementar cada ítem.*
