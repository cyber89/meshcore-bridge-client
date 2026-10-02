# Reporte de Auditoría Integral Capa por Capa: MeshCore Bridge

> **Estado**: En Ejecución (Fases 1 y 2 completadas — Capa 1: Presentación y Exposición; Capa 2: Orquestación, Aplicación y Casos de Uso)  
> **Fecha de Inicio**: 2026-10-01  
> **Ámbito de Evaluación**: Código fuente en `/src/`, arquitectura canónica de 5 capas, cumplimiento estricto de invariantes SSoT (`AGENTS.md`, `CONTEXT.md`), robustez perimetral, estándares RESTful (RFC 7807), tipado estático (`mypy --strict`), análisis de vulnerabilidades (`bandit`) y estilo (`ruff`).  
> **Metodología de Replicación**: Cada defecto o desviación contractual detectada cuenta con un script de reproducción determinista y aislado en `scratch/` con evidencia observable en terminal.

---

## 1. Alcance Global y Metodología de la Auditoría

La auditoría se ejecuta estrictamente **capa por capa**, abordando una única capa a la vez, de acuerdo con el Modelo Canónico de 5 Capas formalizado en [`docs/SYSTEM_LAYERS_MANUAL.md`](SYSTEM_LAYERS_MANUAL.md) y [`docs/ARCHITECTURE.md`](ARCHITECTURE.md):

1. **Capa 1: Presentación y Exposición** (Web Server, API Router, Controllers, WebSocket, Ingress MQTT, Map Tiles).
2. **Capa 2: Orquestación, Aplicación y Casos de Uso** (BridgeCore, RxEventRouter, Deduplicador, HealthReporter, Watchdog).
3. **Capa 3: Dominio, Negocio y Red Malla** (ProtocolTypes, Enums canónicos, NodeRegistry, RateLimiter, AirtimeTracker, RepeaterManager, SensorDecoder).
4. **Capa 4: Persistencia, Registro y Almacenamiento** (Almacenamiento atómico JSON de nodos/canales/airtime, PacketBuffer circular, SQLite MBTiles de solo lectura).
5. **Capa 5: Infraestructura, Hardware, Framing y Driver Físico** (SerialTransport, Framing Companion oficial, TCP Companion Server, VirtualMeshAdapter).

---

## 2. Auditoría Detallada — Capa 1: Presentación y Exposición

### 2.1 Inventario de Componentes y Módulos de la Capa 1

| Archivo / Componente | Rol / Responsabilidad | Métrica Linter / Tipado |
|---|---|---|
| [`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py) | Servidor HTTP 1.1 nativo y WebSocket RFC 6455 sobre `asyncio.start_server`. Control de concurrencia (máx 32 clientes WS), límites de carga útil (1MB DoS protection), manejo de gzip y estáticos. | `ruff: 0 issues` / `mypy: OK` |
| [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py) | Enrutador central REST que despacha peticiones hacia controladores de dominio, procesa query strings y normaliza respuestas de error bajo RFC 7807 Problem Details. | `ruff: 0 issues` / `mypy: OK` |
| [`src/web/security_inspector.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/security_inspector.py) | Inspector perimetral de seguridad en tiempo real. Bloquea Directory Traversal, escáneres de vulnerabilidades (`sqlmap`, `nikto`, etc.), payloads anómalos y almacena accesos sospechosos. | `ruff: 0 issues` / `mypy: OK` |
| [`src/web/map_tile_service.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/map_tile_service.py) | Servicio de cartografía offline autónomo. Soporta teselas XYZ en disco y bases SQLite `.mbtiles` de sólo lectura con cache en memoria y detección MIME binaria. | `ruff: 0 issues` / `mypy: OK` |
| [`src/web/controllers/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/) | 9 controladores especializados por caso de uso: `tx_controller`, `contacts_controller`, `channels_controller`, `nodes_controller`, `repeater_controller`, `config_controller`, `system_controller`, `packets_controller`, `logs_controller`. | `ruff: 0 issues` / `mypy: OK` |
| [`src/mqtt_client.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/mqtt_client.py) | Cliente MQTT cliente asíncrono sobre `paho-mqtt` v1/v2 con reconexión exponencial y publicación segura en hilo de loop. | `ruff: 0 issues` / `mypy: OK` |
| [`src/mqtt_dispatcher.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/mqtt_dispatcher.py) | Despachador de ingreso para tópicos MQTT entrantes (`{prefix}/tx`, `{prefix}/admin/cmd`, `{prefix}/admin/repeater/{node_id}/cmd`). | `ruff: 0 issues` / `mypy: OK` |
| [`src/web/static/js/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/) | SPA ligera Vanilla JavaScript (sin frameworks externos) con EventBus desacoplado, almacenamiento IndexedDB y comunicación WebSocket bidireccional. | `58/58 endpoints verificados` |

---

### 2.2 Evaluación de Arquitectura, "Deep Modules" y Principios SOLID

1. **Abstracción e Interfaz Simple (Deep Modules)**:
   - La clase `MeshCoreHttpServer` expone una interfaz concisa (`start()`, `stop()`, `broadcast_event()`), ocultando más de 1,100 líneas de lógica compleja de framing binario WebSocket, compresión dinámica Gzip, negociación HTTP 1.1 y mitigación DoS.
   - El enrutador `WebAPIRouter` encapsula el parsing de query strings y la validación numérica de parámetros en un solo punto (`_parse_bounded_int`), reduciendo drásticamente la duplicación en los controladores.
2. **Principio de Responsabilidad Única (SRP)**:
   - Los controladores en `src/web/controllers/` exhiben alta cohesión:
     - `ContactsController` gestiona exclusivamente contactos de usuarios y sincronización de libretas.
     - `TxController` gestiona el despacho de chat y difusión general.
     - `RepeaterController` se ocupa de la administración remota de infraestructura.
3. **Inyección de Dependencias**:
   - Se utiliza la dataclass `ApiContext` para desacoplar los controladores del objeto monolítico `bridge`, facilitando pruebas unitarias aisladas sin levantar sockets ni hardware real.

---

### 2.3 Verificación de Invariantes Inmutables de Protocolo y Seguridad (SSoT)

Se auditó minuciosamente el cumplimiento de las reglas inmutables de [`AGENTS.md`](../AGENTS.md) y [`CONTEXT.md`](../CONTEXT.md):

| Regla Inmutable SSoT | Estado en Capa 1 | Evidencia en Código |
|---|---|---|
| **Aislamiento de Repetidores en Contactos** | ✅ **Cumplido** | [`contacts_controller.py:41-42`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/contacts_controller.py#L41-L42): Rechaza explícitamente nodos de rol `REPEATER`, `ROUTER` o `LOCAL` con error HTTP 400 `repeater_contact_forbidden`. |
| **Prohibición de Chat/DM a Repetidores** | ✅ **Cumplido** | [`tx_controller.py:57-58`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/tx_controller.py#L57-L58): Rechaza envíos dirigidos a repetidores con HTTP 400 `tx_to_repeater_forbidden`. |
| **Prohibición de Loopback a Estación Base Local** | ✅ **Cumplido** | [`tx_controller.py:54-55`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/tx_controller.py#L54-L55): Rechaza envíos hacia la clave pública local con HTTP 400 `tx_to_local_forbidden`. |
| **Enmascaramiento de Claves y Secretos (PSK)** | ✅ **Cumplido** | [`channels_controller.py:167-170`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/channels_controller.py#L167-L170): `_get_masked_channels_list()` reemplaza toda clave PSK por `••••••••` en respuestas REST. |
| **Protección contra Directory Traversal** | ✅ **Cumplido** | [`http_server.py:364-376`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py#L364-L376) y [`security_inspector.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/security_inspector.py): Sanitiza rutas relativas, normaliza separadores y verifica pertenencia con `is_relative_to()`. |
| **Límites DoS y Protección de Memoria** | ✅ **Cumplido** | [`http_server.py:405-420`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py#L405-L420): Rechaza cuerpos HTTP > 1 MB con HTTP 413 `Payload Too Large`. Limita WebSocket a un máximo de 32 clientes concurrentes. |

---

### 2.4 Matriz de Verificación Estática y Contratos

| Herramienta | Comando Ejecutado | Resultado | Observaciones |
|---|---|---|---|
| **Ruff Linter** | `ruff check src/web src/mqtt_client.py src/mqtt_dispatcher.py` | **0 Errores** | Conformidad total con PEP 8 y buenas prácticas. |
| **Mypy Strict** | `mypy --strict src/web src/mqtt_client.py src/mqtt_dispatcher.py` | **0 Errores** | 18 archivos de código analizados con tipado estricto al 100%. |
| **Bandit Security** | `bandit -r src/web src/mqtt_client.py src/mqtt_dispatcher.py` | **0 Problemas** | 0 vulnerabilidades de severidad Media o Alta detectadas. |
| **API Contract Parity** | `verify_api_parity.py` | **100% Coincidencia** | 101 rutas REST en backend; 58 llamadas en frontend JS verificadas 1:1. |

---

## 3. Hallazgos y Defectos Detectados en la Capa 1 (Con Replicación Determinista)

Durante la inspección de flujos de control y manejo de excepciones en la Capa 1, se detectaron **2 defectos / incumplimientos contractuales**, los cuales fueron reproducidos de manera aislada y determinista.

---

### Hallazgo C1-01 (Defecto REST): Código HTTP 500 no controlado en cambio de nivel de logs

- **Severidad**: Media
- **Componente**: [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py#L448-L452)
- **Endpoint**: `POST /api/system/logs/level`
- **Estándar Violado**: RFC 7807 (Problem Details for HTTP APIs) y buenas prácticas REST. Los errores de validación de entrada del cliente deben retornar HTTP 400 (`Bad Request`) o HTTP 422 (`Unprocessable Entity`), nunca HTTP 500 (`Internal Server Error`).

#### Descripción del Error
En el método `_dispatch_system` de `api_router.py`:
```python
        if clean_path == "/api/system/logs/level":
            if method == "GET":
                diag = getattr(self.bridge, "diagnostics", None)
                lvl = diag.get_current_log_level() if diag else "INFO"
                return 200, {"status": "ok", "level": lvl}
            if method == "POST":
                diag = getattr(self.bridge, "diagnostics", None)
                target_lvl = req_body.get("level", "INFO")
                if diag:
                    new_lvl = diag.set_log_level(str(target_lvl))
                    return 200, {"status": "ok", "level": new_lvl}
                return problem_details(400, "Bad Request", "Diagnostic manager no disponible", "diagnostic_unavailable")
```
Cuando un cliente envía un valor de nivel de logging inválido (por ejemplo: `{"level": "INVALID_CUSTOM_LEVEL"}` o `{"level": "NIVEL_INEXISTENTE"}`), `DiagnosticManager.set_log_level()` lanza `ValueError(f"Nivel de log inválido: {level_name}")`.  
Al carecer de un bloque `try...except ValueError`, la excepción escala sin control hasta el bloque genérico `except Exception as e:` de `WebAPIRouter.handle_request`, transformando un error sintáctico del cliente en una respuesta de fallo interno de servidor `500 Internal Server Error`.

#### Replicación Determinista
- **Script de Reproducción**: [`scratch/reproduce_capa1_bug1_log_level_500.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa1_bug1_log_level_500.py)
- **Ejecución y Evidencia en Terminal**:
```text
$ .venv/Scripts/python.exe scratch/reproduce_capa1_bug1_log_level_500.py
ERROR:root:Error procesando solicitud REST POST /api/system/logs/level: Nivel de log inválido: SUPER_CRITICAL_CUSTOM_LEVEL
Traceback (most recent call last):
  File "C:\Users\Ruby\Desktop\meshcore-bridge\src\web\api_router.py", line 363, in handle_request
    return await self._dispatch_system(method, path, clean_path, req_body)
  File "C:\Users\Ruby\Desktop\meshcore-bridge\src\web\api_router.py", line 450, in _dispatch_system
    new_lvl = diag.set_log_level(str(target_lvl))
  File "C:\Users\Ruby\Desktop\meshcore-bridge\src\diagnostics.py", line 193, in set_log_level
    raise ValueError(f"Nivel de log inválido: {level_name}")
ValueError: Nivel de log inválido: SUPER_CRITICAL_CUSTOM_LEVEL

=== REPRODUCING BUG 1: POST /api/system/logs/level returns HTTP 500 on invalid client input ===
HTTP Status Code returned: 500
Response Body: {'type': 'urn:meshcore:error:internal_server_error', 'title': 'Internal Server Error', 'status': 500, 'detail': 'Nivel de log inválido: SUPER_CRITICAL_CUSTOM_LEVEL', 'error': 'internal_server_error', 'message': 'Nivel de log inválido: SUPER_CRITICAL_CUSTOM_LEVEL', 'timestamp': 1790894094.688314}

[REPRODUCTION CONFIRMED] BUG IDENTIFIED: The API returned HTTP 500 (Internal Server Error) instead of HTTP 400 Bad Request.
```

#### Propuesta de Solución (Remediación)
Envolver la llamada a `diag.set_log_level` en un bloque `try...except ValueError` y retornar `problem_details(400, "Bad Request", str(ve), "invalid_log_level")`:
```python
            if method == "POST":
                diag = getattr(self.bridge, "diagnostics", None)
                target_lvl = req_body.get("level", "INFO")
                if diag:
                    try:
                        new_lvl = diag.set_log_level(str(target_lvl))
                        return 200, {"status": "ok", "level": new_lvl}
                    except ValueError as ve:
                        return problem_details(400, "Bad Request", str(ve), "invalid_log_level")
                return problem_details(400, "Bad Request", "Diagnostic manager no disponible", "diagnostic_unavailable")
```

---

### Hallazgo C1-02 (Defecto MQTT Ingress): Pérdida silenciosa de respuestas en comandos de administración vía MQTT

- **Severidad**: Alta
- **Componente**: [`src/mqtt_dispatcher.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/mqtt_dispatcher.py#L185-L195) y [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py#L348-L398)
- **Tópico Afectado**: `{prefix}/admin/cmd` (`meshcore/admin/cmd`)
- **Estándar Violado**: Contrato de mensajería asíncrona MQTT (Arquitectura de n8n / Bridge). Todo comando publicado por el usuario o n8n en `meshcore/admin/cmd` debe producir una respuesta estructurada en `meshcore/admin/status`.

#### Descripción del Error
En `src/mqtt_dispatcher.py`:
```python
    async def _handle_admin_request(self, payload_str: str) -> None:
        """Ejecuta comandos de administración sobre el hardware."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = payload_str
        command = dict(data) if isinstance(data, dict) else {"action": str(data)}
        command.setdefault("action", command.get("command", ""))
        logging.info("[MQTT-ADMIN-IN] Solicitud de administración recibida")
        await self._ctx.handle_admin(command)
```
1. `_handle_admin_request` ejecuta `await self._ctx.handle_admin(command)`, pero **descarta por completo el diccionario devuelto por la llamada** (`res = await ...`).
2. Mientras que comandos históricos (como `list_nodes`, `get_config`, o comandos CLI y de repetidores) realizan llamadas explícitas a `self._publish_safe(config.TOPIC_ADMIN_STAT, ...)` dentro de sus respectivos ejecutores en `admin_handler.py`, las siguientes acciones locales:
   - `get_custom_vars`
   - `set_custom_vars` / `set_custom_var`
   - `delete_custom_var`
   - `get_path_hash_mode` / `set_path_hash_mode`
   - `get_autoadd_config` / `set_autoadd_config`
   - `get_flood_scope` / `set_flood_scope`
   - Y cualquier error controlado capturado en `AdminCommandHandler.handle()` (ej. parámetros inválidos con código 422, fallo de firmware con código 400)  
   **únicamente retornan el diccionario `res` sin publicarlo en `TOPIC_ADMIN_STAT`**.
3. En consecuencia, si un usuario o integración n8n envía una solicitud MQTT para consultar variables personalizadas (`{"action": "get_custom_vars"}`) o hash mode, el bridge ejecuta la acción internamente, pero **nunca publica la respuesta en `meshcore/admin/status`**, provocando un bloqueo por timeout indefinido en el cliente MQTT.

#### Replicación Determinista
- **Script de Reproducción**: [`scratch/reproduce_capa1_bug2_mqtt_admin_drop.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa1_bug2_mqtt_admin_drop.py)
- **Ejecución y Evidencia en Terminal**:
```text
$ .venv/Scripts/python.exe scratch/reproduce_capa1_bug2_mqtt_admin_drop.py
=== REPRODUCING BUG 2: MQTT Admin Commands drop responses for get_custom_vars / path_hash / autoadd / flood ===

--- Submitting command: list_nodes ---
Messages published for list_nodes: 1
  -> Topic: meshcore/admin/status, Payload: {"status": "ok", "action": "list_nodes", "nodes": []}

--- Submitting command: get_custom_vars ---
Messages published for get_custom_vars: 0

[REPRODUCTION CONFIRMED] BUG IDENTIFIED: 'get_custom_vars' completed, but published 0 messages to MQTT!
Root cause: admin_handler.py returns 'res' without publishing to TOPIC_ADMIN_STAT, and mqtt_dispatcher._handle_admin_request drops the return value of handle_admin().
Contract violation: MQTT client sent a command to meshcore/admin/cmd expecting response on meshcore/admin/status, but no response was ever emitted.
```

#### Propuesta de Solución (Remediación)
En `src/mqtt_dispatcher.py`, capturar el resultado de `handle_admin` y, si contiene una respuesta y no fue emitida previamente, asegurar la publicación en `config.TOPIC_ADMIN_STAT`:
```python
    async def _handle_admin_request(self, payload_str: str) -> None:
        """Ejecuta comandos de administración sobre el hardware y publica el resultado."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = payload_str
        command = dict(data) if isinstance(data, dict) else {"action": str(data)}
        command.setdefault("action", command.get("command", ""))
        logging.info("[MQTT-ADMIN-IN] Solicitud de administración recibida")
        res = await self._ctx.handle_admin(command)
        if isinstance(res, dict):
            # Para acciones que no publican internamente (ej. get_custom_vars, get_path_hash_mode, etc.)
            # o ante respuestas de error (status == "error")
            action = command.get("action", "")
            if action in (
                "get_custom_vars", "set_custom_vars", "set_custom_var", "delete_custom_var",
                "get_path_hash_mode", "set_path_hash_mode",
                "get_autoadd_config", "set_autoadd_config",
                "get_flood_scope", "set_flood_scope",
            ) or res.get("status") == "error":
                self._ctx.mqtt.publish_safe(config.TOPIC_ADMIN_STAT, json.dumps(res), qos=1)
```

---

## 4. Dictamen y Calificación de la Capa 1

- **Puntaje de Calidad de Capa 1**: **9.2 / 10**
- **Estado General**: Excelente nivel de separación de responsabilidades, seguridad perimetral contra DoS/Traversal y apego al tipado estricto (`mypy --strict`).
- **Puntos Críticos a Corregir**:
  1. Capturar `ValueError` en `POST /api/system/logs/level` para responder HTTP 400.
  2. Publicar respuestas de comandos locales / errores en `meshcore/admin/status` para evitar pérdidas de respuesta en clientes MQTT.

---

---

## 5. Auditoría Detallada — Capa 2: Orquestación, Aplicación y Casos de Uso

### 5.1 Inventario de Componentes y Módulos de la Capa 2

| Archivo / Componente | Rol / Responsabilidad | Métrica Linter / Tipado |
|---|---|---|
| [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py) | Orquestador central del ciclo de vida (`MeshCoreBridge`), arranque resiliente con diagnóstico preflight, apagado ordenado con timeouts individuales (1.5s máx), coordinación de transmisión TX e integración TCP Companion. | `ruff: 0 issues` / `mypy: OK` |
| [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py) | Enrutador principal de eventos RX de la red LoRa hacia MQTT, WebSockets y controladores de dominio; cálculo de LQI instantáneo, actualización de presencia y buffer circular. | `ruff: 0 issues` / `mypy: OK` |
| [`src/routers/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/) | 7 manejadores especializados de eventos RX: `base.py`, `advert_handler.py`, `channel_handler.py`, `direct_handler.py`, `repeater_handler.py`, `system_handler.py`, `telemetry_handler.py`. | `ruff: 0 issues` / `mypy: OK` |
| [`src/deduplicator.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/deduplicator.py) | Filtro de deduplicación de paquetes en RAM con ventana deslizante (default 60s), límite acotado (5,000 entradas) y poda continua basada en monotonic time. | `ruff: 0 issues` / `mypy: OK` |
| [`src/health_reporter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/health_reporter.py) | Observabilidad periódica en background; publica snapshots estructurados de salud del sistema, profundidad de cola TX y estado de enlaces en `meshcore/bridge/health`. | `ruff: 0 issues` / `mypy: OK` |
| [`src/serial/watchdog.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/watchdog.py) | Monitor de latido de la UART con keep-alive pasivo/activo, detección de desconexión física de hardware y reconexión resiliente con backoff exponencial y prevención de hot loops. | `ruff: 0 issues` / `mypy: OK` |
| [`src/preflight.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/preflight.py) | Diagnóstico pre-vuelo para comprobar sockets MQTT, puertos serie/TCP y evitar arranques en estados inconsistentes. | `ruff: 0 issues` / `mypy: OK` |
| [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py) & [`src/admin/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/) | Orquestación de casos de uso de administración local y remota (`CliCommandExecutor`, `LocalConfigExecutor`, `RepeaterAdminExecutor`, `TracerouteExecutor`, `WaiterRegistry`). | `ruff: 0 issues` / `mypy: OK` |

---

### 5.2 Evaluación de Arquitectura, "Deep Modules" y Principios SOLID en Capa 2

1. **Abstracción del Ciclo de Vida y Apagado Gracioso**:
   - `MeshCoreBridge._stop_subsystems()` retiene y cancela únicamente tareas propias (`self._background_tasks`), sin invocar cancelaciones globales peligrosas sobre `asyncio.all_tasks()`.
   - Cada subsistema (`tcp_server`, `web_server`, `health_reporter`, `watchdog`, `rate_limiter`, `serial_adapter`) cuenta con un timeout individual estricto (1.5 segundos) con captura aislada de `asyncio.TimeoutError`, garantizando que la falla o demora de un componente no bloquee el apagado del proceso.
   - Las operaciones de I/O de disco potencialmente bloqueantes (`node_registry.save_to_file` y `mqtt.stop`) son delegadas de forma segura a threads mediante `asyncio.to_thread`.
2. **Patrón Strategy en el Despacho de Eventos RX**:
   - `RxEventRouter` utiliza una lista de manejadores que heredan de `BaseRxHandler` (`can_handle()` / `handle()`), desacoplando limpiamente la lógica de anuncios (`AdvertHandler`), telemetría (`TelemetryHandler`), ACKs (`RepeaterAdminHandler`) y mensajes de usuario (`ChannelMessageHandler`, `DirectMessageHandler`).
3. **Gestión Determinista de Promesas RF (`WaiterRegistry`)**:
   - `WaiterRegistry.expect_response()` implementa un context manager asíncrono `@asynccontextmanager` que registra y desregistra los futuros pendientes garantizando su cancelación determinista en bloques `finally:`, eliminando fugas de memoria por comandos RF no respondidos.

---

### 5.3 Verificación de Invariantes Inmutables de Protocolo (SSoT) en Capa 2

| Regla Inmutable SSoT | Estado en Capa 2 | Evidencia en Código |
|---|---|---|
| **Prevención de Bucles de Origen Propio (Loopback Guard)** | ✅ **Cumplido** | [`rx_router.py:616`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py#L616), [`channel_handler.py:40`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/channel_handler.py#L40) y [`direct_handler.py:35`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/direct_handler.py#L35): Se descartan paquetes provenientes de la clave pública del nodo local antes de republicar a MQTT o Web. |
| **Aislamiento de Repetidores en Mensajería de Usuario** | ✅ **Cumplido** | [`rx_router.py:643-651`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py#L643-L651): Paquetes provenientes de nodos clasificados como repetidor o router se tratan como respuestas de infraestructura o telemetría, nunca como chat de usuario. |
| **Protección de Credenciales en Despacho Administrativo** | ✅ **Cumplido** | [`repeater_executor.py:222`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/repeater_executor.py#L222): Las contraseñas de repetidores enviadas por RF se enmascaran (`login {'*' * len(pwd)}`) antes de ser registradas en la respuesta estructurada o en MQTT. |
| **Concurrencia sin Bloqueo del Event Loop** | ✅ **Cumplido** | Auditoría AST (`audit_async_concurrency.py`): Cero llamadas bloqueantes `time.sleep()` o `requests` en corrutinas. |

---

### 5.4 Matriz de Verificación Estática y Concurrencia

| Herramienta | Comando Ejecutado | Resultado | Observaciones |
|---|---|---|---|
| **Ruff Linter** | `ruff check src/bridge_core.py src/rx_router.py src/routers src/deduplicator.py src/health_reporter.py src/serial/watchdog.py src/preflight.py src/admin_handler.py src/admin` | **0 Errores** | Conformidad total de sintaxis y estilo. |
| **Mypy Strict** | `mypy --strict src/bridge_core.py src/rx_router.py src/routers src/deduplicator.py src/health_reporter.py src/serial/watchdog.py src/preflight.py src/admin_handler.py src/admin` | **0 Errores** | 21 archivos fuente analizados con tipado estricto al 100%. |
| **Bandit Security** | `bandit -r src/bridge_core.py ... -ll -ii` | **0 Problemas** | 0 vulnerabilidades de severidad Media o Alta detectadas. |
| **Async Concurrency Audit** | `audit_async_concurrency.py` | **100% Conforme** | 0 bloqueos sincrónicos en el bucle de eventos. |

---

### 5.5 Hallazgos y Defectos Detectados en la Capa 2 (Con Replicación Determinista)

Durante la inspección profunda de la orquestación asíncrona y el flujo de eventos de radio, se identificaron **2 defectos arquitectónicos críticos**, ambos replicados determinísticamente:

---

### Hallazgo C2-01 (Defecto de Malla): Omisión Total de Deduplicación en el Flujo Estándar de Radio Companion

- **Severidad**: Alta
- **Componente**: [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py#L1031-L1034) y [`src/routers/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/)
- **Requisito Violado**: Regla inmutable de mitigación de spam y tormentas de retransmisión LoRa (`AGENTS.md` - Checklist de Impacto en la Malla, Pregunta 2).
- **Descripción del Error**:
  1. `MeshCoreBridge` inicializa formalmente `self.deduplicator = PacketDeduplicator(...)` y lo inyecta en `RxRouterContext`.
  2. Sin embargo, en todo `src/rx_router.py`, `self._ctx.deduplicator.is_duplicate()` **únicamente es invocado en la línea 1032**, dentro del método `_dispatch_parsed_frame(MeshcoreFrame)`.
  3. En modo operativo Companion estándar (utilizando el SDK oficial de MeshCore), los eventos de radio son despachados como diccionarios o eventos SDK (`CHANNEL_MSG_RECV`, `CONTACT_MSG_RECV`, etc.) a través de los manejadores `ChannelMessageHandler`, `DirectMessageHandler`, etc.
  4. **Ninguno de estos manejadores consulta el deduplicador**.
  5. En consecuencia, cuando un paquete de difusión o mensaje directo es retransmitido por múltiples repetidores de la malla (inundación controlada habitual en LoRa), el bridge procesa cada eco idéntico como un paquete nuevo: ejecuta grabaciones repetidas en disco/búfer, emite múltiples eventos idénticos por WebSocket y publica mensajes duplicados en los tópicos MQTT (`meshcore/rx/all`, `meshcore/rx/public`, `meshcore/rx/channel/ch_X`).

#### Replicación Determinista
- **Script de Reproducción**: [`scratch/reproduce_capa2_bug1_dedup_bypass.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa2_bug1_dedup_bypass.py)
- **Ejecución y Evidencia en Terminal**:
```text
$ .venv/Scripts/python.exe scratch/reproduce_capa2_bug1_dedup_bypass.py
INFO:root:[RX-CANAL] De: SenderNode -> Para: Canal #0 | Texto: 'Flood mesh test message' | LQI: 81.36% [EXCELLENT] | RSSI: -80 dBm, SNR: 9.0 dB
INFO:root:[RX-CANAL] De: SenderNode -> Para: Canal #0 | Texto: 'Flood mesh test message' | LQI: 79.04% [GOOD] | RSSI: -83 dBm, SNR: 8.5 dB
=== REPRODUCING BUG C2-01: Deduplication Bypass for Standard Mesh Events in RxEventRouter ===

[Step 1] Feeding incoming mesh channel message...
MQTT publish calls after 1st event: 2 (published to rx/all and rx/public)
Deduplicator cache entries: 0

[Step 2] Feeding identical mesh channel message 100ms later (simulated multi-hop flood)...
Total MQTT publish calls after 2nd event: 4
Deduplicator cache entries: 0

[REPRODUCTION CONFIRMED] BUG IDENTIFIED: Both identical packets were fully processed (2 -> 4 MQTT publishes)!
Root cause: RxEventRouter only calls deduplicator.is_duplicate() in _dispatch_parsed_frame(MeshcoreFrame).
Standard companion SDK events completely bypass deduplication, causing duplicate MQTT publications, redundant database writes and duplicate WebSocket events during mesh flooding.
```

#### Propuesta de Solución (Remediación)
En `src/rx_router.py`, incorporar la validación de duplicados en `_handle_mesh_msg_common` antes de procesar o publicar:
```python
        dedup_key = f"msg::{msg.sender}::{msg.channel_idx}::{hash(msg.text)}"
        if await self._ctx.deduplicator.is_duplicate(dedup_key):
            logging.debug(f"[RX-DEDUP] Descartando mensaje duplicado de {msg.sender} en canal #{msg.channel_idx}")
            return None
```

---

### Hallazgo C2-02 (Defecto de Concurrencia): Bloqueo Indefinido de `_transaction_lock` en Servidor TCP Companion

- **Severidad**: Crítica
- **Componente**: [`src/bridge_core.py:269`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py#L269) y [`src/tcp_companion_server.py:377`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py#L377)
- **Requisito Violado**: Estándar de concurrencia y prevención de bloqueos indefinidos (`async-concurrency-engineering`).
- **Descripción del Error**:
  1. En `src/tcp_companion_server.py`, el despacho de comandos entrantes de clientes móviles y CLI se ejecuta bajo una cerradura de transacción exclusiva:
     ```python
     async with self._transaction_lock:
         sent = await self.bridge.handle_tcp_companion_command(payload, client_writer)
     ```
  2. En `src/bridge_core.py` (método `handle_tcp_companion_command`), cuando la aplicación móvil o CLI envía un mensaje de chat (tipo 2 o 3), la transmisión se encola en el `RateLimiter`:
     ```python
     future = await self.rate_limiter.submit(payload=payload, priority=TxPriority.NORMAL, target=target, channel_idx=channel_idx)
     result = await future
     ```
  3. A diferencia de `tx_controller.py` y `mqtt_dispatcher.py` (que utilizan `await asyncio.wait_for(future, timeout=30.0)`), en `bridge_core.py:269` se realiza un **`await future` sin límite de tiempo (unbounded wait)**.
  4. Si la cola de transmisión está llena, o el transceptor serial está ocupado en una transacción administrativa, o se activa el cutoff de duty cycle de airtime LoRa, el futuro permanece sin resolver.
  5. En ese escenario, `handle_tcp_companion_command` retiene `self._transaction_lock` indefinidamente, **bloqueando por completo el procesamiento de cualquier comando posterior para todos los clientes conectados al servidor TCP Companion**.

#### Replicación Determinista
- **Script de Reproducción**: [`scratch/reproduce_capa2_bug2_tcp_companion_unbounded_future.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa2_bug2_tcp_companion_unbounded_future.py)
- **Ejecución y Evidencia en Terminal**:
```text
$ .venv/Scripts/python.exe scratch/reproduce_capa2_bug2_tcp_companion_unbounded_future.py
=== REPRODUCING BUG C2-02: Unbounded 'await future' in handle_tcp_companion_command ===

[Step 1] Invoking handle_tcp_companion_command with unresolved future...
[REPRODUCTION CONFIRMED] BUG IDENTIFIED: handle_tcp_companion_command hung indefinitely!
Root cause: line 269 of src/bridge_core.py awaits 'result = await future' without an asyncio.wait_for timeout.
Contrast: tx_controller.py and mqtt_dispatcher.py use wait_for(future, timeout=30.0).
Impact: In tcp_companion_server.py:377, this is called inside 'async with self._transaction_lock:'.
Holding _transaction_lock indefinitely completely freezes the TCP Companion server for all connected mobile apps and CLI clients.
```

#### Propuesta de Solución (Remediación)
En `src/bridge_core.py:269`, envolver la espera del futuro con un timeout acotado (ej. 30 segundos) y captura de `asyncio.TimeoutError`:
```python
                try:
                    future = await self.rate_limiter.submit(
                        payload=payload, priority=TxPriority.NORMAL,
                        target=target, channel_idx=channel_idx
                    )
                    result = await asyncio.wait_for(future, timeout=30.0)
                    return isinstance(result, dict) and str(result.get("status", "")).lower() in ("sent", "ok", "success")
                except asyncio.TimeoutError:
                    logging.warning("Timeout esperando confirmación de transmisión TCP Companion en cola TX", extra={"skip_broadcast": True})
                    return False
                except Exception:
                    logging.warning("No se pudo enviar chat TCP por la cola TX", extra={"skip_broadcast": True})
                    return False
```

---

---

## 7. Auditoría Detallada: Capa 3 – Dominio, Negocio y Red Malla (MeshCore Domain)

### 7.1 Alcance y Módulos Auditados

La Capa 3 concentra el modelo de dominio puro, la lógica de negocio de la red mallada y los algoritmos matemáticos deterministas de radiofrecuencia y telemetría:

| Módulo | Responsabilidad de Dominio | Dependencias Externas |
|---|---|---|
| [`src/protocol_types.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/protocol_types.py) | Tipos canónicos, opcodes oficiales, enums y framing in-memory SOF/EOF/CRC | `struct`, `enum`, `dataclasses` (Stdlib puro) |
| [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) | `NodeRegistry`, identidades inmutables `NodeIdentity`, `NodeRfMetrics`, `NodeTelemetry`, `NodeContactInfo` | Stdlib puro (`threading`, `json`, `time`) |
| [`src/rate_limiter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rate_limiter.py) | `TxRateLimiter`, `CustomTxQueue`, `AirtimeTracker`, fórmula de airtime Semtech AN1200.13 | Stdlib puro (`asyncio`, `collections`, `heapq`) |
| [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py) | `RepeaterManager`, construcción de comandos CLI/Admin a repetidores y parseo de telemetría | Stdlib puro (`re`, `json`, `time`) |
| [`src/lqi_engine.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/lqi_engine.py) | `LinkQualityEngine`, cálculo EMA de calidad de enlace LQI, atenuación y saltos | Stdlib puro (`time`, `enum`) |
| [`src/sensor_decoder.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/sensor_decoder.py) | `CayenneLPPDecoder`, decodificador binario IPSO CayenneLPP y formateador visual | `io`, `struct` (Stdlib puro) |
| [`src/shared_utils.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/shared_utils.py) | Funciones de dominio transversales: clasificación de roles, normalización de batería, límites de potencia | `src.protocol_types` |
| [`src/target_resolver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/target_resolver.py) | `TargetResolver`, resolución unificada de destinos sin inventar claves ni prefijos ambiguos | `typing` |

---

### 7.2 Matriz de Verificación Estática y Cumplimiento

Se ejecutó la batería completa de analizadores estáticos de código sobre los 8 módulos de la Capa 3:

```powershell
# 1. Linter y formateo PEP 8
.venv\Scripts\ruff.exe check src/protocol_types.py src/contact_manager.py src/rate_limiter.py src/repeater_manager.py src/lqi_engine.py src/sensor_decoder.py src/shared_utils.py src/target_resolver.py
# Resultado: All checks passed! (0 errores)

# 2. Tipado estricto Mypy
.venv\Scripts\mypy.exe --strict src/protocol_types.py src/contact_manager.py src/rate_limiter.py src/repeater_manager.py src/lqi_engine.py src/sensor_decoder.py src/shared_utils.py src/target_resolver.py
# Resultado: Success: no issues found in 8 source files

# 3. Auditoría de Seguridad Bandit (CWE/OWASP)
.venv\Scripts\bandit.exe -r src/protocol_types.py src/contact_manager.py src/rate_limiter.py src/repeater_manager.py src/lqi_engine.py src/sensor_decoder.py src/shared_utils.py src/target_resolver.py
# Resultado: No issues identified. (0 low, 0 medium, 0 high)

# 4. Compatibilidad Python 3.10
python scripts/verify_python_standards.py
# Resultado: Python 3.10 verification passed!
```

---

### 7.3 Hallazgos y Defectos Replicados en la Capa 3

---

#### 🔴 Bug C3-01: Excepción de Concurrencia `deque mutated during iteration` en `AirtimeTracker.get_stats()`

- **Gravedad**: Media-Alta (Provoca fallos HTTP 500 intermitentes en la WebUI SPA y colapsos en el reportero periódico de telemetría MQTT/WebSocket).
- **Módulo**: [`src/rate_limiter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rate_limiter.py#L387-L445) (`AirtimeTracker.get_stats`)
- **Regla Violada**: `AGENTS.md` Sección 2 (Concurrencia segura entre bucles asíncronos y lecturas concurrentes).

##### Análisis Causal
En `AirtimeTracker`, `self._history` es una instancia de `collections.deque` que almacena los registros de transmisión de las últimas 24 horas. 
1. El hilo/worker de transmisión (`TxRateLimiter._worker_loop`) invoca continuamente `self.airtime_tracker.record_tx(...)`, el cual realiza `self._history.append(rec)` y poda registros antiguos mediante `self._history.popleft()`.
2. Al mismo tiempo, los endpoints REST de estadísticas (`GET /api/stats`, `GET /api/system/health`, `GET /api/airtime`), el despachador de WebSockets o el reportero MQTT (`HealthReporter`) llaman a `get_stats()`.
3. En `get_stats()` (líneas 397-402), se itera directamente sobre la colección:
   ```python
   for r in self._history:
       daily_ms += r.airtime_ms
       if r.timestamp >= cutoff_1h:
           hourly_ms += r.airtime_ms
           hourly_pkts += 1
   ```
4. En Python, `collections.deque` no admite modificaciones concurrentes (`append` o `popleft`) mientras un iterador está activo. La colección lanza inmediatamente una excepción nativa inatrapable: `RuntimeError: deque mutated during iteration`.
5. Al no existir un lock de exclusión mutua para la lectura de `_history`, cualquier carga concurrente de tráfico LoRa genera excepciones no controladas.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa3_bug1_airtime_deque_concurrency.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug1_airtime_deque_concurrency.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa3_bug1_airtime_deque_concurrency.py
  # Salida:
  # [REPRODUCED] Bug C3-01: Caught expected RuntimeError: deque mutated during iteration
  # Exit Code: 1
  ```

##### Propuesta de Solución (Remediación)
Añadir un cerrojo de sincronización `self._history_lock = threading.Lock()` en `AirtimeTracker` y proteger la iteración creando una instantánea `list(self._history)` bajo el lock:
```python
    def get_stats(self) -> dict[str, Any]:
        now = time.time()
        with self._history_lock:
            self._prune(now)
            records_snapshot = list(self._history)
            cutoff_1h = now - 3600.0
            hourly_ms = sum(r.airtime_ms for r in records_snapshot if r.timestamp >= cutoff_1h)
            daily_ms = sum(r.airtime_ms for r in records_snapshot)
            hourly_pkts = sum(1 for r in records_snapshot if r.timestamp >= cutoff_1h)
```

---

#### 🔴 Bug C3-02: Excepción de Concurrencia `dictionary changed size during iteration` en Métodos de Búsqueda de `NodeRegistry`

- **Gravedad**: Alta (Bloquea o hace fallar búsquedas de contactos, autocompletado en el frontend y ruteo de mensajes entrantes/salientes).
- **Módulo**: [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py#L1326-L1362) (`NodeRegistry.get_by_key_or_prefix`, `find_by_name`, `list_discovered`)
- **Regla Violada**: Invariante de hilo seguro en operaciones O(1) de `NodeRegistry`.

##### Análisis Causal
`NodeRegistry` declara un `self._lock = threading.Lock()` para garantizar operaciones atómicas. Métodos de escritura como `add_or_update()`, `set_local_pubkey()`, `remove_node()` y `cleanup_inactive()` adquieren estrictamente `with self._lock:`.

Sin embargo, los métodos de lectura y búsqueda clave omiten la adquisición de dicho lock:
1. `get_by_key_or_prefix(self, query: str)` en líneas 1342-1344:
   ```python
   matches = [contact for key, contact in self._nodes_by_key.items()
              if len(q) < len(key) and key.startswith(q)]
   ```
2. `find_by_name(self, name: str)` en líneas 1357-1361:
   ```python
   for contact in self._nodes_by_key.values():
       c_name = (contact.name or "").strip().lower()
       ...
   ```
3. `list_discovered(self)` en líneas 1238-1241:
   ```python
   for c in self._nodes_by_key.values():
   ```

Cuando la radio recibe anuncios en ráfaga (adverts de nodos vecinos) o paquetes LoRa que disparan `add_or_update()`, el diccionario `self._nodes_by_key` cambia de tamaño en segundo plano. Si en ese mismo instante un hilo HTTP (FastAPI) resuelve un contacto para la interfaz web, o `TargetResolver` busca un prefijo, Python aborta con `RuntimeError: dictionary changed size during iteration`.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa3_bug2_noderegistry_dict_concurrency.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug2_noderegistry_dict_concurrency.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa3_bug2_noderegistry_dict_concurrency.py
  # Salida:
  # [REPRODUCED] Bug C3-02: Caught expected RuntimeError: dictionary changed size during iteration
  # Exit Code: 1
  ```

##### Propuesta de Solución (Remediación)
Envolver las búsquedas e iteraciones internas de `NodeRegistry` bajo el cerrojo existente `with self._lock:`:
```python
    def get_by_key_or_prefix(self, query: str) -> NodeContactInfo | None:
        if not query:
            return None
        q = query.strip().lower()
        with self._lock:
            if q in self._nodes_by_key:
                return self._nodes_by_key[q]
            if q in self._nodes_by_name:
                target_key = self._nodes_by_name[q]
                return self._nodes_by_key.get(target_key)
            matches = [contact for key, contact in self._nodes_by_key.items()
                       if len(q) < len(key) and key.startswith(q)]
            return matches[0] if len(matches) == 1 else None

    def find_by_name(self, name: str) -> NodeContactInfo | None:
        if not name:
            return None
        n_clean = name.strip().lower()
        with self._lock:
            if n_clean in self._nodes_by_name:
                cand_key = self._nodes_by_name[n_clean]
                res = self._nodes_by_key.get(cand_key)
                if res:
                    return res
            for contact in self._nodes_by_key.values():
                c_name = (contact.name or "").strip().lower()
                c_alias = (contact.alias or "").strip().lower()
                if c_name == n_clean or c_alias == n_clean:
                    return contact
        return None
```

---

#### 🟡 Bug C3-03: Pérdida de Historial Acumulado de Airtime y Paquetes en Reinicios (`AirtimeTracker.load_history`)

- **Gravedad**: Media (Afecta la persistencia a largo plazo de estadísticas regulatorias de radiofrecuencia y telemetría histórica).
- **Módulo**: [`src/rate_limiter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rate_limiter.py#L232-L276) (`AirtimeTracker.load_history`)
- **Regla Violada**: `AGENTS.md` Sección 4 (Checklist de Impacto en la Malla LoRa - Pregunta 3: Persistencia de estado y seguridad).

##### Análisis Causal
En `save_history()`, `AirtimeTracker` serializa el archivo JSON de airtime guardando campos agregados de por vida junto con los registros detallados de la ventana de 24 horas:
```json
{
  "total_airtime_ms": 125430.5,
  "total_packets": 5420,
  "records": [...]
}
```
Sin embargo, en `load_history()`:
```python
        self.total_airtime_ms: float = 0.0
        self.total_packets: int = 0
        ...
        for r_data in recs:
            try:
                rec = AirtimeRecord.from_dict(r_data)
                if rec.timestamp >= cutoff_24h:
                    self._history.append(rec)
                    self.total_airtime_ms += rec.airtime_ms
                    self.total_packets += 1
```
1. `load_history()` ignora por completo `data.get("total_airtime_ms")` y `data.get("total_packets")`.
2. En su lugar, inicializa los contadores en cero y únicamente suma los registros que no hayan expirado en la ventana deslizante de 24 horas (`rec.timestamp >= cutoff_24h`).
3. Si el transceptor o bridge permanece apagado durante más de 24 horas, todos los registros son descartados y tanto `total_airtime_ms` como `total_packets` se resetean a `0.0` y `0`.
4. Incluso durante la operación continua normal, cualquier tiempo de aire acumulado antes de las últimas 24 horas es destruido en el siguiente reinicio del servicio, destruyendo las métricas de uso histórico.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa3_bug3_airtime_history_loss.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug3_airtime_history_loss.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa3_bug3_airtime_history_loss.py
  # Salida:
  # [STEP 1] Recorded initial airtime: 8000.0 ms, packets: 2
  # [STEP 2] Saved to JSON: total_airtime_ms=8000.0, total_packets=2
  # [STEP 3] Reloaded in tracker2: total_airtime_ms=0.0, total_packets=0
  # [REPRODUCED] Bug C3-03: Cumulative history lost on reload! Expected 8000.0 ms / 2 pkts, got 0.0 ms / 0 pkts.
  # Exit Code: 1
  ```

##### Propuesta de Solución (Remediación)
Restaurar los totales acumulados desde los campos guardados en `data`:
```python
            saved_total_at = data.get("total_airtime_ms")
            if saved_total_at is not None:
                self.total_airtime_ms = float(saved_total_at)
            saved_total_pkts = data.get("total_packets")
            if saved_total_pkts is not None:
                self.total_packets = int(saved_total_pkts)
```

---

## 8. Dictamen y Calificación de la Capa 3

- **Puntaje de Calidad de Capa 3**: **8.7 / 10**
- **Estado General**: Excelente rigor matemático en las fórmulas de modulación LoRa Semtech AN1200.13, decodificación Cayenne LPP y composición limpia en dataclasses inmutables de `NodeContactInfo`.
- **Puntos Críticos a Corregir**:
  1. Proteger con cerrojo de sincronización la iteración de `_history` en `AirtimeTracker.get_stats()` para evitar colapsos por concurrencia.
  2. Adquirir `self._lock` en los métodos de búsqueda por prefijo y nombre de `NodeRegistry`.
  3. Rehidratar fielmente `total_airtime_ms` y `total_packets` desde el archivo JSON en `AirtimeTracker.load_history()`.

---

## 9. Transición a Capa 4

Conforme a la regla de ejecución **capa por capa, una a la vez**, se completó la auditoría de la Capa 3 y se procedió a la inspección exhaustiva de la Capa 4.

---

## 10. Auditoría Detallada: Capa 4 - Adaptadores, Dispositivos y Servicios

### 10.1 Alcance y Módulos Inspeccionados

La **Capa 4 (Adaptadores, Dispositivos y Servicios)** abarca el subsistema de comunicación de bajo nivel con el transceptor radio, la serialización/deserialización binaria, emulación física en memoria, watchdog de vivacidad de hardware y el servidor de sockets TCP para clientes oficiales (App Móvil y MeshCore CLI).

- [`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py): Fachada canónica y re-exportación de interfaces seriales.
- [`src/serial/serial_base.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/serial_base.py): Clase abstracta base `BaseSerialAdapter` y auto-detección multiplataforma `detect_serial_port()`.
- [`src/serial/sdk_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/sdk_adapter.py): Adaptador de producción basado en el SDK oficial `meshcore_py` con sincronización de respuestas, serialización de transacciones binarias y puente de eventos.
- [`src/serial/raw_framing.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/raw_framing.py): Máquina de estados de de-framing en memoria con delimitadores SOF/EOF, byte stuffing (ESC/XOR) y verificación estricta de CRC-16-CCITT.
- [`src/serial/watchdog.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/watchdog.py): Monitor supervisor asíncrono con verificación de presencia física USB, ping suave de vivacidad y reconexión automática con backoff exponencial.
- [`src/tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py): Servidor asíncrono TCP (`0x3C`/`0x3E`) con framing binario Companion, control de concurrencia mediante `_transaction_lock`, autenticación opcional y enrutamiento bidireccional hacia la radio.
- [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py): Transceptor virtual y simulador de malla distribuida para pruebas sin hardware (telemetría CayenneLPP, bot de eco en DMs y comandos Companion).
- [`src/packet_buffer.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/packet_buffer.py): Búfer circular en memoria para sniffer LoRa y generadores de exportación binaria PCAP (Wireshark DLT_USER0), CSV estructurado y JSON.

---

### 10.2 Análisis Estático y Métricas de Conformidad

1. **Ruff Linter**:
   - `ruff check src/serial/ src/serial_driver.py src/tcp_companion_server.py src/virtual_mesh_adapter.py src/packet_buffer.py`
   - **Resultado**: 0 errores o warnings de formato/sintaxis.
2. **Mypy Strict**:
   - `mypy --strict src/serial/ src/serial_driver.py src/tcp_companion_server.py src/virtual_mesh_adapter.py src/packet_buffer.py`
   - **Resultado**: 0 errores en 8 archivos fuente evaluados.
3. **Bandit Security**:
   - 0 vulnerabilidades de severidad Media o Alta detectadas. 10 avisos de severidad Baja correspondientes a patrones `try-except-pass` intencionales durante cierres y limpiezas de descriptores de sockets.
4. **Verificación de Protocolo Oficial (SSoT)**:
   - Los opcodes y layouts de trama de Companion (`CMD_SEND_TXT_MSG=2`, `CMD_SEND_CHANNEL_TXT_MSG=3`, `CMD_GET_CONTACTS=4`, `CMD_DEVICE_QUERY=22`, `CMD_GET_CHANNEL=31`) concuerdan con la especificación de `reference/meshcore/` y `reference/openhop_core/`.

---

### 10.3 Hallazgos y Defectos Detectados en la Capa 4

A continuación se detallan los 3 defectos identificados en esta capa, todos replicados de manera determinista mediante scripts aislados en el directorio `scratch/`.

---

#### 🔴 Bug C4-01: Falla Crítica al Eliminar Contactos por Prefijo Hexadecimal (`MeshcoreSDKAdapter.remove_contact`)

- **Gravedad**: Alta (Bloquea la eliminación de contactos en el transceptor serial y deja registros huérfanos en la memoria del SDK).
- **Módulo**: [`src/serial/sdk_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial/sdk_adapter.py#L1408-L1428) (`remove_contact`)
- **Regla Violada**: SSoT de Interfaz Hardware MeshCore y `AGENTS.md` (Integridad del registro de contactos).

##### Análisis Causal
En `MeshcoreSDKAdapter`, operaciones como `share_contact()` y `export_contact()` implementan resolución defensiva del destino invocando `self._resolve_target(contact_key)` para convertir identificadores de 12 caracteres (prefijos), nombres o alias en la clave pública canónica completa de 32 bytes (64 caracteres hexadecimales).

Sin embargo, en `remove_contact()`:
```python
    async def remove_contact(self, pubkey: str) -> dict[str, Any]:
        ...
        try:
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "remove_contact"):
                res = await self.run_sdk_command("remove_contact", pubkey)
                ...
                contacts = getattr(self.mc, "_contacts", None)
                if isinstance(contacts, dict):
                    contacts.pop(pubkey, None)
                return {"status": "OK", "response": str(res)}
        except Exception as e:
            logging.warning(f"Fallo eliminando contacto del transceptor serial: {e}")
            return {"status": "ERROR", "reason": str(e)}
```
1. Si un usuario invoca `DELETE /api/contacts/{pubkey}` pasando un prefijo de 12 caracteres (formato canónico de `NodeRegistry` para nodos descubiertos por advert), `remove_contact()` pasa directamente el string de 12 caracteres a `self.mc.commands.remove_contact(pubkey)`.
2. El SDK oficial `meshcore_py` ejecuta internamente `_validate_destination(key, prefix_length=32)`, el cual exige estrictamente una cadena de 64 caracteres hexadecimales (`len(dst) >= 2 * prefix_length`). Al recibir 12 caracteres, lanza `ValueError("Invalid public key hex string: ...")`.
3. Esto es capturado por la cláusula `except Exception`, retornando `{"status": "ERROR", "reason": "..."}`, lo que causa que el controlador web (`contacts_controller.py`) devuelva un fallo de mutación serial y **aborte la eliminación del contacto en el bridge**.
4. Además, `contacts.pop(pubkey, None)` busca la clave literal de 12 caracteres en `self.mc._contacts` (que está indexado por claves completas de 64 caracteres), fallando silenciosamente en limpiar el contacto del caché del SDK.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa4_bug1_remove_contact_prefix.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug1_remove_contact_prefix.py)
- **Ejecución y Salida**:
  ```powershell
  .venv\Scripts\python scratch\reproduce_capa4_bug1_remove_contact_prefix.py
  # Salida:
  # WARNING:root:Fallo eliminando contacto del transceptor serial: Invalid public key hex string: a1b2c3d4e5f6
  # === TEST REPRODUCCIÓN BUG C4-01: remove_contact con prefijo ===
  # Contacto en caché antes del borrado: ['a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0']
  # Intentando eliminar usando prefijo de 12 caracteres: 'a1b2c3d4e5f6'...
  # Resultado devuelto por adapter.remove_contact: {'status': 'ERROR', 'reason': 'Invalid public key hex string: a1b2c3d4e5f6'}
  # ¿Fallo con status ERROR?: True
  # ¿Clave completa sigue presente en mc._contacts?: True
  # >>> ERROR REPRODUCIDO CON ÉXITO: remove_contact no resuelve el prefijo a clave completa de 32 bytes.
  ```

##### Propuesta de Solución (Remediación)
Resolver el identificador a través de `self._resolve_target(pubkey)` antes de emitir la orden a la radio y purgar el diccionario:
```python
        try:
            target_key = pubkey
            try:
                target = self._resolve_target(pubkey)
                if isinstance(target, dict) and "public_key" in target:
                    target_key = str(target["public_key"])
                elif hasattr(target, "public_key"):
                    target_key = str(target.public_key)
                elif isinstance(target, str):
                    target_key = target
            except Exception as ex_res:
                logging.debug("Target resolution for remove_contact fallback: %s", ex_res)

            norm_key = target_key.lower()
            if hasattr(self.mc, "commands") and hasattr(self.mc.commands, "remove_contact"):
                res = await self.run_sdk_command("remove_contact", norm_key)
                error = self._command_error(res)
                if error:
                    return error
                contacts = getattr(self.mc, "_contacts", None)
                if isinstance(contacts, dict):
                    contacts.pop(norm_key, None)
                    # Purgar también por prefijo si la clave original difiere
                    for k in list(contacts.keys()):
                        if k.startswith(pubkey.lower()):
                            contacts.pop(k, None)
                return {"status": "OK", "response": str(res)}
```

---

#### 🟡 Bug C4-02: Bucle Local Permitido hacia Prefijo de la Estación Base Host (`VirtualMeshAdapter.send_message`)

- **Gravedad**: Media (Violación de invariante canónica de dominio LoRa).
- **Módulo**: [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py#L538-L541) (`VirtualMeshAdapter.send_message`)
- **Regla Violada**: `AGENTS.md` Regla 1.1 Item 2 (Restricción Estricta del Nodo Local - bucle local prohibido).

##### Análisis Causal
En `VirtualMeshAdapter.send_message()`:
```python
        target_clean = str(target or "").strip().lower()
        local_key = str(self.mc.self_info.get("public_key", "")).lower()
        if target_clean and (target_clean == "local" or target_clean == local_key):
            return {"status": "ERROR", "reason": "No se permite chat al nodo local"}
```
1. La guarda contra mensajes dirigidos a la propia estación base local solo verifica coincidencia exacta con el string `"local"` o con la clave completa de 64 caracteres (`target_clean == local_key`).
2. Si un cliente o proceso transmite un mensaje directo especificando el prefijo de 12 caracteres de la estación base (ej. `112233445566`), `target_clean == local_key` evalúa a `False` (`12 != 64`).
3. El simulador omite la guarda, crea un nodo dinámico sintético denominado `Node_112233` con la clave del propio transceptor local, y programa la corutina `_simulate_echo_reply`.
4. El bot de eco inyecta un evento `ACK` y un evento `DIRECT_MSG` con emisor `112233445566` de vuelta al bridge, provocando un bucle de retroalimentación interna.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa4_bug2_virtual_local_loopback.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug2_virtual_local_loopback.py)
- **Ejecución y Salida**:
  ```powershell
  .venv\Scripts\python scratch\reproduce_capa4_bug2_virtual_local_loopback.py
  # Salida:
  # === TEST REPRODUCCIÓN BUG C4-02: Omisión de guarda de nodo local en VirtualMeshAdapter ===
  # Clave pública de la estación base local: 11223344556677889900aabbccddeeff11223344556677889900aabbccddeeff
  # Prefijo destino probado (12 caracteres):  112233445566
  # Respuesta inmediata de send_message: {'status': 'ok', 'delivered': False, 'target': '112233445566', ...}
  # Eventos recibidos en callback RX tras el envío: 2
  #   - Evento: ACK, Emisor: 112233445566, Texto: 
  #   - Evento: DIRECT_MSG, Emisor: 112233445566, Texto: [Echo DM de Node_112233]: Recibido: ...
  # ¿send_message aceptó el envío (status == 'ok')?: True
  # ¿Se generó eco/bucle desde el propio nodo local?: True
  # >>> ERROR REPRODUCIDO CON ÉXITO: Bucle local permitido hacia el prefijo de la estación base.
  ```

##### Propuesta de Solución (Remediación)
Verificar prefijo bidireccional exactamente como en `sdk_adapter.py` y `bridge_core.py`:
```python
        target_clean = str(target or "").strip().lower()
        local_key = str(self.mc.self_info.get("public_key", "")).lower()
        if target_clean and (
            target_clean == "local"
            or target_clean == local_key
            or (local_key and (local_key.startswith(target_clean) or target_clean.startswith(local_key[:12])))
        ):
            return {"status": "ERROR", "reason": "No se permite chat al nodo local"}
```

---

#### 🟡 Bug C4-03: Excepción no Controlada por PSK ASCII en Consulta de Canal Companion (`VirtualMeshAdapter.send_raw_companion_frame`)

- **Gravedad**: Media (Provoca crash no controlado en la corutina de despacho TCP Companion).
- **Módulo**: [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py#L748-L754) (`send_raw_companion_frame`)
- **Regla Violada**: Robustez ante entradas arbitrarias y compatibilidad con framing Companion.

##### Análisis Causal
En `VirtualMeshAdapter`:
```python
        elif cmd_type == 31 and len(data) == 2 and data[1] in self.channels:
            channel = self.channels[data[1]]
            name = str(channel["name"]).encode("utf-8")[:31].decode("utf-8", "ignore").encode("utf-8")
            secret = str(channel.get("psk", ""))
            key = bytes.fromhex(secret) if secret else hashlib.sha256(b"#public").digest()[:16]
            response = bytes([18, data[1]]) + name.ljust(32, b"\x00") + key
```
1. Cuando un cliente TCP Companion envía una consulta de información de canal (`CMD_GET_CHANNEL` opcode 31 / `0x1F`), el simulador intenta extraer la clave AES de 16 bytes llamando `bytes.fromhex(secret)`.
2. Si el canal fue configurado mediante la API web o `set_channel` utilizando una contraseña en texto plano (ej. `ClaveSecretaTact`, `my-custom-psk`), `bytes.fromhex(secret)` arroja `ValueError: non-hexadecimal number found in fromhex()`.
3. Al no existir un bloque `try-except` protegiendo este comando, la excepción escala hasta `TcpCompanionServer._dispatch_companion_command`, que registra una advertencia y descarta la solicitud, dejando al cliente TCP Companion sin los datos del canal y con un error `0x01 0x01` genérico.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa4_bug3_virtual_channel_psk_crash.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug3_virtual_channel_psk_crash.py)
- **Ejecución y Salida**:
  ```powershell
  .venv\Scripts\python scratch\reproduce_capa4_bug3_virtual_channel_psk_crash.py
  # Salida:
  # === TEST REPRODUCCIÓN BUG C4-03: Crash por PSK no hexadecimal en VirtualMeshAdapter ===
  # Configurando canal 1 con PSK ASCII: 'ClaveSecretaTact'...
  # Enviando trama binaria Companion CMD_GET_CHANNEL (0x1F 0x01)...
  # ¡CRASH DETECTADO! Tipo: ValueError, Mensaje: non-hexadecimal number found in fromhex() arg at position 1
  # ¿Se produjo crash con ValueError?: True
  # >>> ERROR REPRODUCIDO CON ÉXITO: bytes.fromhex() no maneja PSKs no hexadecimales en el simulador.
  ```

##### Propuesta de Solución (Remediación)
Adoptar el algoritmo canónico de normalización de claves implementado en `MeshcoreSDKAdapter.set_channel`:
```python
            secret = str(channel.get("psk", "")).strip()
            if not secret:
                key = hashlib.sha256(b"#public").digest()[:16]
            elif len(secret) == 32 and all(c in "0123456789abcdefABCDEF" for c in secret):
                key = bytes.fromhex(secret)
            elif len(secret) == 16:
                key = secret.encode("utf-8")
            else:
                key = hashlib.sha256(secret.encode("utf-8")).digest()[:16]
```

---

## 11. Dictamen y Calificación de la Capa 4

- **Puntaje de Calidad de Capa 4**: **8.6 / 10**
- **Estado General**: Excelente arquitectura asíncrona no bloqueante. El diseño del `SerialWatchdog` con ciclo escalonado de 2 segundos, verificación síncrona del descriptor USB y backoff exponencial previene hot-loops. El de-framing en `RawSerialFramingAdapter` y `TcpCompanionServer` aplica delimitación estricta, byte stuffing e inspección de tráfico sospechoso.
- **Puntos Críticos a Corregir**:
  1. Incorporar resolución `_resolve_target()` en `MeshcoreSDKAdapter.remove_contact()` para habilitar el borrado de contactos mediante prefijos hexadecimales o nombres.
  2. Endurecer la comprobación de nodo local en `VirtualMeshAdapter.send_message()` verificando prefijos para impedir bucles locales simulados.
  3. Proteger la conversión de claves de canal en `VirtualMeshAdapter.send_raw_companion_frame()` soportando claves ASCII y aplicando hashing SHA-256 cuando no sean hexadecimales puras.

---

## 12. Auditoría Detallada: Capa 5 (Infraestructura, Configuración y Persistencia)

### 12.1 Módulos Inspeccionados y Alcance

La Capa 5 concentra la infraestructura base del sistema, el aprovisionamiento de configuración en tiempo de arranque y ejecución, la persistencia atómica en disco para tolerancia a fallas eléctricas, y los subsistemas de logging rotativo y diagnóstico.

| Módulo / Archivo | Responsabilidad Arquitectónica | Líneas de Código (LOC) |
|---|---|---|
| [`config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/config.py) | Carga de variables de entorno `.env`, fallback nativo sin dependencias, validación semántica de rangos de radio LoRa y puertos de red (`_validate_config`). | 194 |
| [`src/web/controllers/channels_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/channels_controller.py) | Persistencia atómica de canales en `data/channels.json` (`_save_channels`, `_save_channels_async`), sincronización y mutación serial, enmascaramiento de claves PSK. | 333 |
| [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) (`NodeRegistry`) | Persistencia atómica de la base de nodos y contactos en `data/node_registry.json` (`save_to_file`, `save_to_file_async`), snapshots inmutables con sufijo PID y nanosegundos. | 1,732 |
| [`src/rate_limiter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rate_limiter.py) (`AirtimeTracker`) | Persistencia atómica del historial regulatorio y ventana móvil de 24 horas en `data/airtime_history.json` (`save_history`, `load_history`, `_write_history`). | 687 |
| [`src/web/controllers/config_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/config_controller.py) | Exposición REST de configuración de nodo, mutaciones dinámicas en caliente de parámetros de espectro y delays de repetidor. | 399 |
| [`src/diagnostics.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/diagnostics.py) & [`meshcore_bridge.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/meshcore_bridge.py) | Infraestructura de logging estructurado, buffer circular en RAM (`SystemLogHandler`), y handlers rotativos de archivos físicos (`RotatingFileHandler`). | 554 |

---

### 12.2 Análisis Estático y Auditoría de Seguridad (Bandit / Mypy / Ruff)

1. **Ruff (PEP 8 y Linting Moderno)**:
   - Ejecución: `ruff check config.py src/web/controllers/config_controller.py src/diagnostics.py`
   - Resultado: **0 errores**. Formateo y tipado conformes a estándares PEP 8.
2. **Mypy Strict (Verificación de Tipos)**:
   - Ejecución: `mypy --strict config.py src/web/controllers/config_controller.py`
   - Resultado: **0 errores**. Total compatibilidad con tipado estricto Python 3.10+.
3. **Bandit (Escaneo de Seguridad AST)**:
   - Ejecución: `bandit -r config.py src/web/controllers/config_controller.py`
   - Hallazgos:
     - `B104: Possible binding to all interfaces (0.0.0.0)` en `config.py:118,125`: `WEB_HOST = "0.0.0.0"` y `TCP_SERVER_HOST = "0.0.0.0"`. Diseñado intencionalmente para permitir acceso en contenedores Docker y redes locales, pero requiere configuración explícita de `BRIDGE_API_KEY` y `COMPANION_TOKEN`.
     - `B110: Try, Except, Pass detected` en `config.py:27`: En el fallback nativo de lectura de `.env`, los errores se capturan con `except Exception: pass`, impidiendo que el operador conozca la causa raíz de fallos de lectura de configuración.

---

### 12.3 Defectos Detectados, Replicados y Analizados en Capa 5

#### 🔴 Bug C5-01: Carrera Concurrente y Colisión de Archivo Temporal en `ChannelsController._save_channels` (Windows `WinError 32`)

- **Gravedad**: Alta (Provoca fallos de persistencia `PermissionError: [WinError 32]` en Windows y riesgo de corrupción o truncamiento de `channels.json` en POSIX ante solicitudes concurrentes).
- **Módulo**: [`src/web/controllers/channels_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/channels_controller.py#L61-L78) (`_save_channels`)
- **Regla Violada**: `AGENTS.md` Sección 2 (Regla 3: "La persistencia en disco de canales y configuraciones debe ser atómica y no bloqueante mediante archivos JSON").

##### Análisis Causal
En `ChannelsController`:
```python
    def _save_channels(self, force: bool = False) -> None:
        ...
        try:
            tmp_path = f"{self.channels_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(list(self.channels.values()), f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.channels_file)
            self._dirty = False
        except Exception as e:
            logging.error(f"Error persistiendo canales en {self.channels_file}: {e}")
            raise
```
1. `_save_channels()` utiliza una ruta de archivo temporal estática y compartida: `f"{self.channels_file}.tmp"`.
2. A diferencia de `NodeRegistry.save_to_file()` (que genera rutas con PID y timestamp en nanosegundos: `f"{target_path.stem}_{os.getpid()}_{time.time_ns()}.tmp"`), `ChannelsController` no añade discriminadores de concurrencia.
3. Además, `_save_channels()` carece de un cerrojo de hilos (`threading.Lock`). Cuando múltiples tareas asíncronas delegan escrituras a hilos (`await asyncio.to_thread(self._save_channels, force)`), múltiples workers abren el mismo archivo `.tmp` de forma simultánea.
4. En Windows, mientras un hilo mantiene abierto el descriptor del archivo temporal o ejecuta `os.replace`, los demás hilos que intentan acceder al mismo archivo colisionan y fallan inmediatamente con:
   `PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`.
5. En Linux/POSIX, las escrituras concurrentes sin bloqueo provocan solapamiento e intercalado de bytes en el archivo temporal antes del reemplazo atómico, corrompiendo la sintaxis JSON.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa5_bug1_channels_temp_race.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug1_channels_temp_race.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa5_bug1_channels_temp_race.py
  # Salida:
  # Total concurrent worker errors caught: 13
  #   [ERROR] Worker 2 failed with PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'channels.json.tmp' -> 'channels.json'
  #   [ERROR] Worker 1 failed with PermissionError: [WinError 32] The process cannot access the file because it is being used by another process: 'channels.json.tmp' -> 'channels.json'
  # >>> BUG C5-01 REPRODUCED: Concurrent writes to fixed temporary path crashed with file locking conflict!
  ```

##### Propuesta de Solución (Remediación)
Incorporar un `threading.Lock` para serializar las operaciones sobre disco y generar nombres temporales únicos basados en PID y nanosegundos:
```python
    def __init__(self, ctx: Any, channels_file: str | None = None) -> None:
        super().__init__(ctx)
        self._disk_lock = threading.Lock()
        ...

    def _save_channels(self, force: bool = False) -> None:
        if not force and not self._dirty:
            return

        target_path = Path(self.channels_file)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self._disk_lock:
            try:
                tmp_path = target_path.with_name(f"{target_path.stem}_{os.getpid()}_{time.time_ns()}.tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(list(self.channels.values()), f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, target_path)
                self._dirty = False
            except Exception as e:
                logging.error(f"Error persistiendo canales en {target_path}: {e}")
                raise
```

---

#### 🟡 Bug C5-02: Pérdida Silenciosa de Configuración y Omisión de Rehidratación en `AirtimeTracker` / `ConfigController`

- **Gravedad**: Media (Afecta la durabilidad de configuraciones críticas de radio y espectro LoRa tras reinicios del servicio).
- **Módulo**: [`src/web/controllers/config_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/config_controller.py#L117-L149) (`set_local_config`) y [`src/rate_limiter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rate_limiter.py#L232-L276) (`AirtimeTracker.load_history`)
- **Regla Violada**: `AGENTS.md` Sección 4 (Checklist de Impacto en la Malla LoRa - Pregunta 3: "Persistir el timestamp del último disparo y parámetros en base de datos o archivo JSON, nunca solo en memoria").

##### Análisis Causal
1. En `ConfigController.set_local_config()`:
   - Cuando el usuario modifica parámetros regulatorios desde la WebUI (`duty_cycle_limit_pct`, `warn_threshold_pct`, `airtime_cutoff_enabled`, `airtime_cutoff_threshold_pct`, `airtime_cutoff_resume_pct`), el controlador muta los atributos en memoria de `limiter.airtime_tracker`, pero **nunca invoca `save_history(sync=True)`**.
2. En `AirtimeTracker.save_history()`:
   - El tracker serializa exitosamente estos 5 parámetros en el payload de `airtime_history.json`:
     ```json
     {
       "duty_cycle_limit_pct": 2.5,
       "warn_threshold_pct": 95.0,
       "cutoff_threshold_pct": 45.0,
       "cutoff_resume_pct": 35.0,
       "cutoff_enabled": false,
       "records": [...]
     }
     ```
3. En `AirtimeTracker.load_history()`:
   - Al reiniciar el proceso puente, `load_history()` rehidrata la lista de registros `records`, `channel_utilization_pct` y `cutoff_active`, pero **ignora por completo** los campos `duty_cycle_limit_pct`, `warn_threshold_pct`, `cutoff_threshold_pct`, `cutoff_resume_pct` y `cutoff_enabled`.
4. En consecuencia, todas las directivas de seguridad de espectro configuradas por el usuario se revierten silenciosamente a los valores por defecto de `config.py` tras un reinicio del puente o un corte de energía.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa5_bug2_airtime_tracker_rehydration.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug2_airtime_tracker_rehydration.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa5_bug2_airtime_tracker_rehydration.py
  # Salida:
  # --- Rehydration Verification after Service Restart ---
  # duty_cycle_limit_pct: expected 2.5, actual 1.0
  # warn_threshold_pct:   expected 95.0, actual 80.0
  # cutoff_threshold_pct: expected 45.0, actual 35.0
  # cutoff_resume_pct:    expected 35.0, actual 30.0
  # cutoff_enabled:       expected False, actual True
  # >>> BUG C5-02 REPRODUCED: 5 configuration parameters were silently discarded on reload
  ```

##### Propuesta de Solución (Remediación)
1. En `ConfigController.set_local_config()`, invocar `limiter.airtime_tracker.save_history(sync=True)` tras actualizar los campos.
2. En `AirtimeTracker.load_history()`, restaurar los valores guardados en disco si están presentes:
```python
        if "duty_cycle_limit_pct" in data:
            self.duty_cycle_limit_pct = float(data["duty_cycle_limit_pct"])
        if "warn_threshold_pct" in data:
            self.warn_threshold_pct = float(data["warn_threshold_pct"])
        if "cutoff_threshold_pct" in data:
            self.cutoff_threshold_pct = float(data["cutoff_threshold_pct"])
        if "cutoff_resume_pct" in data:
            self.cutoff_resume_pct = float(data["cutoff_resume_pct"])
        if "cutoff_enabled" in data:
            self.cutoff_enabled = bool(data["cutoff_enabled"])
```

---

#### 🟡 Bug C5-03: Corrupción de Valores por Comentarios en Línea y Comillas en Parser Fallback de `.env` (`config.py`)

- **Gravedad**: Media (Afecta entornos donde `python-dotenv` no está presente o en contenedores mínimos).
- **Módulo**: [`config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/config.py#L18-L28) (Parser nativo de fallback de `.env`)
- **Regla Violada**: Robustez en la carga de configuración y aislamiento de fallos de infraestructura.

##### Análisis Causal
En `config.py`:
```python
    if env_path.is_file():
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass
```
1. Si un archivo `.env` contiene comentarios en línea habituales, tales como:
   `WEB_PORT=9090 # Puerto Web de monitoreo` o `BRIDGE_API_KEY="super-secret-12345" # Token de seguridad`
2. `line.split("=", 1)` asigna a `v` la cadena `"9090 # Puerto Web de monitoreo"`.
3. Al llamar a `_safe_int("WEB_PORT", 8080)`, la conversión `int("9090 # Puerto Web de monitoreo")` arroja `ValueError`, provocando que el puente descarte el puerto configurado por el usuario y utilice silenciosamente el puerto 8080 por defecto.
4. Asimismo, las comillas dobles que encierran secretos con comentarios en línea no se eliminan, ya que el carácter de cierre de la línea es `#` y no la comilla, corrompiendo tokens de autenticación API y contraseñas MQTT.
5. El bloque `except Exception: pass` silencia cualquier error de lectura, impidiendo alertar al administrador en los logs de arranque.

##### Replicación Determinista
- **Script de prueba**: [`scratch/reproduce_capa5_bug3_env_fallback_parser.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug3_env_fallback_parser.py)
- **Ejecución y Salida**:
  ```powershell
  python scratch/reproduce_capa5_bug3_env_fallback_parser.py
  # Salida:
  # --- Errors Encountered ---
  #   [ERROR] int(WEB_PORT) failed: invalid literal for int() with base 10: '9090 # Puerto Web de monitoreo'
  #   [ERROR] float(DUTY_CYCLE_LIMIT_PCT) failed: could not convert string to float: '2.0 # Limite horario LoRa'
  #   [ERROR] BRIDGE_API_KEY corrupted with quotes and comments: 'super-secret-12345" # Token de seguridad'
  # >>> BUG C5-03 REPRODUCED: Fallback .env parser failed to strip inline comments and preserve clean tokens!
  ```

##### Propuesta de Solución (Remediación)
Reescribir el parser nativo de fallback para manejar comentarios en línea respetando valores entrecomillados y reportar advertencias en consola si la carga falla:
```python
    if env_path.is_file():
        try:
            with open(env_path, encoding="utf-8") as f:
                for line_no, raw_line in enumerate(f, 1):
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    # Respetar strings entrecomillados
                    if (v.startswith('"') and '"' in v[1:]) or (v.startswith("'") and "'" in v[1:]):
                        quote_char = v[0]
                        end_quote_idx = v.find(quote_char, 1)
                        clean_val = v[1:end_quote_idx]
                    else:
                        clean_val = v.split("#", 1)[0].strip()
                    if k and k not in os.environ:
                        os.environ[k] = clean_val
        except Exception as e:
            import sys
            print(f"[CONFIG] Advertencia al procesar .env con parser nativo: {e}", file=sys.stderr)
```

---

## 13. Dictamen y Calificación de la Capa 5

- **Puntaje de Calidad de Capa 5**: **8.9 / 10**
- **Estado General**: Muy sólido diseño de persistencia y resiliencia. El uso de reemplazo atómico (`os.replace`) sobre archivos temporales protege la base de datos de canales y nodos contra corrupciones catastróficas durante cortes imprevistos de suministro eléctrico. La validación semántica temprana en `config._validate_config()` previene el arranque del sistema con parámetros de radiofrecuencia fuera de norma o puertos inválidos.
- **Puntos Críticos a Corregir**:
  1. Unificar el patrón de nombres temporales en `ChannelsController._save_channels` utilizando identificadores únicos (PID + nanosegundos) y serialización `threading.Lock` para eliminar bloqueos de concurrencia en Windows.
  2. Implementar la rehidratación completa de parámetros de espectro y límites horarios en `AirtimeTracker.load_history()` y forzar guardado síncrono al recibirlos en `ConfigController.set_local_config`.
  3. Fortalecer el parser nativo de `.env` en `config.py` para aislar comentarios en línea sin corromper valores numéricos ni tokens entrecomillados.

---

## 14. Resumen Ejecutivo Global y Matriz Comparativa de Calidad (Capas 1 a 5)

La auditoría completa, rigurosa y determinista capa por capa de **MeshCore Bridge** ha finalizado con éxito. Todos los componentes de la aplicación han sido examinados en profundidad, contrastados con las especificaciones de arquitectura (`CONTEXT.md`, `PROTOCOL_SPEC.md`, `ARCHITECTURE.md`, `AGENTS.md`), validados mediante escaneo estático y sometidos a pruebas de reproducción aisladas en `scratch/`.

### 14.1 Matriz de Calidad Consolidada

| Capa Arquitectónica | Ámbito / Módulos Clave | Calificación | Bugs Críticos (🔴) | Bugs Medios (🟡) | Estado General |
|---|---|:---:|:---:|:---:|---|
| **Capa 1: Presentación y Exposición** | `http_server.py`, `api_router.py`, controllers, `mqtt_client.py`, `mqtt_dispatcher.py` | **9.2 / 10** | 1 (`LOG_LEVEL` 500) | 1 (MQTT admin drop) | Excelente interfaz SPA y REST conforme a RFC 7807 Problem Details. |
| **Capa 2: Orquestación, Aplicación y Casos de Uso** | `bridge_core.py`, `rx_router.py`, routers especializados, `deduplicator.py`, `admin_handler.py` | **8.8 / 10** | 0 | 2 (Dedup bypass, TCP Future leak) | Gran resiliencia asíncrona y orquestación Deep Modules desacoplada. |
| **Capa 3: Dominio, Negocio y Red Malla** | `protocol_types.py`, `contact_manager.py`, `rate_limiter.py`, `repeater_manager.py`, `lqi_engine.py` | **8.7 / 10** | 2 (Deque race, Dict iteration race) | 1 (Airtime lifetime stats loss) | Modelos de dominio inmutables y estricto respeto a reglas SSoT de repetidores. |
| **Capa 4: Adaptadores, Dispositivos y Servicios** | `serial_driver.py`, `serial_base.py`, `sdk_adapter.py`, `raw_framing.py`, `tcp_companion_server.py`, `virtual_mesh.py` | **8.6 / 10** | 1 (Remove contact prefix failure) | 2 (Virtual local loopback, Companion PSK crash) | Watchdog serial con backoff exponencial y framing Companion/Raw robusto. |
| **Capa 5: Infraestructura, Configuración y Persistencia** | `config.py`, persistencia JSON atómica (`channels`, `nodes`, `airtime`), rotación de logs | **8.9 / 10** | 1 (Channels temp file Windows lock) | 2 (Airtime rehydration loss, .env parser) | Persistencia atómica anti-corrupción por apagado forzado y validación temprana. |
| **TOTAL CONSOLIDADO** | **Auditoría Integral de MeshCore Bridge** | **8.84 / 10** | **5** | **8** | **Grado de Producción e Ingeniería de Alta Confiabilidad** |

---

### 14.2 Catálogo Consolidado de Defectos Replicados Determinísticamente

Todos los defectos fueron verificados mediante scripts reproducibles independientes creados en el directorio `scratch/`:

1. [`scratch/reproduce_capa1_bug1_log_level_500.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa1_bug1_log_level_500.py): Error HTTP 500 no controlado por niveles de log inválidos.
2. [`scratch/reproduce_capa1_bug2_mqtt_admin_drop.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa1_bug2_mqtt_admin_drop.py): Descarte silencioso de comandos de administración MQTT sin clave `action`.
3. [`scratch/reproduce_capa2_bug1_dedup_bypass.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa2_bug1_dedup_bypass.py): Evasión de deduplicación de paquetes por inconsistencia en normalización de saltos / SNR.
4. [`scratch/reproduce_capa2_bug2_tcp_companion_unbounded_future.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa2_bug2_tcp_companion_unbounded_future.py): Fuga de futuros asíncronos sin timeout en TCP Companion.
5. [`scratch/reproduce_capa3_bug1_airtime_deque_concurrency.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug1_airtime_deque_concurrency.py): Excepción por mutación concurrente en la cola de cálculo de Duty Cycle.
6. [`scratch/reproduce_capa3_bug2_noderegistry_dict_concurrency.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug2_noderegistry_dict_concurrency.py): `RuntimeError: dictionary changed size during iteration` en la libreta de nodos.
7. [`scratch/reproduce_capa3_bug3_airtime_history_loss.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa3_bug3_airtime_history_loss.py): Pérdida de contadores históricos acumulados de airtime en reinicios.
8. [`scratch/reproduce_capa4_bug1_remove_contact_prefix.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug1_remove_contact_prefix.py): Imposibilidad de eliminar contactos mediante prefijos hexadecimales en el adaptador SDK.
9. [`scratch/reproduce_capa4_bug2_virtual_local_loopback.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug2_virtual_local_loopback.py): Evasión de protección de bucle local en el adaptador virtual ante prefijos del transceptor host.
10. [`scratch/reproduce_capa4_bug3_virtual_channel_psk_crash.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa4_bug3_virtual_channel_psk_crash.py): Crash `ValueError` por claves PSK ASCII en consultas Companion binarias.
11. [`scratch/reproduce_capa5_bug1_channels_temp_race.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug1_channels_temp_race.py): Carrera de colisión y `[WinError 32]` en el archivo temporal estático de canales.
12. [`scratch/reproduce_capa5_bug2_airtime_tracker_rehydration.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug2_airtime_tracker_rehydration.py): Omisión de rehidratación de 5 parámetros regulatorios en `AirtimeTracker.load_history()`.
13. [`scratch/reproduce_capa5_bug3_env_fallback_parser.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scratch/reproduce_capa5_bug3_env_fallback_parser.py): Corrupción de puertos y secretos por comentarios en línea en el parser de fallback de `.env`.

---

### 14.3 Conclusiones y Hoja de Ruta de Remediación

1. **Fortaleza de la Base Arquitectónica**: El sistema exhibe un alto nivel de madurez técnica (**8.84 / 10**). El modelo de desacoplamiento en 5 capas, el estricto aislamiento de dispositivos repetidores y nodo local, y la gestión de airtime con ventana móvil posicionan a MeshCore Bridge como un puente LoRa de grado industrial.
2. **Prioridad Inmediata de Corrección**:
   - Aplicar cerrojos de sincronización (`threading.Lock` / `asyncio.Lock`) y sufijos únicos en escrituras atómicas concurrentes (`NodeRegistry`, `ChannelsController`, `AirtimeTracker`).
   - Completar la rehidratación de parámetros de configuración en el ciclo de vida de arranque del puente.
   - Fortalecer los resolvedores de destinos (`_resolve_target`) en operaciones de borrado y protección de bucle local.



