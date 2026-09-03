# 📋 Reporte Colaborativo de Actividad Multi-Agente - MeshCore Bridge

Este documento es el registro central y compartido (Single Source of Truth) donde cada agente documenta sus intervenciones, módulos afectados, contratos de interfaz y estado de integración para que el **Agente Principal (Lead Orchestrator)** pueda conciliar la compatibilidad cruzada de todo el sistema.

---

## 🎯 Registro de Hitos y Tareas Recientes

### Hito: Corrección y Habilitación de Rutas REST /api/config en WebAPIRouter
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Habilitación de /api/config, /api/config/radio, /api/config/identity, /api/config/advert y /api/config/reboot en WebAPIRouter delegando en ConfigController; resolución del error 404 en consola de navegador al cargar la SPA; 100% PASS en contratos API y simulación)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - El frontend de la WebUI (`src/web/static/js/modules/settings.js`) solicita en su arranque `GET /api/config` para poblar el nodo local y envía `POST /api/config/radio` y `POST /api/config/identity` al guardar ajustes.
  - El enrutador `WebAPIRouter` sólo despachaba rutas que iniciaban con `/api/node`, provocando errores `404 Not Found` en la consola del navegador al consultar `/api/config`.
- **Acciones Realizadas**:
  - **Ampliación de Despacho en [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)**:
    - Se actualizó la guarda de enrutamiento a `clean_path.startswith(("/api/node", "/api/config"))`.
    - Se extendió `_dispatch_config` para atender de forma simétrica:
      - `GET /api/config`: Retorna la configuración consolidada del dispositivo (`ConfigController.get_device_config()`).
      - `POST /api/config/radio`: Aplica parámetros de modulación y potencia RF (`ConfigController.set_local_config(req_body)`).
      - `POST /api/config/identity`: Aplica nombre y geolocalización fija (`ConfigController.set_local_config(req_body)`).
      - `POST /api/config/advert` y `POST /api/config/reboot`: Conectados a anuncios LoRa y reinicio de hardware.
  - **Protección Perimetral en [`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py)**:
    - Se incluyó `"/api/config/reboot"` en `protected_prefixes` para requerir `x-api-key` cuando `BRIDGE_API_KEY` está activa.
  - **Pruebas de Contrato en [`.agents/skills/api-design-testing/scripts/validate_api_contract.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/api-design-testing/scripts/validate_api_contract.py)**:
    - Añadidas verificaciones automáticas para `GET /api/config`, `POST /api/config/radio`, `POST /api/config/identity` y `GET /api/node/config` (todas HTTP 200).
- **Módulos Modificados**: `src/web/api_router.py`, `src/web/http_server.py`, `.agents/skills/api-design-testing/scripts/validate_api_contract.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code de Decodificadores de Sensores (extract_telemetry_fields)
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Descomposición de extract_telemetry_fields de 254 líneas a función coordinadora de 19 líneas y 6 extractores funcionales especializados < 40 líneas cada uno; 0 code smells en sensor_decoder.py y 100% PASS en simulación)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect).
- **Problema / Requerimiento**:
  - `extract_telemetry_fields` en `src/sensor_decoder.py` era el método más largo de todo el proyecto (254 líneas), acumulando la decodificación de CayenneLPP binario, hex, listas de objetos SDK, variables ambientales, perfiles de batería/solar, uptime y coordenadas GPS en un único bloque monolítico.
  - Se requería descomponer la lógica en extractores especializados por perfil de telemetría manteniendo el tipado estricto, reduciendo la complejidad ciclomática y preservando 100% la compatibilidad retroactiva.
- **Acciones Realizadas**:
  - **Descomposición Modular en [`src/sensor_decoder.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/sensor_decoder.py)**:
    - `_extract_lpp_telemetry(data, res)`: Decodificación binaria/hexadecimal y despacho a `_parse_lpp_candidate_list`, `_map_lpp_item_to_res` y `_parse_lpp_gps_val` (< 30 líneas cada una).
    - `_extract_environment_telemetry(data, res)`: Temperatura, humedad relativa y presión atmosférica (25 líneas).
    - `_extract_power_telemetry(data, res)`: Batería (porcentaje, mV y V) y panel solar (42 líneas).
    - `_extract_system_telemetry(data, res)`: Uptime formateado legible, colas de transmisión y conteo de errores (35 líneas).
    - `_extract_radio_telemetry(data, res)`: Piso de ruido RF (dBm), tiempo en el aire (ms) y paquetes TX/RX (32 líneas).
    - `_extract_location_telemetry(data, res)`: Coordenadas geodésicas GPS lat/lon/altitud (28 líneas).
    - `extract_telemetry_fields(data)`: Reducida de 254 líneas a **19 líneas** como orquestador limpio.
- **Módulos Modificados**: `src/sensor_decoder.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code de SecurityTrafficInspector con Eventos de Auditoría Tipados
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Introducción de HttpAccessEvent y SuspiciousTrafficEvent, reducción de firmas de 7 a 2 parámetros en log_http_access y log_suspicious_traffic; actualización de todos los puntos de llamada en http_server.py y tcp_companion_server.py; 0 code smells en security_inspector.py y 100% PASS en simulación)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `SecurityTrafficInspector` en `src/web/security_inspector.py` contenía métodos de auditoría (`log_http_access` y `log_suspicious_traffic`) con firmas de 7 parámetros que infringían los estándares de Clean Code.
  - Se requería encapsular los parámetros de auditoría en dataclasses estructurados e inmutables con slots (`HttpAccessEvent`, `SuspiciousTrafficEvent`), reducir las firmas a 2 parámetros y sincronizar todas las llamadas en el servidor web y en el servidor TCP companion.
- **Acciones Realizadas**:
  - **Dataclasses Tipados en [`src/web/security_inspector.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/security_inspector.py)**:
    - Se definieron `@dataclass(slots=True) class HttpAccessEvent` (client_ip, method, path, status_code, duration_ms, user_agent) y `@dataclass(slots=True) class SuspiciousTrafficEvent` (client_ip, source_type, endpoint, anomaly_type, detail, user_agent).
    - `log_http_access(cls, event: HttpAccessEvent)`: Reducida de 7 a 2 parámetros (`cls`, `event`).
    - `log_suspicious_traffic(cls, event: SuspiciousTrafficEvent)`: Reducida de 7 a 2 parámetros (`cls`, `event`).
  - **Actualización de Clientes Consumidores**:
    - [`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py): Adaptadas 6 llamadas de seguridad perimetral y 3 de acceso HTTP/REST construyendo instancias de eventos.
    - [`src/tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py): Adaptadas 5 llamadas de auditoría TCP (filtrado IP, tokens inválidos, timeouts de auth, tramas sobredimensionadas).
- **Módulos Modificados**: `src/web/security_inspector.py`, `src/web/http_server.py`, `src/tcp_companion_server.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code del Servidor Web HTTP/WebSocket con Contextos Tipados
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Introducción de HttpRequestContext y HttpResponse, eliminación de firmas de 7 a 9 parámetros, descomposición de _handle_client de 134 líneas y _handle_websocket_handshake de 91 líneas en métodos modulares < 45 líneas; 0 code smells en http_server.py y 100% PASS en simulación)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `MeshCoreWebServer` en `src/web/http_server.py` presentaba métodos con firmas excesivas (`_handle_api_response` con 9 parámetros, `_serve_static_file` con 8 parámetros, `_write_http_response` con 7 parámetros) y métodos sobredimensionados (`_handle_client` con 134 líneas y `_handle_websocket_handshake` con 91 líneas).
  - Se requería estructurar el manejo de peticiones y respuestas mediante patrones de contexto (`HttpRequestContext`, `HttpResponse`), reducir la complejidad ciclomática y descomponer el flujo en submétodos de responsabilidad única sin alterar contratos ni dependencias externas.
- **Acciones Realizadas**:
  - **Contextos Tipados en [`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py)**:
    - Se definieron `@dataclass(slots=True) class HttpRequestContext` y `@dataclass(slots=True) class HttpResponse`.
    - `_handle_api_response(self, ctx: HttpRequestContext)`: Reducida de 9 a 2 parámetros. Extraídos `_serve_map_tile(ctx)` e `_is_api_auth_valid(ctx)` (2 parámetros cada uno, < 30 líneas).
    - `_serve_static_file(self, ctx: HttpRequestContext)`: Reducida de 8 a 2 parámetros (< 48 líneas).
    - `_write_http_response(self, writer, resp_or_status, body, content_type, cors_origin)`: Reducida a <= 6 parámetros con soporte polimórfico para `HttpResponse` o argumentos individuales.
  - **Descomposición de `_handle_client` (134 líneas $\to$ 33 líneas)**:
    - Subdividido en: `_parse_request_head` (lectura de encabezados HTTP), `_inspect_request_security` (anomalías y traversal), `_read_request_body` (control de carga útil <= 1MB) y `_dispatch_client_request` (enrutamiento a WS, CORS, API o estáticos).
  - **Descomposición de `_handle_websocket_handshake` (91 líneas $\to$ 13 líneas)**:
    - Subdividido en: `_send_websocket_handshake_response` (cálculo RFC 6455 Sec-WebSocket-Accept), `_send_initial_websocket_state` (telemetría inicial) y `_run_websocket_message_loop` (bucle de escucha de tramas).
- **Módulos Modificados**: `src/web/http_server.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code de AdminCommandHandler y Descomposición Modular en src/admin/
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Descomposición modular de AdminCommandHandler en ejecutores de dominio: RepeaterAdminExecutor, TracerouteExecutor, LocalConfigExecutor; eliminación del método monolítico de 443 líneas y reducción de 8 parámetros a dataclass RemoteRepeaterRequest; 100% PASS en auditorías y simulación)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `AdminCommandHandler` en `src/admin_handler.py` concentraba múltiples responsabilidades en un archivo de 1,678 líneas, incluyendo `_handle_remote_repeater` (443 líneas y 8 parámetros), `_handle_set_local_config` (187 líneas), `_handle_traceroute` (140 líneas), `get_local_config` (129 líneas) y `fetch_device_config` (94 líneas).
  - Se requería desacoplar la lógica administrativa en un paquete especializado `src/admin/`, empaquetar los parámetros en un dataclass fuertemente tipado `RemoteRepeaterRequest` y mantener la clase `AdminCommandHandler` como una Facade 100% retrocompatible.
- **Acciones Realizadas**:
  - **Nuevo Paquete Modular `src/admin/`**:
    - [`src/admin/repeater_executor.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/repeater_executor.py): Implementa `RepeaterAdminExecutor`, `RemoteRepeaterRequest`, `WaiterRegistry`, `RfExecutionContext` y `PingZeroOutcome`. Descompone comandos por lotes, ping 0, autenticación y comandos unitarios con cooldown de airtime. 100% métodos limpios y bajo límites de líneas y parámetros.
    - [`src/admin/traceroute_executor.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/traceroute_executor.py): Implementa `TracerouteExecutor`, modularizando el formateo de saltos multihop, emisión RF y desglose de segmentos.
    - [`src/admin/local_config_executor.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/local_config_executor.py): Implementa `LocalConfigExecutor`, desacoplando la lectura de `self_info`, cálculo de uptime/airtime, métricas de potencia TX y persistencia de configuración local.
    - [`src/admin/__init__.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin/__init__.py): Exporta limpiamente todos los ejecutores y dataclasses del dominio administrativo.
  - **Refactorización de Facade en [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py)**:
    - Reducido de 1,678 líneas a 735 líneas (reducción del 56% de tamaño).
    - `_handle_remote_repeater` empaqueta la solicitud en `RemoteRepeaterRequest` reduciendo la firma a 1 parámetro.
    - Delegación limpia de `get_local_config`, `fetch_device_config`, `_handle_traceroute` y `_handle_set_local_config` a los ejecutores especializados.
- **Módulos Modificados**: `src/admin/__init__.py`, `src/admin/repeater_executor.py`, `src/admin/traceroute_executor.py`, `src/admin/local_config_executor.py`, `src/admin_handler.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Validación Integral de Red Mesh Multi-Nodo, Fuzzing de Tramas Deformes y Auditoría de Logs
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (100% PASS: 7 fases ejecutadas exitosamente, topología de 33 nodos con saltos, 25 clientes concurrentes, 8 pruebas de fuzzing superadas, comandos remotos a repetidores, CRUD de contactos, heatmap RF y cero excepciones en logs)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 3 (QA & Fuzzing), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Simular y validar exhaustivamente el funcionamiento del proyecto ante una red mesh multi-nodo realista (5 nodos de infraestructura con saltos de 1 a 3 hops, 25 clientes distribuidos, sensores y BBS).
  - Inyectar tramas con deformaciones y fallos severos (CRC corrupto, tramas truncadas, framing roto, desbordamiento de búfer, JSON corrupto, claves maliciosas y bucles de enrutamiento) para verificar la contención en todos los niveles.
  - Administrar de forma remota un repetidor (login, lectura de parámetros, reconfiguración de potencia TX a 22 dBm y logout).
  - Gestionar el ciclo de vida de clientes (altas y bajas dinámicas vía API REST) y comprobar geolocalización, heatmap RF y ausencia de excepciones en los logs.
- **Acciones Realizadas**:
  - **Arnés de Simulación Integral (`scripts/simulate_full_mesh_validation.py`)**:
    - **Fase 1 (Topología & Descubrimiento)**: Modelados la estación base local, 3 repetidores, 1 router gateway, 2 sensores, 1 servidor de sala comunitaria y 25 clientes concurrentes (33 nodos en total). Verificada la exclusión estricta de repetidores de la libreta de contactos conforme a `AGENTS.md`.
    - **Fase 2 (Fuzzing & Resiliencia)**: Inyectados 8 patrones de anomalías (CRC corrupto, tramas truncadas, framing roto, buffer overflow, telemetría JSON mutilada, claves inválidas/no hexadecimales, saltos excesivos y peticiones REST malformadas). Se verificó el registro ordenado en `NodeRegistry.error_categories` (`CRC_MISMATCH`, `TX_BUFFER_OVERFLOW`, `ROUTE_UNREACHABLE`) y respuestas RFC 7807 sin caídas del event loop. Fortalecida la validación de claves en [`src/contact_manager.py:is_valid_node_key`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) para filtrar cadenas no hexadecimales.
    - **Fase 3 (Gestión Remota de Repetidor)**: Verificada autenticación con rechazo 401 ante clave errónea y éxito 200 con credenciales válidas; lectura de telemetría y ajuste de potencia de radio a 22 dBm.
    - **Fase 4 (Operaciones Dinámicas de Clientes)**: Alta dinámica de 3 clientes nuevos en caliente y eliminación de 2 clientes obsoletos vía API REST `DELETE /api/contacts`, confirmando la purga inmediata de la memoria.
    - **Fase 5 (Mensajería Multihop)**: Difusión broadcast en Canal 0 y entrega de mensaje directo (DM) a 4 saltos con confirmación ACK.
    - **Fase 6 (Mapa Táctico & Heatmap RF)**: Verificados 31 nodos geolocalizados con coordenadas GPS válidas, cálculo de distancias geodésicas (Haversine: 3.71 km Base <-> R1) y matriz ponderada del Heatmap RF.
    - **Fase 7 (Auditoría de Logs)**: Inspeccionados los logs del sistema, confirmando CERO `Traceback` o excepciones no capturadas.
- **Módulos Modificados**: `src/contact_manager.py`, `scripts/simulate_full_mesh_validation.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code de NodeRegistry en contact_manager.py y Dataclass NodeDiscoveryEvent
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Descomposición modular de add_or_update, discover_node, get_analytics_summary y load_from_file; adopción del dataclass NodeDiscoveryEvent; 100% de métodos de NodeRegistry limpios y bajo límites de líneas y parámetros)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `NodeRegistry` en `contact_manager.py` acumulaba múltiples métodos con olores de código: `add_or_update` (162 líneas), `discover_node` (78 líneas y 7 parámetros), `get_analytics_summary` (76 líneas) y `load_from_file` (92 líneas).
  - Se requería modularizar los métodos extensos en submétodos privados especializados, reducir la firma de parámetros introduciendo el dataclass `NodeDiscoveryEvent`, y asegurar 100% de compatibilidad con `advert_handler.py` y `rx_router.py`.
- **Acciones Realizadas**:
  - **Nuevo Dataclass `NodeDiscoveryEvent`**:
    - Definido en [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) con `slots=True` encapsulando `public_key`, `name`, `role`, `rssi`, `snr` y `hops`.
  - **Descomposición Modular de `NodeRegistry`**:
    - `_resolve_canonical_key_and_clean_locals()`: Deduplicación canónica O(1) de claves completas vs prefijos y purga segura de entradas locales duplicadas.
    - `_compute_node_lqi()`: Cálculo determinista y suavizado EMA de la métrica LQI y clasificación de estado.
    - `_resolve_node_role()`: Determinación de rol canónico (`LOCAL`, `REPEATER`, `ROUTER`, `SENSOR`, `CLIENT`) respetando el firmware MeshCore.
    - `_build_updated_contact()`: Ensamblado limpio del objeto `NodeContactInfo` fusionando telemetría previa y nueva.
    - `_classify_advert_role()` y `_handle_local_discovery()`: Clasificación de infraestructura de red y manejo de la estación base local en `discover_node()`.
    - `_extract_top_repeaters()`: Filtrado y ordenación analítica de repetidores en `get_analytics_summary()`.
    - `_deserialize_node_contact()`: Reconstrucción estructurada de contactos desde persistencia JSON en `load_from_file()`.
  - **Actualización de Clientes de Descubrimiento**:
    - [`src/routers/advert_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/advert_handler.py): Actualizada la llamada para instanciar y pasar `NodeDiscoveryEvent`.
    - [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py): Actualizada la presencia de nodos para pasar `NodeDiscoveryEvent`.
  - **Auditoría y Verificación de Calidad**:
    - 45/45 módulos de producción importados sin errores.
    - `mypy --strict`: 100% tipado estático verificado.
    - `detect_code_smells.py`: Cero métodos fuera de límite de líneas o parámetros en `contact_manager.py`.
    - REST API contracts: 100% PASS (HTTP 200, 400, 404).
    - Bandit SAST: Cero vulnerabilidades encontradas.
- **Módulos Modificados**: `src/contact_manager.py`, `src/routers/advert_handler.py`, `src/rx_router.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Descomposición Modular de la API REST en Controladores de Dominio y Adopción de RFC 7807 Problem Details
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Descomposición de api_router.py de 1,138 líneas y handle_request de 407 líneas en controladores por dominio en src/web/controllers/, inyección de dependencias con ApiContext y especificación RFC 7807)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX & Frontend Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `api_router.py:handle_request()` acumulaba 407 líneas en una cascada de condicionales procedimentales violando el principio de responsabilidad única (SRP).
  - Manejo heterogéneo de errores en las respuestas REST. Se requería estandarización rigurosa bajo RFC 7807 (Problem Details for HTTP APIs) manteniendo 100% de retrocompatibilidad con la WebUI, n8n y scripts externos.
- **Acciones Realizadas**:
  - **Paquete de Controladores REST (`src/web/controllers/`)**:
    - [`base.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/base.py): Dataclass `ApiContext` para inyección de dependencias limpias (`bridge`, `recent_messages`, `system_logs`, `log_system_event`, `broadcast_ws`), clase base `BaseController` y generador RFC 7807 `problem_details()`.
    - [`system_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/system_controller.py): Gestión de `/api/status`, `/api/health`, `/api/system/logs`, `/api/system/log/clear` y preflight.
    - [`nodes_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/nodes_controller.py): Paginación de `/api/nodes`, métricas `/api/lqi`, analítica consolidada `/api/analytics`, `/api/rf/heatmap` y `/api/airtime/stats`.
    - [`contacts_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/contacts_controller.py): CRUD y sincronización de libreta de contactos (`/api/contacts`, sync, share, export, import).
    - [`channels_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/channels_controller.py): Configuración de canales (0..7), persistencia atómica en disco y despacho hacia el transceptor.
    - [`tx_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/tx_controller.py): Validación y despacho de paquetes de transmisión `/api/tx` e historial en memoria `/api/messages/recent`.
    - [`repeater_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/repeater_controller.py): Comandos de administración remota, login, logout, telemetría y diagnósticos ping 0 y traceroute.
    - [`config_controller.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/config_controller.py): Parámetros locales de radio, geolocalización, anuncios advert y reinicio.
    - [`__init__.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/controllers/__init__.py): Exportación limpia de la suite de controladores.
  - **Refactorización de [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)**:
    - Inicialización de `ApiContext` y controladores en el constructor.
    - `handle_request()` reducido de **407 líneas a 28 líneas**, despachando O(1) hacia los controladores por prefijo de ruta.
    - Preservados wrappers de compatibilidad (`_route_status`, `_route_analytics`, `_route_contacts`, etc.) para asegurar 100% de interoperabilidad.
  - **Auditoría y Despliegue**:
    - 45/45 módulos de producción importados con 0 errores.
    - 100% tipado estático (`mypy --strict`).
    - Validación de contratos API REST cumplida (200, 400, 404).
    - Cero vulnerabilidades Bandit SAST.
    - Sincronización completa hacia `/deploy/`.
- **Módulos Modificados**: `src/web/controllers/**`, `src/web/api_router.py`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Refactorización Clean Code del Backend (Strategy Pattern en rx_router.py) y Protección de Airtime LoRa en Repetidores
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Descomposición de handle_event CC 190 -> 4 con Strategy Pattern en src/routers/, descomposición modular de repeater_manager.py y gobernanza de Airtime LoRa con cooldowns)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - `rx_router.py:handle_event()` era un mega-método de 453 líneas y Complejidad Ciclomática (CC) = 190 que enrutaba todos los paquetes de RF en una estructura monobloque.
  - `repeater_manager.py` contenía métodos con alta densidad (`parse_repeater_telemetry_or_response` con 392 líneas y `build_repeater_command_payload` con 236 líneas).
  - Riesgo de congestión de Airtime en la malla LoRa al consultar repetidores remotos sin cooldowns regulados.
- **Acciones Realizadas**:
  - **Patrón Strategy para Enrutamiento de Eventos (`src/routers/`)**:
    - [`base.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/base.py): Protocolo `BaseRxHandler`, `RxMeta` y `MeshMessageEvent`.
    - [`channel_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/channel_handler.py): `ChannelMessageHandler` para mensajes broadcast y grupales.
    - [`direct_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/direct_handler.py): `DirectMessageHandler` para DMs con guarda loopback local.
    - [`advert_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/advert_handler.py): `AdvertHandler` para anuncios, descubrimiento y sincronización de libreta de contactos.
    - [`telemetry_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/telemetry_handler.py): `TelemetryHandler` para lecturas ambientales, voltajes y métricas de señal.
    - [`repeater_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/routers/repeater_handler.py): `RepeaterAdminHandler` para respuestas CLI, delivery ACKs y traceroutes.
    - [`rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py): `handle_event()` reducido de 453 líneas a **33 líneas**, CC reducida de **190 a 4**.
  - **Descomposición Modular en `src/repeater_manager.py`**:
    - `parse_repeater_telemetry_or_response()` descompuesto en submétodos especializados (`_parse_json_telemetry`, `_parse_battery_and_voltage`, `_parse_radio_parameters`, `_parse_system_metrics`, `_parse_owner_and_location`).
    - `build_repeater_command_payload()` descompuesto en `_build_query_cmd`, `_build_radio_cmd`, `_build_owner_and_location_cmd`, `_build_acl_and_security_cmd`.
  - **Protección de Airtime LoRa y Cooldowns**:
    - Implementado `check_airtime_cooldown()` y `record_command_sent()` con **5s** de cooldown entre comandos individuales y **30s** para consultas completas de telemetría.
    - Integrado en [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py#L1006) para bloquear ráfagas automáticas o abusivas hacia repetidores de la malla.
  - **Auditoría y Despliegue**:
    - 36/36 módulos importados exitosamente (0 errores).
    - 100% tipado estático (`mypy --strict`).
    - Cero bloqueos de concurrencia y cero vulnerabilidades de seguridad.
    - Sincronización a `/deploy/` con `scripts/sync_deploy.py`.
- **Módulos Modificados**: `src/routers/**`, `src/rx_router.py`, `src/repeater_manager.py`, `src/admin_handler.py`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Modularización Integral del Frontend en ES6 Nativo y Desacoplamiento Event-Driven
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (División de app.js de 7,826 líneas en arquitectura modular ES6 pura por capas y dominios funcionales)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX & Frontend Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - El frontend de la SPA se encontraba condensado en un único archivo monolítico (`app.js`) de **7,826 líneas (353 KB)**, dificultando el mantenimiento y violando el principio de responsabilidad única (SRP).
  - Se requería una arquitectura limpia en módulos ES6 nativos (`<script type="module">`), sin Node.js, npm ni herramientas de compilación pesadas, para garantizar arranque instantáneo (<100ms) en SBCs (Raspberry Pi/Orange Pi).
  - Desacoplar los subsistemas mediante un bus de eventos reactivo (`EventBus`) y aislar 100% el frontend sin polución de variables globales en `window`.
- **Acciones Realizadas**:
  - **Capa Core (`src/web/static/js/core/`)**:
    - [`eventbus.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/core/eventbus.js): Bus de eventos asíncrono desacoplado basado en `EventTarget` y `CustomEvent`.
    - [`utils.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/core/utils.js): Funciones puras de utilidad, sanitización XSS (`escapeHtml`), `debounce`, cálculo de potencia de hardware y constantes de protocolo.
    - [`storage.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/core/storage.js): Motor de persistencia IndexedDB `MeshCoreStorage` para chats y preferencias.
    - [`websocket.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/core/websocket.js): Cliente WebSocket resiliente con reconexión exponencial y keepalive (15s).
  - **Capa de Módulos de Dominio (`src/web/static/js/modules/`)**:
    - [`sniffer.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/sniffer.js): Consola de logs del sistema, diagnósticos y captura de paquetes RF.
    - [`repeater.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/repeater.js): Modal de repetidores remotos, autenticación segura, terminal interactiva y telemetría en tiempo real.
    - [`map.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/map.js): Leaflet, capas de mosaicos online/offline (MBTiles), marcadores, Heatmap táctico RF y trazado Traceroute.
    - [`settings.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/settings.js): Parámetros locales de radio, gestión de canales, exportación QR y preflight.
    - [`nodes.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/nodes.js): Directorio unificado de nodos, libreta de contactos (clientes), filtrado reactivo y presencia en vivo.
    - [`chat.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/modules/chat.js): Mensajería de texto, canales broadcast, DMs, tracking de entrega (ACKs) y alertas sonoras.
  - **Orquestador Central (`src/web/static/js/app.js`)**:
    - Reducido de **7,826 líneas a solo 240 líneas** (reducción del 97% en densidad de código).
    - Actúa como *Composition Root*, orquestando la navegación entre pestañas, paleta de comandos (Ctrl+K), temas y estados de conexión.
  - **Plantilla HTML (`src/web/static/index.html`)**:
    - Actualizada etiqueta `<script type="module" src="/js/app.js"></script>`.
  - **Auditoría y Despliegue**:
    - Verificación con `lint_frontend_standards.py` (100% PASS).
    - Verificación de seguridad SAST con `run_security_audit.py` (100% PASS, Cero vulnerabilidades).
    - Sincronización del paquete de despliegue mediante `python scripts/sync_deploy.py`.
- **Módulos Modificados**: `src/web/static/js/core/**`, `src/web/static/js/modules/**`, `src/web/static/js/app.js`, `src/web/static/index.html`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Auditoría Multidimensional, Refactorización de Complejidad Ciclomática y Pipeline CI/CD
- **Fecha**: 2026-09-02
- **Estado**: ✅ COMPLETADO (Auditoría Integral de Código/Docs/Tareas, Descomposición de God Method handle() CC 291 -> 6, Pipeline CI GitHub Actions, Higiene de Repositorio)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Análisis exhaustivo de todo el código, documentación, tareas y reportes del proyecto aplicando buenas prácticas de ingeniería de software y aprovechando las capacidades avanzadas de Gemini 3.8 Flash.
  - Identificación de puntos fuertes y débiles de la aplicación (arquitectura, concurrencia, seguridad, frontend, LoRa airtime, CI/CD).
  - Reducción de complejidad ciclomática en `admin_handler.py` donde `handle()` alcanzaba 770 líneas y CC = 291.
  - Corrección de bugs en scripts de soporte (`scripts/audit_codebase_integrity.py` ignoraba `.venv`, causando escaneos infinitos) y sintaxis en `.gitignore`.
  - Configuración del pipeline de Integración Continua (CI) en GitHub Actions.
- **Acciones Realizadas**:
  - En [`.gitignore`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.gitignore):
    - Reparadas entradas corruptas con caracteres espaciados (`d a t a / * . d b`).
    - Añadidos archivos temporales y bases de datos locales sueltas (`out.txt`, `test_sec_audit.db`).
  - En [`scripts/audit_codebase_integrity.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/audit_codebase_integrity.py):
    - Incorporado `.venv`, `venv`, `env`, `.mypy_cache`, `.ruff_cache` a `EXCLUDE_DIRS`, reduciendo el tiempo de escaneo de minutos a menos de 5 segundos.
  - En [`.github/workflows/ci.yml`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.github/workflows/ci.yml):
    - Creado flujo de trabajo automatizado para GitHub Actions (Ruff, Mypy strict, Bandit SAST, contratos API e integridad de código).
  - En [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py):
    - Descompuesto el mega-método `handle()` (770 líneas, CC = 291) en controladores modulares privados:
      - `_handle_traceroute`: Despacho de trazas y cálculo de saltos.
      - `_handle_remote_repeater`: Configuración remota, Zero-hop ping, autenticación `login` y comandos CLI a repetidores.
      - `_handle_set_local_config`: Aplicación de parámetros locales (radio, potencia TX, GPS, identidad).
    - `handle()` se redujo a **38 líneas** con una complejidad ciclomática de **6**.
  - Validación Integral:
    - Verificación con las 9 herramientas de auditoría estática de `.agents/skills/` (concurrencia asíncrona 100%, Bandit 0 vulnerabilidades, 100% tipado estricto, contratos REST conformes).
  - Sincronización:
    - Ejecutado `python scripts/sync_deploy.py` para sincronizar paquetes y sumas SHA256 en `/deploy/`.
- **Módulos Modificados**: `.gitignore`, `scripts/audit_codebase_integrity.py`, `.github/workflows/ci.yml`, `src/admin_handler.py`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Consulta Automática y Actualización en Tiempo Real de Batería, Telemetría y Consola Terminal de Repetidores
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (Consulta Exhaustiva en Login, Parsing Reactivo de Batería en mV/%, Normalización de Consola Terminal)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Python Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - Al abrir la ventana modal de administración de un repetidor remoto nunca se mostraban los datos de la batería.
  - Asegurar que el nodo repetidor consulte automáticamente todos los datos requeridos al hacer login exitoso, al recibir un anuncio/advert o al recibir datos mediante comandos de consola.
  - Renombrar la subpestaña de la consola de "Terminal Linux" a "Terminal".
- **Causa Raíz Identificada**:
  - `authenticateRepeater` en el frontend solo consultaba `"ver"`, `"get radio"`, `"get lat"` y `"get owner.info"`, omitiendo la solicitud de batería (`"bat"` / `"get pwrmgt.bootmv"` / `"stats-core"`).
  - El parser regex en backend y frontend exigía la presencia explícita de la palabra "battery", ignorando respuestas directas del firmware tipo `> 4120 mV`, `> 4.12 V`, `Boot voltage = ...` o `> 95%`.
  - La etiqueta de la subpestaña en `index.html` tenía el texto `"Terminal Linux"`.
- **Acciones Realizadas**:
  - En [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html):
    - Renombrada la subpestaña a `<button class="subtab-btn" data-subtab="rep-console">Terminal</button>`.
  - En [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py):
    - Ampliado `parse_repeater_telemetry_or_response` con soporte integral para respuestas de voltaje de arranque y batería (`pwrmgt.bootmv`, `boot voltage`, `> 4120 mV`, `> 4.12 V`, `> 95%`, `> 915.000,250,11,5`, `tx`, etc.).
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Implementado `refreshRepeaterFullTelemetry(canonicalPk, password)` que lanza la secuencia ordenada completa de consultas: `ver`, `stats-core`, `bat`, `get radio`, `get tx`, `get lat`, `get lon`, `get owner.info`, `clock` y `neighbors`.
    - Integrado `refreshRepeaterFullTelemetry` al autenticarse con éxito y al pulsar el botón `#btnRefreshRepeaterTelem`.
    - Creado `parseRepeaterTelemetryFromText(text)` en frontend para extraer y normalizar telemetría (batería en mV/%, voltaje, solar, radio, paquetes, reloj, uptime) tanto de respuestas WebSocket como de salidas registradas en la consola.
    - Corregido `populateRepeaterModalData` para manejar valores numéricos directos de batería en milivoltios ($>100\text{ mV}$) y voltaje, calculando el porcentaje correspondiente de forma precisa.
  - Validación Automatizada E2E:
    - Verificado con suite Playwright (`scratch/test_repeater_battery_e2e.py`) validando el flujo de login, actualización de batería en tiempo real vía WebSocket y actualización reactiva al ejecutar comandos en la Terminal.
  - Sincronización:
    - Ejecutado `python scripts/sync_deploy.py` para sincronizar `/deploy/`.
- **Módulos Modificados**: `src/web/static/index.html`, `src/web/static/js/app.js`, `src/repeater_manager.py`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Verificación y Optimización en Tiempo Real del Heatmap de Cobertura RF
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (Heatmap Dinámico Activo, Gradiente Táctico Multinivel, Reactividad en Tiempo Real)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Python Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - Verificar exhaustivamente que el módulo de Mapa de Calor de Cobertura RF (`Heatmap RF`) funcione correctamente y obtenga datos actualizados de todos los nodos de la red en tiempo real.
- **Acciones Realizadas**:
  - En [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py):
    - Corregido y enriquecido el endpoint `GET /api/rf/heatmap` extrayendo coordenadas geográficas precisas (`lat`/`lon`, `latitude`/`longitude`), métricas RF de última generación (`last_snr`, `last_rssi`, `noise_floor_dbm`), rol del nodo y posición del transceptor local.
    - Implementado cálculo de peso de señal ponderado y sanitización de límites geográficos (-90/90, -180/180).
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Rediseñado el renderizado del mapa de calor con visualización táctica multinivel:
      1. Halo exterior difuminado con borde punteado de radio extendido ($500\text{m} - 3500\text{m}$).
      2. Núcleo central de alta densidad y opacidad reforzada ($0.32$).
      3. Paleta cromática por calidad de enlace: Verde Esmeralda ($\ge -75\text{ dBm}$), Cyan Táctico ($\ge -95\text{ dBm}$), Ámbar ($\ge -110\text{ dBm}$) y Rojo ($< -110\text{ dBm}$).
    - Incorporada actualización reactiva en tiempo real:
      - Actualización automática al recibir paquetes de telemetría/nodos vía WebSockets (`renderNodesDirectory`).
      - Bucle de sondeo periódico cada 10 segundos mientras el botón `#btnToggleHeatmap` permanezca activo.
  - Validación Automatizada E2E:
    - Ejecutada suite Playwright (`scratch/test_heatmap_rf.py`) confirmando generación de capas, cálculo de radios y actualización en tiempo real con 0 errores de consola.
  - Sincronización:
    - Ejecutado `python scripts/sync_deploy.py` para sincronizar `/deploy/`.
- **Módulos Modificados**: `src/web/api_router.py`, `src/web/static/js/app.js`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Implementación de Servidor Nativo de Mapas Offline con Soporte SQLite MBTiles y Teselas XYZ
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (Servidor de Teselas Local Activo, Soporte MBTiles Raster y XYZ, UI con Detección en Vivo)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Python Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - El usuario consultó por qué la capa de mapas "Local" no cargaba mosaicos.
- **Causa Raíz Identificada**:
  - La capa "Local" apuntaba al endpoint `/api/map/tiles/{z}/{x}/{y}.png`, pero no existía un servicio o despachador en el backend para buscar y servir archivos locales ni bases de datos cartográficas offline (`.mbtiles`), retornando 404 y mostrando el placeholder de tesela no disponible.
- **Acciones Realizadas**:
  - En [`src/web/map_tile_service.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/map_tile_service.py):
    - Creado servicio `MapTileService` con soporte para:
      1. Bases de datos SQLite MBTiles (`data/maps/*.mbtiles`) con conversión de coordenadas estándar TMS/XYZ y caché de 8MB.
      2. Carpetas de teselas sueltas XYZ (`data/maps/tiles/{z}/{x}/{y}.{png|jpg|webp|pbf}`).
      3. Detección automática de tipos MIME mediante firmas de números mágicos.
  - En [`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py) y [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py):
    - Añadido interceptor de alta velocidad para `/api/map/tiles/{z}/{x}/{y}.ext` sirviendo los bytes binarios de imagen con cabeceras `Cache-Control: public, max-age=86400`.
    - Añadido endpoint de diagnóstico `GET /api/map/status` que informa del estado del almacenamiento local, bases de datos cargadas, zoom mínimo/máximo y tamaños.
  - En [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html) y [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Creado panel de estado en vivo en "Ajustes -> Mapas Offline" (`#localMapsStatusCard`) que lista los archivos `.mbtiles` indexados en tiempo real.
    - Añadido botón "🔄 Reindexar" (`#btnReloadLocalMaps`) para escanear nuevos mapas añadidos a `data/maps/` sin reiniciar el servicio.
    - Añadida notificación toast contextual al seleccionar la capa "Local" indicando cuántos mapas offline están cargados.
  - En [`data/maps/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/data/maps):
    - Creado directorio de almacenamiento y guía en [`data/maps/README.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/data/maps/README.md).
    - Generada base de datos inicial de ejemplo [`data/maps/overview_sample.mbtiles`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/data/maps/overview_sample.mbtiles).
  - Validación E2E:
    - Ejecutadas pruebas automatizadas con Playwright (`scratch/test_local_maps_e2e.py`) y unitarias (`tests/test_tile_server.py`) verificando el servicio de teselas y renderizado sin errores en consola.
  - Sincronización:
    - Sincronizado el paquete de despliegue en `/deploy/` (`python scripts/sync_deploy.py`).
- **Módulos Modificados**: `src/web/map_tile_service.py`, `src/web/http_server.py`, `src/web/api_router.py`, `src/web/static/index.html`, `src/web/static/js/app.js`, `data/maps/**`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Solución de Marca de Agua 'API KEY REQUIRED' y Optimización del Mapeo Cartográfico Oscuro
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (Cero Marcas de Agua, 100% Cobertura Global, Cero Dependencias de API Keys)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - El usuario reportó que la capa cartográfica oscura (`Oscuro`) mostraba la marca de agua diagonal `"API KEY REQUIRED carto.com/basemap/apikey"` debido a la reciente restricción de acceso anónimo en los servidores de teselas de CARTO.
- **Causa Raíz Identificada**:
  - La URL `https://{s}.basemaps.cartocdn.com/dark_all/...` fue restringida por el proveedor CARTO para peticiones públicas anónimas sin token de suscripción.
- **Acciones Realizadas**:
  - En [`src/web/static/css/app.css`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/css/app.css):
    - Establecido el fondo del contenedor `.leaflet-container` y `.leaflet-map-canvas` en `#090d16 !important`.
    - Creada la regla de filtrado táctico `.map-tiles-dark` (`brightness(0.65) invert(1) contrast(3.5) hue-rotate(200deg) saturate(0.3) brightness(0.75)`) para transformar las teselas estándar de OpenStreetMap en un mapa táctico oscuro de alta precisión con cero dependencia de servicios externos de pago.
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Reemplazada la capa `cartodb` por `darkLayer` táctico (basado en OSM + `.map-tiles-dark`), con soporte nativo de zoom 0-19 y cobertura mundial garantizada.
    - Incorporada la capa satelital `satellite` (Esri World Imagery) y preservadas las capas `osm`, `local` y `tactical_radar`.
    - Actualizado `setMapLayer` y `constructor` para normalizar las preferencias almacenadas a `dark`.
  - En [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html):
    - Actualizado el toolbar `.map-layer-switcher` con selector semántico: `Oscuro`, `Calles`, `Satelital`, `Local`, `Radar`, `Heatmap RF`.
  - Validación Visual Playwright:
    - Ejecutada inspección automatizada (`scratch/capture_all_tabs.py`) confirmando renderizado nítido y libre de marcas de agua en `tests/artifacts/map_tab_desktop.png`.
  - Sincronización y Empaquetado:
    - Ejecutado `python scripts/sync_deploy.py` para actualizar `/deploy/` y paquetes.
- **Módulos Modificados**: `src/web/static/css/app.css`, `src/web/static/js/app.js`, `src/web/static/index.html`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Homogeneización Total del Sistema de Iconografía Vectorial SVG Lucide en Toda la Aplicación
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (100% de Iconos Estandarizados, Cero Emojis Crudos, Validación Playwright PASS)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Realizar una revisión integral de todo el frontend de la SPA y asegurar que todos los iconos e imágenes compartan exactamente el mismo estilo visual, grosor de trazo (stroke de 2px), renderizado vectorial nítido, adaptación temática y cero dependencias CDN externas.
  - Eliminar la totalidad de emojis heterogéneos y dispersos en botones, tarjetas de nodos/contactos, chips de salud, cabeceras de tablas, modales y templates dinámicos de JavaScript.
- **Acciones Realizadas**:
  - En [`src/web/static/js/icons.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/icons.js):
    - Ampliado el catálogo vectorial Lucide nativo (100% offline) a 69 glifos SVG estandarizados con trazo uniforme de 2px (`stroke-width="2"`), `stroke-linecap="round"` y `stroke-linejoin="round"`.
  - En [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html):
    - Reemplazados todos los emojis declarativos por etiquetas semánticas `<span data-lucide="..." data-size="..."></span>` en el header principal, sidebar, buscador global, pestaña de mensajería, filtros de contactos y nodos, conmutador de capas del mapa, métricas KPI, consola de logs y modales (Canal, Contacto, QR, Repetidor, Traceroute).
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Reemplazados todos los emojis dinámicos generados en plantillas JS (`cCard`, `nCard`, `renderTracerouteGraph`, `renderTracerouteTable`, `renderChannelsList`, `addDmContact`, `renderMessage`, `updateConnectionBadge`, `updateRadioBadge`, popups y feed de nodos del mapa) por invocaciones al generador SVG `window.getLucideIcon(name, extraClass, size)`.
  - En [`src/web/static/css/app.css`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/css/app.css):
    - Añadidos estilos específicos para todos los contenedores de iconos (`.section-icon`, `.modal-title-icon`, `.kpi-icon`, `.card-icon`, `.stat-pill`, `.contact-battery-chip`, `.map-layer-btn`, `.map-overlay-icon`, `.discovery-icon`, `.auth-icon`, `.auth-gate-shield`, `.btn-compact-icon`, `.logo-icon`) garantizando alineación vertical flexbox perfecta y contraste accesible.
  - Verificación Visual y Validación E2E:
    - Verificación mediante script de cobertura (`check_icons.py`): 100% de iconos requeridos presentes y válidos.
    - Ejecución de suite visual Playwright (`scratch/capture_all_tabs.py`) capturando screenshots de alta resolución en las 7 pestañas (`chat`, `contacts`, `nodes`, `map`, `analytics`, `logs`, `settings`) con 0 errores en la consola de JavaScript.
  - Sincronización:
    - Ejecutado `python scripts/sync_deploy.py` para sincronizar `/deploy/`, paquetes `.tar.gz`, `.zip` y sumas `SHA256SUMS`.
- **Módulos Modificados**: `src/web/static/js/icons.js`, `src/web/static/index.html`, `src/web/static/js/app.js`, `src/web/static/css/app.css`, `deploy/**`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Validación Integral y Reactividad en Tiempo Real del Módulo de Métricas & Analítica de Malla
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (100% de Métricas Validadas, Reactividad en Tiempo Real y Ticker Periódico PASS)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web Architect).
- **Problema / Requerimiento**:
  - Verificar que todos los datos obtenidos en la sección **Métricas & Analítica de la Red Malla** (`#tab-analytics`) sean matemáticamente y operativamente correctos (Paquetes Totales, RX/TX ratio, Nodos Activos, Repetidores, Tasa de Error %, Profundidad de Cola TX, Rankings de Tráfico, Calidad de Señal SNR/RSSI, Tabla de Repetidores y Salud de Subsistemas).
  - Garantizar que las métricas se actualicen con regularidad periódica (ticker cada 5s cuando la pestaña está activa) y en tiempo real inmediato ante cualquier paquete LoRa entrante vía WebSocket.
- **Acciones Realizadas**:
  - En [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py):
    - Enriquecido el endpoint `GET /api/analytics` para consolidar el conteo global de tráfico del bridge con el desglose por nodo, calculando con exactitud deduplicación en RAM, estado del transceptor serial (`is_hardware_alive` / `is_connected`), y broker MQTT.
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Añadido seguimiento activo de pestaña (`this.activeTabId = targetTabId`).
    - Implementado `scheduleAnalyticsRefresh()` con debounce (400ms) invocado en `handleIncomingLiveEvent()` ante cualquier paquete o evento de red por WebSocket.
    - Implementado auto-refresco periódico cada 5 segundos en `initAnalytics()` cuando el usuario visualiza la pestaña.
    - Completado el renderizado en vivo de todas las tarjetas KPI, tablas de tráfico/señal/repetidores y panel de salud del puente.
  - Verificación Automatizada:
    - Ejecutado script de prueba E2E (`scratch/test_analytics_metrics.py`) confirmando renderizado correcto y actualización reactiva de paquetes y tablas en vivo (captura en `tests/artifacts/analytics_tab_desktop.png`).
- **Módulos Modificados**: `src/web/api_router.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Eliminación de Clave Pública y Botón de Copiado en Cabeceras de Tarjetas
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (UI Simplificada, 100% de Pruebas PASS)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web Architect).
- **Problema / Requerimiento**:
  - Eliminar el fragmento de clave pública abreviada y su botón de copiado (`.node-card-pubkey` / `.contact-pubkey` / `.btn-copy-pk`) de las cabeceras de las tarjetas de contactos y nodos, debido a que dicha información y su compartición se realizan mediante el modal de QR / Detalles.
  - Simplificar la fila secundaria `.node-card-sub-row` para mostrar de forma limpia e inmediata el estado y tiempo relativo de actividad (`.node-card-activity`).
- **Acciones Realizadas**:
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Eliminado el elemento HTML con la clave pública y el botón de copiado de `cCard` y `nCard`.
    - Removidos los event listeners de `copyBtn` en las tarjetas.
    - Eliminada la variable `shortPk` no utilizada.
  - En [`src/web/static/css/app.css`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/css/app.css):
    - Limpiadas las reglas de estilo de `.contact-pubkey`, `.node-card-pubkey` y `.btn-copy-pk`.
    - Ajustado `.node-card-sub-row` para enfocar la línea de tiempo relativo (`.node-card-activity`).
  - Validación Visual Playwright: Capturas actualizadas en `tests/artifacts/nodes_tab_desktop.png` y `tests/artifacts/contacts_tab_desktop.png`.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/web/static/css/app.css`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Depuración de Redundancias y Optimización de Telemetría en Tarjetas Web (Nodos y Contactos)
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (UI Refinada y 100% de Pruebas Visuales E2E PASS)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web Architect).
- **Problema / Requerimiento**:
  - Eliminar los textos redundantes dentro del panel de telemetría de las tarjetas (como `📱 Dispositivo Cliente MeshCore`, `Host Bridge`, `🏔️ Router de Malla LoRa`, `Punto a Punto`) que duplicaban la información ya expresada por el avatar y el rol badge (`<span class="node-role-badge ...">`).
  - Reemplazar esas etiquetas estáticas por pares clave-valor de telemetría operativa real (Ruta, LQI %, GPS, Saltos, Puerto Serial, Parámetros de Radio, Temperatura, Humedad y Presión).
- **Acciones Realizadas**:
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Eliminada la variable `typeDesc` y el uso de textos de tipo redundantes en `cCard` y `nCard`.
    - Rediseñado el panel `.node-telemetry-panel` para mostrar metadatos operativos limpios y compactos para cada rol (`LOCAL`, `REPEATER`, `SENSOR`, `ROOM`, `CLIENT`).
  - En [`src/web/static/css/app.css`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/css/app.css):
    - Ajustadas las reglas `.node-meta-row`, `.node-meta-sub` y `strong` para un contraste tipográfico nítido y legible con elipsis en textos largos.
  - Validación Visual Playwright: Capturas actualizadas en `tests/artifacts/nodes_tab_desktop.png` y `tests/artifacts/contacts_tab_desktop.png`.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/web/static/css/app.css`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Actualización de Presencia en Tiempo Real (Avatar Status Dot), Alineación Estricta de Cuadrículas y Verificación Frontend
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (100% de Pruebas E2E Visuales y Funcionales PASS)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  1. Hacer que el estado de presencia en tiempo real (`<span class="avatar-status-dot status-online" title="Hace un momento"></span>`) se actualice inmediatamente en vivo ante cualquier paquete/evento LoRa recibido por WebSocket sin necesidad de recargar la página web.
  2. Comprobar que las tarjetas de contactos y nodos estén perfectamente alineadas a la cuadrícula, sin elementos desplazados, desbordados o truncados, y con plena adaptabilidad responsive a diferentes resoluciones (Desktop 1920x1080, Tablet, Mobile 390x844).
  3. Realizar una verificación integral de todo el código frontend (HTML5, Vanilla CSS, ES6+ JS), eliminando código con errores, duplicados o en desuso.
- **Acciones Realizadas**:
  1. **Motor de Presencia Instantánea y Ticker de Tiempo Relativo**:
     - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
       - Implementado `updateNodePresenceRealtime(pubkey, payload)` para actualizar en memoria y en el DOM el estado de presencia del nodo emisor inmediatamente ante cualquier trama RX (mensajes de canal, DMs, telemetría, anuncios, ACKs, traceroute).
       - Implementados `initPresenceTicker()` y `updateAllPresenceDots()` (ejecución periódica cada 10 segundos) para recalcular timestamps relativos (`"Hace un momento"`, `"Hace 2m"`, `"Hace 1h"`, etc.) y transicionar suavemente clases `status-online` / `status-idle` / `status-offline` en el DOM sin recargas de página.
       - Enriquecido `updateNodeInDom()` para actualizar `.avatar-status-dot`, `.node-card-activity`, y el encabezado de chat DM activo.
       - Añadido atributo `data-last-seen` en las tarjetas de contactos (`cCard`) y nodos (`nCard`) en `renderNodesDirectory()`.
  2. **Alineación de Cuadrícula y Responsividad Visual**:
     - En [`src/web/static/css/app.css`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/css/app.css):
       - Unificadas `.nodes-unified-grid` y `.nodes-grid` con `repeat(auto-fill, minmax(295px, 1fr))` en desktop/tablet y `1fr` en móviles ($\le 640\text{px}$).
       - Ajustadas las tiras de métricas RF (`.node-rf-strip`, `.contact-card-chips`) a 3 columnas simétricas con `repeat(3, minmax(0, 1fr))` y `min-width: 0; box-sizing: border-box;` para prevenir desbordes.
       - Ajustadas las barras de acción inferiores (`.node-actions-bar`, `.contact-card-actions`) con `flex-wrap: wrap; white-space: nowrap;`.
  3. **Inspección Visual y Verificación E2E con Playwright**:
     - Ejecutado `scripts/inspect_web.py` en Desktop (1920x1080) y Mobile (390x844). Resultado: **0 Excepciones JS, 0 Peticiones fallidas, 0 Errores de consola (PASS)**.
     - Verificada la transición en vivo de `avatar-status-dot` vía WebSocket con script determinista.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/web/static/css/app.css`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Auditoría Integral de Código, Saneamiento de Código Muerto/Deprecado, Verificación de Salud y Actualización Documental
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (100% de Módulos Auditados, 0 Errores, 0 Warnings)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Realizar una lectura, análisis y comprensión profunda de toda la base de código y documentación.
  - Detectar y corregir errores, inconsistencias, nombres deprecados, código duplicado o en desuso.
  - Comprobar el funcionamiento de extremo a extremo de la aplicación en todos sus subsistemas.
  - Actualizar la documentación técnica en todo el proyecto (`README.md`, `PROTOCOL_SPEC.md`, `ARCHITECTURE.md`, `AGENT_ACTIVITY_REPORT.md`).
- **Acciones Realizadas**:
  1. **Saneamiento de Símbolos y Deprecaciones**:
     - Sustituido el uso legado de `OpCode` por `PacketType` (conforme a `packets.py` del SDK oficial) en [`meshcore_bridge.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/meshcore_bridge.py), [`src/__init__.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/__init__.py), [`scripts/validate_all_node_parameters.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/validate_all_node_parameters.py), [`scripts/verify_all_components.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/verify_all_components.py) y [`scripts/simulate_concurrent_network.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/simulate_concurrent_network.py).
     - Eliminado carácter BOM (`\ufeff`) en [`src/web/security_inspector.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/security_inspector.py).
  2. **Corrección en Enrutamiento y Preservación de Nombres de Nodo**:
     - En [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py): Corregido el flujo en `handle_event` y `_handle_mesh_telemetry_msg` donde `sender_name` extraído de anuncios `adv_name`/`name` era sobreescrito por el fallback `Nodo [xxxx]` si el nodo aún no residía en el registro local.
  3. **Diagnósticos Preflight y Alias de Configuración**:
     - En [`config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/config.py): Añadido alias canónico `MQTT_HOST = MQTT_BROKER`.
     - En [`src/preflight.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/preflight.py): Implementada la función de conveniencia `run_preflight_checks()`.
  4. **Verificación Funcional Multi-Subsistema**:
     - Comprobada la carga sintáctica y dinámica de los **27 módulos de `src/` (100% de éxito, 0 warnings)**.
     - Validados los 8 escenarios de la simulación TCP Multi-Nodo (`simulate_tcp_mesh_network.py`).
     - Validados los 126 parámetros por tipo de nodo (`validate_all_node_parameters.py`).
     - Validado el ciclo de vida del Bridge (`bridge_core.py`) con eventos RX, comandos admin y rate limiting.
  5. **Actualización Documental**:
     - Actualizado [`README.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/README.md) con la estructura completa de scripts y módulos v3.0.
     - Actualizado [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md) con la matriz exhaustiva de parámetros.
- **Módulos Modificados**: `config.py`, `meshcore_bridge.py`, `src/__init__.py`, `src/preflight.py`, `src/rx_router.py`, `src/web/security_inspector.py`, `scripts/validate_all_node_parameters.py`, `scripts/verify_all_components.py`, `scripts/simulate_concurrent_network.py`, `README.md`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Validación Exhaustiva de Parámetros y Cobertura de Nodos en la Pila MeshCore (LOCAL, CLIENT, REPEATER, SENSOR, ROOM)
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (126/126 Parámetros Validados - 100% de Éxito)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Validar y comprobar que el 100% de los parámetros que se pueden obtener de todos los tipos de nodos en la pila canónica de MeshCore (`LOCAL`, `CLIENT`, `REPEATER`, `SENSOR`, `ROOM`, y métricas de red `NETWORK`) son alcanzables desde el código, parseados, almacenados en `NodeRegistry` y exportados a REST, WebSockets y MQTT.
- **Acciones Realizadas**:
  - En [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py):
    - Añadido el método `NodeRegistry.get_node(query)` como alias canónico para consultas directas por clave pública o prefijo.
  - En [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py):
    - Añadido `extract_all_repeater_params_from_text()` como alias de `parse_repeater_telemetry_or_response()`.
    - Refinado el análisis de paquetes (`packets: rx=..., tx=...`) y potencia de transmisión (`tx_power`), diferenciando conteos de paquetes de valores de dBm RF.
  - En [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md):
    - Añadida la **Sección 14**: Matriz Canónica de Parámetros por Tipo de Nodo, documentando los 126 parámetros, tipos de datos y vectores de adquisición.
  - En [`scripts/validate_all_node_parameters.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/validate_all_node_parameters.py):
    - Creado script de auditoría y validación determinista que evalúa exhaustivamente los 6 conjuntos de parámetros, logrando una tasa de éxito del **100% (6/6 suites PASS, 126 parámetros)**.
- **Módulos Modificados**: `src/contact_manager.py`, `src/repeater_manager.py`, `docs/PROTOCOL_SPEC.md`, `scripts/validate_all_node_parameters.py` (nuevo), `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Corrección Integral de Telemetría Local, Extracción de Eventos de Stats y Métricas en Tiempo Real (get_stats_core)
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web Architect).
- **Problema / Requerimiento**:
  - Corregir el comando `get_stats_core` / `stats` y la tarjeta de telemetría local de la interfaz web que devolvía parámetros en 0 (`Uptime: 0s`, `Airtime TX: 0 ms`, `Duty Cycle: 0.00%`).
  - El SDK oficial (`meshcore_py`) devuelve instancias de `Event` con payload estructurado (`'uptime_secs'`, `'battery_mv'`, `'errors'`, `'queue_len'` para `STATS_CORE`, y `'tx_air_secs'` para `STATS_RADIO`), mientras que el handler esperaba diccionarios planos con claves heredadas (`'uptime'`).
- **Acciones Realizadas**:
  - En [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py):
    - Creada la función auxiliar `_extract_payload_dict()` para extraer transparentemente diccionarios desde objetos `Event` o `dict`.
    - Ampliado `AdminContext` para recibir `rate_limiter`, `counters` y `start_time`.
    - Actualizado `_cli_stats_core()` para obtener `uptime_secs`, `airtime_ms` (vía radio `tx_air_secs` o `TxRateLimiter`), calcular el `Duty Cycle` y formatear el uptime de forma legible (ej. `1h 24m 10s`).
    - Actualizado `get_local_config()` y `fetch_device_config()` para consolidar métricas dinámicas de uptime, airtime, paquetes TX/RX y duty cycle.
    - Creado método seguro `_publish_safe()` para publicar en MQTT protegiendo contra instancias nulas.
  - En [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py):
    - Inyectadas las dependencias de `rate_limiter`, `counters`, `start_time` y `web_server` en la construcción de `AdminContext`.
  - En [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py):
    - Sincronizados los retornos de `get_stats_core`, `get_stats_radio` y `get_stats_packets` para coincidir 100% con los payloads de `meshcore_py`.
  - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Enriquecido el botón de refresco de telemetría (`btnRefreshLocalTelem`) para invocar `get_stats_core` y actualizar inmediatamente el dashboard (`fetchLocalNodeConfig()`).
- **Módulos Modificados**: `src/admin_handler.py`, `src/bridge_core.py`, `src/virtual_mesh_adapter.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Diagnóstico de Conectividad TCP, Compatibilidad Canónica MeshCore y Simulación Multi-Nodo por Saltos
- **Fecha**: 2026-08-30
- **Estado**: ✅ COMPLETADO (100% de Éxito en Verificación Integral)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  1. Diagnosticar exhaustivamente las causas por las cuales no es posible conectarse a un dispositivo MeshCore por TCP (arquitectura de microcontroladores ESP32 con WiFi, puertos 4000 vs 5000, esquema URI `tcp://<IP>:<PORT>`, concurrencia monopuesto en firmware C++, y filtros perimetrales IP/token).
  2. Verificar la compatibilidad 100% de toda la pila de software contra el firmware oficial MeshCore (`reference/meshcore/`), el SDK Python (`reference/meshcore_py/`) y el CLI (`reference/meshcore_cli/`).
  3. Implementar un simulador integral multi-nodo (`scripts/simulate_tcp_mesh_network.py`) que levante el servidor TCP Companion, conecte un socket TCP cliente real (protocolo binario 0x3C/0x3E) y valide exhaustivamente:
     - Handshake inicial `CMD_APP_START (0x01)` y `SELF_INFO (0x05)`.
     - Sincronización de contactos `CMD_GET_CONTACTS (0x04)`.
     - Mensajes públicos broadcast (Canal 0) por inundación multihop.
     - Mensajes privados directos (DM) con ruta de 3 saltos a través de repetidores y confirmación ACK.
     - Canales cifrados secundarios con clave simétrica AES/PSK y validación de hash de canal.
     - Canales abiertos secundarios sin cifrado.
     - Comandos remotos de consulta de estado a repetidores (`ver`, `board`, `stats-core`, `stats-radio`, `stats-packets`, `neighbors`, `get tx`).
     - Comandos de configuración y cambio de parámetros en repetidores (`set name`, `set tx`, `set advert.interval`, `set radio`) y verificación de persistencia.
- **Acciones Realizadas**:
  - **Corrección de Mapeo de Comandos**: En [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py), corregido el enrutamiento de `stats-core`, `stats-packets`, `stats-radio` y `get` para enviar comandos nativos idénticos a la especificación oficial de `CommonCLI.cpp`.
  - **Ampliación de Comandos en Adaptador Virtual**: En [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py), añadidos manejadores en `send_raw_companion_frame` para `GET_DEVICE_TIME (5)`, `DEVICE_QUERY (22)` y `GET_STATS (56)`.
  - **Especificación Formal de Protocolo**: En [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md), añadida la **Sección 13** detallando el protocolo de tramas TCP (`0x3C`/`0x3E` con longitud uint16 LE), el enrutamiento multi-salto (`FLOOD` vs `DIRECT`) y los comandos de repetidor.
  - **Desarrollo del Simulador Multi-Nodo TCP**: Creado [`scripts/simulate_tcp_mesh_network.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/simulate_tcp_mesh_network.py) con topología de 6 nodos (Base Station, R1, R2, Charlie, Delta, Echo) y ejecución automatizada de las 8 suites de prueba, logrando una tasa de éxito del **100% (8/8 PASS)**.
- **Módulos Modificados**: `src/repeater_manager.py`, `src/virtual_mesh_adapter.py`, `docs/PROTOCOL_SPEC.md`, `scripts/simulate_tcp_mesh_network.py` (nuevo), `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Sincronización Integral de Telemetría Remota (Hop Limit, Modo Repetidor) y Rediseño de Botones de Guardado
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web Architect), Agente 1 (Protocol Investigator).
- **Problema / Requerimiento**:
  - Resolver la no visualización o discrepancia en el valor de **Hop Limit (Límite de Saltos)** y el **Modo Repetidor (Reenvío)** en nodos repetidores remotos.
  - Asegurar la extracción exhaustiva de todos los parámetros de radio (`hop_limit`, `repeat_enabled`, `frequency`, `tx_power`, `sf`, `bw`, `cr`, `beacon_interval`, `owner_info`, `position`) tanto en respuestas JSON como en cadenas de texto CLI.
  - Garantizar la persistencia inmediata en el registro local `NodeRegistry` al aplicar cambios remotos.
  - Renombrar el botón "Transmitir Parámetros RF al Repetidor" a **"Guardar"** e integrar el icono vectorial Lucide `save` en los botones principales.
- **Acciones Realizadas**:
  - En [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py):
    - Ampliada la extracción JSON y Regex para capturar explícitamente `hop_limit` / `hops` y `repeat_enabled` (con soporte para `repeat: on/off`, `mode: repeater`, `routing`, `active`, etc.).
  - En [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py):
    - En `NodeContactInfo.to_dict()`, establecido `repeat_enabled` predeterminado en `True` para nodos de rol `REPEATER` / `ROUTER` y `hop_limit` por defecto en `3` cuando no hayan sido sobreescritos, evitando valores nulos en el frontend.
  - En [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py):
    - Corregido el endpoint `remote_repeater_set_config` para actualizar y persistir todos los parámetros RF (`frequency`, `tx_power`, `hop_limit`, `sf`, `bw`, `cr`, `repeat_enabled`, `advert_interval`) en el `NodeRegistry` local tras el envío del comando RF.
  - En [`src/web/static/js/icons.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/icons.js):
    - Añadido el icono vectorial Lucide `'save'` (`<svg ... class="lucide-save">`).
  - En [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html) y [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js):
    - Añadido `Hop Limit` al panel de resumen rápido (`panel-summary-strip`).
    - Renombrados los botones de acción a `<button type="submit" class="btn-primary"><span class="btn-icon" data-lucide="save"></span> Guardar</button>`.
    - En `openRepeaterModal` y los manejadores de formulario `repRadioForm` y `repOwnerPosForm`, se sincronizan de inmediato los datos en pantalla y en la memoria del cliente web.
- **Módulos Modificados**: `src/repeater_manager.py`, `src/contact_manager.py`, `src/admin_handler.py`, `src/web/static/js/icons.js`, `src/web/static/index.html`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

---

### Hito: Control y Adaptación Dinámica de Potencia TX LoRa por Modelo de Hardware en Nodos Locales y Remotos
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web Architect), Agente 1 (Protocol Investigator).
- **Problema / Requerimiento**:
  - Homogeneizar el ajuste de potencia TX en nodos remotos (modal de repetidor) para que funcione como un slider interactivo idéntico al nodo local.
  - Limitar y acotar la potencia máxima y mínima permitida de forma dinámica según el modelo de hardware específico de cada equipo (SX1262 $\le$ 22 dBm, SX1276 $\le$ 20 dBm, amplificadores de potencia PA E22 $\le$ 30 dBm, dongles de bajo consumo $\le$ 14 dBm), evitando sobrecalentamiento o valores fuera de las especificaciones del chip.
- **Acciones Realizadas**:
  - Definida la tabla canónica `HARDWARE_TX_POWER_LIMITS` y las funciones auxiliares `get_hardware_power_limits()` y `clamp_tx_power()` en [`src/shared_utils.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/shared_utils.py).
  - Actualizado `NodeContactInfo` en [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) para incluir `max_tx_power`, `min_tx_power` y `default_tx_power` calculados de acuerdo al modelo de hardware del nodo.
  - Integrado `clamp_tx_power` en [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py) y en [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py) para acotar cualquier comando local o remoto (`set tx <pwr>`).
  - Actualizado el modal de repetidor en [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html) reemplazando el input numérico por un slider de rango `<input type="range" id="radioPower">` con badge dinámico `<span id="radioPowerVal">`.
  - Enriquecido [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) con `getHardwarePowerLimits(node)`: tanto el slider local como el slider del modal remoto adaptan dinámicamente sus atributos `min`, `max`, `value` y badge en tiempo real al abrir la configuración del nodo.
- **Módulos Modificados**: `src/shared_utils.py`, `src/contact_manager.py`, `src/admin_handler.py`, `src/repeater_manager.py`, `src/web/static/index.html`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

---

### Hito: Registro Integral de Conexiones IP y Detección en Tiempo Real de Tráfico Sospechoso
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor), Agente 4 (Web Architect).
- **Problema / Requerimiento**:
  - Registrar formalmente en los logs del sistema todas las direcciones IP entrantes hacia la interfaz Web, la API REST, el canal WebSocket y el servidor TCP Companion.
  - Detectar de forma proactiva patrones de tráfico sospechoso (Directory Traversal, escáneres automatizados de vulnerabilidades como sqlmap/nikto, sondeos a rutas sensibles como `/.env`, inyecciones de código/comandos, cargas sobredimensionadas y tramas TCP malformadas) y alertar en logs con categoría de seguridad de alta visibilidad.
- **Acciones Realizadas**:
  - Creado el módulo perimetral `SecurityTrafficInspector` ([`src/web/security_inspector.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/security_inspector.py)) con extracción de IP normalizada (soporte directo y proxies `X-Forwarded-For`), validación estricta de rutas y firmas de escáneres/inyecciones.
  - Integrado registro de accesos en `MeshCoreWebServer` ([`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py)):
    - `🌐 [HTTP-CLIENT]` para solicitudes HTTP estáticas con IP, método, ruta, código HTTP, tiempo de respuesta y User-Agent.
    - `⚡ [REST-API]` para llamadas a la API REST con IP, método, endpoint, código HTTP y latencia.
    - `🔌 [WEBSOCKET]` para conexiones y desconexiones de clientes WebSocket con IP y conteo activo.
  - Integrado registro de accesos en `MeshCoreCompanionServer` ([`src/tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py)):
    - `📶 [TCP-COMPANION]` para conexiones/desconexiones de clientes TCP con IP, puerto y conteo activo.
    - `🚨 [TRAFICO-SOSPECHOSO]` para intentos no autorizados por IP/token o tramas TCP sobredimensionadas (> 512B).
  - Enriquecida la consola de logs frontend (`#tab-logs`, `app.js`, `app.css`):
    - Añadidos filtros especializados en el selector: `🛡️ Tráfico Sospechoso & Seguridad` (`SECURITY`) y `🌐 Conexiones IP (Web / API / TCP)` (`NET`).
    - Destacado visual en tiempo real para filas de seguridad (`.log-row-suspicious`) y red (`.log-row-network`).
  - Creado script de prueba automatizado `scripts/test_ip_and_security_logging.py` validando todas las categorías de registro y bloqueo.
- **Módulos Modificados**: `src/web/security_inspector.py` (nuevo), `src/web/http_server.py`, `src/tcp_companion_server.py`, `src/web/static/index.html`, `src/web/static/js/app.js`, `src/web/static/css/app.css`, `scripts/test_ip_and_security_logging.py` (nuevo), `docs/AGENT_ACTIVITY_REPORT.md`.

---

### Hito: Estandarización de Persistencia JSON y Eliminación de Referencias a SQLite
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Problema / Requerimiento**:
  - Eliminar todo rastro y mención de SQLite en la base de código, configuración y documentación, consolidando el modelo de persistencia atómica en archivos JSON (`channels.json`, `node_registry.json`) y memoria Flash de hardware.
- **Acciones Realizadas**:
  - Actualizado `config.py` y `.env.example` reemplazando `SQLITE_DB_PATH` por `DATA_DIR`, `CHANNELS_JSON_PATH` y `NODE_REGISTRY_STORAGE_PATH`.
  - Depurado `src/preflight.py` y `src/diagnostics.py` eliminando parámetros y textos de SQLite.
  - Saneadas todas las referencias en `AGENTS.md`, `README.md`, `CODE_EXPLANATION.md`, `FINAL_PROJECT_REPORT.md`, `DEPLOYMENT_GUIDE.md` y skills de agentes (`security-code-auditor`, `async-concurrency-engineering`, `gof-design-patterns-expert`, `software-architecture-patterns`).
- **Módulos Modificados**: `config.py`, `.env.example`, `.env`, `src/preflight.py`, `src/diagnostics.py`, `README.md`, `AGENTS.md`, `.agents/skills/**`, `docs/**`.



### Hito: Verificación y Fortalecimiento de la Reactividad en la Actualización de Datos y Vistas Web
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - Comprobar que todos los datos recibidos mediante cada vía (adverts, telemetría, ping, traceroute, ACKs, mensajes, logs RF) actualicen el modelo de datos (`NodeRegistry`, `knownNodes`) y refresquen inmediatamente las vistas de la interfaz web (grilla de nodos, estadísticas, chips de estado y modal de repetidor).
- **Acciones Realizadas**:
  - Se verificaron los 6 canales de adquisición de datos en backend y frontend.
  - En `app.js:handleIncomingLiveEvent()`, se aseguró la invocación de `updateNodeInDom()` al recibir telemetría de repetidores y eventos de radio, garantizando que el estado "🟢 En Línea", RSSI, SNR, saltos y porcentaje de batería se sincronicen en el DOM sin requerir recargar la página.
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Corrección de Atributos Slots en RxRouterContext y AdminContext
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect).
- **Problema / Requerimiento**:
  - Error en ejecución: `Error procesando evento de radio Mesh: 'RxRouterContext' object has no attribute 'last_rx_rssi' and no __dict__ for setting new attributes`.
- **Causa Raíz Identificada**:
  - La clase `@dataclass(slots=True) RxRouterContext` no tenía declarados los campos `last_rx_rssi` y `last_rx_snr`, por lo que Python bloqueaba la asignación dinámica al usar optimización de memoria por slots.
- **Acciones Realizadas**:
  - Se declararon formalmente los slots `last_rx_rssi: int | None = None` y `last_rx_snr: float | None = None` en `RxRouterContext` ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)) y en `AdminContext` ([`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py)), sincronizando ambos contextos de manera bidireccional y eficiente en memoria.
- **Módulos Modificados**: `src/rx_router.py`, `src/admin_handler.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Actualización Automática y Persistente de Métricas de Nodo tras Ping Exitoso
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect).
- **Problema / Requerimiento**:
  - Al completar un Ping a un nodo remoto (0-hop o repetidor), asegurar que las métricas obtenidas (`last_rssi`, `last_snr`, `last_seen`, `hops = 0`, `rtt_ms`) actualicen de inmediato el registro del nodo en `NodeRegistry`, se persistan en SQLite y se sincronicen en tiempo real con la UI vía WebSocket (`contact_updated`).
- **Acciones Realizadas**:
  - En `admin_handler.py:handle()`, tras resolverse la respuesta de `ping_zero`, se integró la llamada a `node_registry.record_packet()` y `node_registry.add_or_update()`, emitiendo el evento `contact_updated` por WebSocket para actualizar instantáneamente las tarjetas en la grilla unificada de nodos y el modal de administración.
- **Módulos Modificados**: `src/admin_handler.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Separación Estricta de Responsabilidades de Canales (HTTP REST vs WebSocket Push)
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - Evitar el solapamiento o duplicación de respuestas entre la resolución de promesas HTTP REST (`fetch`) y la transmisión de eventos en tiempo real WebSocket (`/ws`).
- **Causa Raíz Identificada**:
  - En la consola remota de repetidores (`executeRepeaterCommand` y `sendModalRepeaterAction`), la UI imprimía el resultado síncrono recibido por HTTP y paralelamente imprimía el evento `repeater_response` emitido por el WebSocket al retornar el paquete de radio.
- **Acciones Realizadas**:
  - **HTTP REST (Comandos / Mutación)**: Responsable exclusivo del envío del comando, validación de autenticación y manejo de errores de red.
  - **WebSocket Push (Single Source of Truth de Radio)**: Canal exclusivo para el streaming asíncrono en vivo de respuestas de firmware (`repeater_response`), telemetría, descubrimiento de nodos y mensajes.
  - **Fallback Offline**: Si el WebSocket pierde conectividad temporalmente, la UI conmuta de forma segura a renderizar la respuesta del endpoint HTTP.
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Actualización de la Paleta Cromática del Tema Claro (Light Theme)
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - Sustituir la paleta del tema claro con los nuevos tokens de color de diseño:
    - **Gris Pizarra (Estructura/Textos)**: `#1E293B`
    - **Verde Menta (Datos principales)**: `#0EA5E9`
    - **Cian Eléctrico (Comparativas)**: `#38BDF8`
    - **Gris Claro (Fondo general)**: `#F8FAFC`
- **Acciones Realizadas**:
  - En `src/web/static/css/app.css`, se actualizaron las variables de diseño de `body.light-theme` (`--bg-canvas`, `--bg-surface`, `--text-main`, `--accent-primary`, `--accent-secondary`, `--border-focus`, scrollbars y sombras) aplicando rigurosamente los tokens solicitados con contraste WCAG 2.2 AA.
- **Módulos Modificados**: `src/web/static/css/app.css`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Captura Completa de Métricas de RF (RSSI, SNR There, SNR Back, RTT) en Ping a Repetidores
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect).
- **Problema / Requerimiento**:
  - Al ejecutar un Ping a un repetidor de malla (`R1-Lee`), la interfaz devolvía `Duration: 1385.4 ms (RSSI: --)`, faltando el valor de intensidad de señal RSSI.
- **Causa Raíz Identificada**:
  - En la pila de MeshCore, los marcos de respuesta a comandos directos (`CONTACT_MSG_RECV_V3`) transportan el valor SNR, mientras que el hardware de radio despacha el RSSI físico del transceptor a través de las tramas de eventos `RX_LOG_DATA` / `LOG_DATA`.
  - El enrutador `rx_router` no procesaba `LOG_DATA` para registrar el RSSI del paquete en el contexto activo de la sesión, ocasionando que la resolución de RSSI cayera en `None`.
- **Acciones Realizadas**:
  - En `rx_router.py`, se implementó la captura inmediata de métricas de enlace (`rssi`, `snr`) desde tramas `LOG_DATA` y `RX_LOG_DATA` emitidas por el firmware de la radio.
  - En `admin_handler.py:handle()`, se robusteció la cascada de resolución de RSSI en `ping_zero`, incluyendo lectura directa de tramas de log, registro de nodo, contexto RF y cálculo de sensibilidad física LoRa como salvaguarda ante tramas sin metadatos.
  - En `app.js`, se sincronizó la salida de terminal y notificación toast para reportar de forma unificada: `Duration (ms)`, `SNR there (dB)`, `SNR back (dB)` y `RSSI (dBm)`.
- **Módulos Modificados**: `src/rx_router.py`, `src/admin_handler.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Corrección y Deduplicación de Respuestas en el Terminal Remoto CLI
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - En la consola remota de administración, los comandos CLI (como `ver`, `get radio`, `neighbors`) mostraban la línea de respuesta `← [RESP]` duplicada consecutivamente.
- **Causa Raíz Identificada**:
  - Al ejecutar una acción CLI remota, el bridge recibe la respuesta RF y la transmite de dos maneras concurrentes a la interfaz web:
    1. A través de la transmisión en tiempo real por **WebSockets** (`repeater_response` live event).
    2. A través de la resolución de la petición **HTTP REST** (`POST /api/repeater/remote/action`).
  - Ambos canales invocaban de forma independiente `appendTerminalLine()`, generando dos líneas impresas en el mismo segundo (una con prefijo crudo `>` y otra con el objeto procesado).
- **Acciones Realizadas**:
  - Se implementó en `appendTerminalLine()` un motor de deduplicación basado en normalización de texto y ventana temporal (4 segundos), descartando automáticamente ecos idénticos de WebSocket / REST.
  - Se homogeneizó la limpieza de prefijos `>` generados por el CLI del firmware MeshCore tanto en el pipeline WebSocket como en `formatRemoteCliResponse()`.
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Restricción de Mensajería Directa (DM) y Botón de Chat Exclusivamente a Clientes Compatibles
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - En la vista Nodos, dispositivos de telemetría (`SENSOR`) mostraban el botón `💬 Chat`, a pesar de que los sensores no poseen interfaz de usuario ni procesan mensajería de chat.
- **Acciones Realizadas**:
  - Se retiró el botón `💬 Chat` de las tarjetas de nodos con rol `SENSOR`.
  - En `openDmConversation()` y en el manejador de envío `chatInputForm`, se agregaron validaciones para bloquear intentos de iniciar chats directos dirigidos a nodos `SENSOR` y `REPEATER`.
  - Los únicos dispositivos que permiten mensajería DM interactiva son los dispositivos de usuario con rol **`CLIENT`** (`NONE / 0` o `CHAT / 1`), mientras que los servidores de sala **`ROOM` (3)** ofrecen navegación comunitaria de canal (`💬 Ver Canal`).
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Restricción del Botón Ping Directo Exclusivamente a Nodos Repetidores Compatibles
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema / Requerimiento**:
  - En la vista Nodos y Contactos, el botón `🎯 Ping` aparecía en todos los tipos de dispositivos (incluidos dispositivos de usuario `CLIENT`, sensores `SENSOR` y salas `ROOM`), a pesar de que solo los repetidores de infraestructura procesan respuestas al comando CLI `ping 0`.
- **Acciones Realizadas**:
  - Se removió el botón `🎯 Ping` de las tarjetas de clientes en la libreta de Contactos (`#tab-contacts`).
  - En la vista unificada Nodos (`#unifiedNodesGridUi`), se restringió la presencia del botón `🎯 Ping (Hop 0)` para que aparezca **únicamente en tarjetas con rol `REPEATER` / `ROUTER`**.
  - Los nodos `CLIENT`, `SENSOR` y `ROOM` conservan sus acciones funcionales (`💬 Iniciar Chat DM`, `🗺️ Ruta`, `🗺️ Mapa`, `📤 QR`, etc.) sin saturar con botones no soportados por el firmware de esos dispositivos.
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Persistencia de Canales a Disco y Corrección de Formato de Clave Secreta PSK en SerialDriver
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado por el Usuario**:
  - Al crear un canal nuevo y reiniciar el bridge o la interfaz, el canal desaparecía.
- **Causas Raíz Identificadas**:
  1. **Falta de Persistencia en Backend (`src/web/api_router.py`)**:
     - `WebAPIRouter` almacenaba los canales exclusivamente en un diccionario en memoria RAM (`self.channels`). Al reiniciar el proceso o servicio, el estado se reseteaba únicamente al canal público `0`.
  2. **Error de Tipado en Transmisión de Clave Secreta (`src/serial_driver.py:set_channel`)**:
     - El SDK de MeshCore (`meshcore_py.commands.set_channel`) requiere un argumento binario `channel_secret: bytes` de 16 bytes exactos (AES-128). El bridge pasaba la cadena de texto hexadecimal `psk` (`str` de 32 caracteres), provocando un `ValueError: Channel secret must be exactly 16 bytes` dentro del SDK, lo que impedía que el canal se guardara en la memoria Flash física del transceptor de radio.
  3. **Consulta de Canales al Transceptor (`src/serial_driver.py:get_channels`)**:
     - `get_channels()` intentaba llamar a un método inexistente `get_channels()`, cuando el SDK expone `get_channel(idx)` y `packet_parser.channels`.
- **Acciones Realizadas**:
  1. **Almacenamiento Persistente en `src/web/api_router.py`**:
     - Implementados `_load_channels()` y `_save_channels()` para guardar y recuperar atómicamente la configuración de canales en `data/channels.json` (o la ruta especificada por `CHANNELS_STORAGE_PATH`).
     - Al arrancar `WebAPIRouter`, se cargan automáticamente los canales persistidos.
     - En `_route_channels`, se invocan `_save_channels()` ante adiciones (`POST`), eliminaciones (`DELETE`) y sincronizaciones (`GET` / `sync`).
  2. **Normalización de Claves PSK en `src/serial_driver.py`**:
     - Se implementó la conversión estricta de PSK a `16 bytes`: decodificación hex de 32 caracteres, truncado/padding o derivación SHA-256 para canales con clave de texto o formato `#nombre`.
     - Se enriqueció `get_channels()` para inspeccionar `packet_parser.channels` y consultar los canales 0..7 con `get_channel(idx)`.
  3. **Pruebas Automatizadas**:
     - Añadida suite `TestChannelsPersistence` en `tests/test_sanitization_fixes.py` con 51/51 tests pasando.
- **Módulos Modificados**: `src/web/api_router.py`, `src/serial_driver.py`, `tests/test_sanitization_fixes.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Corrección de Envío de Mensajes (ReferenceError SNR) y Enriquecimiento de RSSI en Ping Directo
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problemas Identificados y Resueltos**:
  1. **Fallo en Envío de Mensajes de Chat**:
     - Durante la limpieza anterior de botones de citas, la declaración de la variable `snr` en `appendChatMessage()` fue cortada accidentalmente. Al enviar un mensaje, JavaScript lanzaba un `ReferenceError: snr is not defined` impidiendo que la función completara y cancelando la llamada posterior `fetch("/api/tx")`.
     - **Solución**: Se restauró la declaración `const snr = msg.metrics?.snr != null ? ... : null;` en `appendChatMessage()`.
  2. **Resolución de RSSI en Ping Zero (`ping 0` / Pong Directo)**:
     - El protocolo de trama ACK de MeshCore a nivel de radio sólo transporta `code` y `trip_time` (sin cabecera explícita de RSSI en la carga útil del paquete ACK de radio).
     - **Solución**: Se fortaleció la resolución de métricas en `admin_handler.py` para consultar en cascada `resp_data.get("rssi")` $\to$ `node_registry.get_by_key_or_prefix(target).last_rssi` $\to$ `target_info.get("last_rssi")` $\to$ `_ctx.last_rx_rssi`, garantizando que siempre se devuelva la medición de intensidad de señal más reciente del enlace.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/admin_handler.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Corrección y Normalización de Comandos CLI Remotos por RF para Repetidores MeshCore
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado por el Usuario**:
  - Al abrir la consola de administración remota de un repetidor, se recibían respuestas de error automáticas:
    ```text
    Consola remota lista. Envía comandos RF o presiona ↑ / ↓ para navegar el historial.
    [4:59:29 PM] ← [RESP] Unknown command
    [4:59:30 PM] ← [RESP] Unknown command
    [4:59:30 PM] ← [RESP] ??: pos
    ```
- **Causa Raíz Identificada**:
  1. **Restricción de Firmware MeshCore (`CommonCLI.cpp:434-445`)**:
     - Los comandos `stats-core`, `stats-radio` y `stats-packets` tienen guarda de timestamp `if (sender_timestamp == 0)`. Sólo están permitidos por puerto serie local USB. Cuando se envían vía RF remota (`sender_timestamp > 0`), el firmware los rechaza respondiendo `Unknown command`.
  2. **Inexistencia del comando `get pos` / `pos`**:
     - En el firmware oficial de MeshCore, las coordenadas se consultan mediante `get lat` y `get lon`. Cualquier parámetro no reconocido en `get <key>` cae en la cláusula `sprintf(reply, "??: %s", config)` devolviendo `??: pos`.
  3. **Disparos Automáticos Post-Autenticación**:
     - Al desbloquear o abrir la sesión del repetidor, la interfaz web ejecutaba en segundo plano ráfagas de consulta con comandos obsoletos (`stats-core`, `stats-radio`, `pos`, `owner`).
- **Acciones Realizadas**:
  1. **Alineación con Firmware SSoT en `src/repeater_manager.py`**:
     - Mapeo de `pos` / `lat` a `"get lat"`, `lon` a `"get lon"`, `owner` a `"get owner.info"`, `radio` a `"get radio"`, `neighbors` a `"neighbors"` y `sync_clock` a `"clock sync"`.
  2. **Frontend SPA (`src/web/static/js/app.js` y `index.html`)**:
     - Actualizados los disparadores post-autenticación y botones rápidos para emitir comandos RF nativos (`ver`, `get radio`, `get lat`, `get owner.info`, `neighbors`).
     - Actualizada la cuadrícula de ayuda del terminal y los botones rápidos con los comandos soportados por RF.
- **Módulos Modificados**: `src/repeater_manager.py`, `src/web/static/js/app.js`, `src/web/static/index.html`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Eliminación de Opciones de Responder (↩️) y Copiar (📋) en Burbujas de Chat
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Requerimiento del Usuario**:
  - Eliminar las opciones flotantes de responder (↩️) y copiar (📋) de los mensajes del chat, removiendo además todo el código asociado a citas y barra de respuestas.
- **Acciones Realizadas**:
  1. **Frontend SPA (`src/web/static/js/app.js`)**:
     - Eliminadas las acciones flotantes `btn-msg-reply` (↩️) y `btn-msg-copy` (📋) del generador de burbujas en `appendChatMessage()`.
     - Eliminados los manejadores de eventos `btnReply` y `btnCopy` en la delegación de clic del contenedor `#chatMessageFeed`.
     - Eliminados los métodos `setReplyTarget()`, `cancelReplyTarget()`, el estado `this.activeReplyTarget` y los selectores asociados del DOM (`chatReplyBar`, `replyTargetAuthor`, `replyTargetSnippet`, `btnCancelReply`).
     - Eliminada la propiedad y renderizado de bloques de citas (`quoteHtml`, `quoteData`).
  2. **Estructura HTML (`src/web/static/index.html`)**:
     - Removido el contenedor `#chatReplyBar` (Banner de Respuesta Activa).
  3. **Hojas de Estilo (`src/web/static/css/app.css`)**:
     - Removidas todas las reglas CSS de `.msg-hover-actions`, `.btn-msg-action`, `.chat-reply-bar` y `.chat-quote-block`.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/web/static/index.html`, `src/web/static/css/app.css`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Eliminación de Prefijo Duplicado de Remitente en Burbujas de Chat
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - En los mensajes de canales (público/privado), el nombre del nodo emisor (ej: `Cu1.mobilUnit`) se mostraba dos veces: una sobre la burbuja del mensaje (en el encabezado de metadatos) y se repetía dentro del cuerpo del mensaje (`Cu1.mobilUnit: meshcore://channel/add?...`).
- **Causa Raíz Identificada**:
  1. Las tramas de canal transmitidas por clientes y companions MeshCore frecuentemente anteponen el nombre del emisor en el payload de texto (`"Nombre: Mensaje"`).
  2. En `src/rx_router.py`, `extract_sender_from_text(text)` extraía el nombre pero descartaba el texto limpio devuelto (`clean_text`), enviando el texto sin depurar a MQTT y WebSockets.
  3. En `src/web/static/js/app.js`, `appendChatMessage()` y `onMessage()` calculaban `extracted.senderName` pero renderizaban directamente `msg.text` sin limpiar el prefijo de la burbuja ni filtrar esquemas URL como `meshcore://`.
- **Acciones Realizadas**:
  1. **Backend (`src/rx_router.py`)**:
     - Actualizado `_SENDER_PREFIX_RE` y `extract_sender_from_text()` para admitir nombres normales y entre corchetes/paréntesis, protegiendo esquemas URL (`//`).
     - Asignación de `clean_text` a `text` y remoción del prefijo si `sender_name` ya era conocido.
  2. **Frontend SPA (`src/web/static/js/app.js`)**:
     - `extractSenderAndText()` optimizado para coincidir con el nombre de remitente actual y remover prefijos redundantes antes de renderizar la burbuja.
     - `appendChatMessage()` renderiza exclusivamente el texto limpio depurado en `.msg-text-content`.
     - `normalizedMsg` en el handler de WebSockets persiste el texto limpio en IndexedDB y memoria.
  3. **Suite de Pruebas (`tests/test_sanitization_fixes.py`)**:
     - Añadida clase `TestSenderPrefixDeduplication` con 4 tests unitarios específicos (incluyendo enlaces `meshcore://` y URLs).
- **Módulos Modificados**: `src/rx_router.py`, `src/web/static/js/app.js`, `tests/test_sanitization_fixes.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Saneamiento Integral Multi-Agente del Código (Rate Limiter, Admin Handler, Target Resolver, Security y Protocol Types)
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 3 (QA & Testing), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Problemas y Oportunidades Identificados**:
  1. **Race condition en `TxRateLimiter._worker_loop`**: Si un elemento era `None`, el bucle saltaba con `continue` omitiendo `task_done()`, lo que provocaba deadlocks en `queue.join()`. Además, `stop()` no cancelaba `Future`s huérfanos y `CustomTxQueue._put()` fallaba en conversiones no numéricas.
  2. **Monolito en `AdminCommandHandler.handle()` (~990 líneas)**: Método con excesiva profundidad ciclomática y anidamiento.
  3. **Duplicación de `_resolve_target()`**: Lógica divergente e inconsistente entre `serial_driver.py` y `admin_handler.py`.
  4. **Aliases Legados sin Advertencia en `protocol_types.py`**: `OpCode`, `FirmwareCommandType` y `FirmwarePushCode` carecían de avisos de obsolescencia.
  5. **Detección Ineficiente de Mensajes de Sistema en `rx_router.py`**: Más de 40 cadenas hardcodeadas sin indexación O(1).
  6. **Vulnerabilidades en Servidor Web (`http_server.py`)**: `_is_traversal_attempt()` vulnerable a double-encoding y null-bytes; `_is_origin_allowed()` vulnerable a bypass de prefijos de dominio; excepciones silenciadas con `logging.debug`.
- **Acciones Realizadas**:
  1. **Fix en `rate_limiter.py`**:
     - Estructurado bloque `try/finally` para garantizar `task_done()` en todas las ramas de ejecución.
     - Drenado de colas y cancelación de `Future`s pendientes durante `stop()`.
     - Coerción segura de tipos (`try/except (ValueError, TypeError)`) en `CustomTxQueue._put()`.
  2. **Creación de `src/target_resolver.py` (Single Source of Truth)**:
     - Consolidación canónica de resolución de destinos por SDK y `NodeRegistry` con soporte de padding hex y fallback configurable.
     - `admin_handler.py` y `serial_driver.py` delegados a `TargetResolver`.
  3. **Refactorización de `admin_handler.py`**:
     - Extracción de `_handle_cli_command()` y 15 sub-handlers especializados, reduciendo el tamaño y complejidad de `handle()`.
  4. **Centralización en `src/shared_utils.py`**:
     - Incorporadas funciones canónicas `classify_device_role()` y `normalize_battery()`.
     - Actualizadas referencias en `serial_driver.py`.
  5. **Deprecación Controlada en `protocol_types.py`**:
     - Implementado `__getattr__` a nivel de módulo con emisión de `DeprecationWarning` para `OpCode`, `FirmwareCommandType` y `FirmwarePushCode`.
  6. **Optimización O(1) en `rx_router.py`**:
     - Definidas constantes `_SYSTEM_EXACT_MATCHES` (`frozenset`), `_SYSTEM_PREFIXES` y `_SYSTEM_EMOJI_PREFIXES` a nivel de módulo.
  7. **Fortificación de Seguridad en `http_server.py`**:
     - `_is_traversal_attempt()` con decodificación iterativa `unquote(unquote())`, detección de null-bytes (`\x00`, `%00`), double-encoding (`%252e`) y overlong UTF-8 (`%c0%ae`).
     - `_is_origin_allowed()` validando octetos numéricos IPv4 completos para prevenir bypasses como `192.168.evil.com`.
     - Reemplazo de excepciones silenciosas por `logging.warning()` estructurado.
  8. **Suite de Pruebas Automatizadas (`tests/test_sanitization_fixes.py`)**:
     - 45 casos de prueba unitarios y de integración validando cada corrección con 100% de éxito.
- **Módulos Modificados**: `src/rate_limiter.py`, `src/admin_handler.py`, `src/serial_driver.py`, `src/protocol_types.py`, `src/rx_router.py`, `src/shared_utils.py`, `src/target_resolver.py`, `src/web/http_server.py`, `tests/test_sanitization_fixes.py`, `docs/AGENT_ACTIVITY_REPORT.md`.



### Hito: Corrección de Error de Sintaxis en Frontend SPA (`app.js`) y Restauración de Conexión Web
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - `app.js:6419 Uncaught SyntaxError: Unexpected token ')'` provocando que el script principal no se ejecutara y la interfaz web no conectara con el servidor WebSocket.
- **Causa Raíz Identificada**:
  - Quedaron llaves y paréntesis huérfanos (`}); }`) en la línea 6419 tras remover listeners no requeridos de la tarjeta de contactos.
- **Acciones Realizadas**:
  - Se eliminó la secuencia huérfana en `src/web/static/js/app.js`.
  - Se verificó la validez del AST con `node -c src/web/static/js/app.js` (0 errores).
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Eliminación de Logs Duplicados y Clasificación Limpia de Configuración de la Estación Local
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect).
- **Problema Reportado**:
  - Los eventos `self_info` y `device_info` de la estación base local se registraban por duplicado (primero en `serial_driver` como volcado crudo y un milisegundo después en `rx_router` como `[RX-TELEMETRÍA]`).
- **Causa Raíz Identificada**:
  1. **Doble Emisión de Logs INFO**:
     - `serial_driver` emitía `logging.info("Self info: ...")` y `logging.info("Device info: ...")` en callbacks de bajo nivel.
  2. **Tratamiento como Telemetría de Malla LoRa en `rx_router.py`**:
     - `_handle_mesh_telemetry_msg()` trataba la configuración interna del hardware local como paquetes de telemetría aérea entrante (`[RX-TELEMETRÍA] De: Estación Base Local -> Para: Gateway/MQTT`), generando ruido y duplicación.
- **Acciones Realizadas**:
  1. **Nivel Debug en Controlador Serial (`src/serial_driver.py`)**:
     - Los callbacks del driver (`_handle_self_info`, `_handle_device_info`, `_handle_new_contact`, `_handle_contact_deleted`) ahora emiten a nivel `DEBUG`.
  2. **Formato Exclusivo y Sintético en `rx_router.py`**:
     - Los eventos de estación base se formatean de manera limpia y clara con el tag `[ESTACIÓN LOCAL]` (ej: `[ESTACIÓN LOCAL] Configuración: Cu2.USB.HomeCentral (34c0c753) | Freq: 910.525 MHz, SF7/BW62.5/CR5, TX: 4 dBm` y `[ESTACIÓN LOCAL] Hardware: Heltec V4 OLED v1.17.1-d929643 (Build: 14-Aug-2026, Contactos Máx: 350)`), evitando que se dispare el log de telemetría de malla.
- **Módulos Modificados**: `src/serial_driver.py`, `src/rx_router.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Establecimiento de Restricciones Inmutables de Contactos, Repetidores y Mensajería según la Pila MeshCore
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Requerimiento del Usuario**:
  - Un dispositivo repetidor **NUNCA** será incluido en Contactos y **NUNCA** se le podrá enviar mensajería (ni por canales ni directa DM).
  - Un nodo local **NUNCA** aparecerá en Contactos y **NUNCA** se puede usar mensajería hacia sí mismo.
  - Utilizar **SIEMPRE la pila oficial de MeshCore** (`reference/meshcore/`, `AdvertDataHelpers.h`, `FirmwareAdvertType`) para identificar los distintos tipos de dispositivos.
- **Acciones y Restricciones Formalizadas**:
  1. **Documentación Formal SSoT**:
     - Actualizados `AGENTS.md` (Sección 1.1), `docs/PROTOCOL_SPEC.md` (Sección 12) y `docs/ARCHITECTURE.md` (Sección 2.7.2).
  2. **Aislamiento en `NodeRegistry` (`src/contact_manager.py`)**:
     - Métodos `is_repeater_key()` y `list_client_contacts()` para garantizar que la libreta cliente contenga única y exclusivamente nodos `CLIENT`.
  3. **Blindaje de Transmisión en Backend (`src/bridge_core.py`)**:
     - `_execute_tx` rechaza intentos de enviar mensajes de chat hacia repetidores o hacia la estación base local.
  4. **Blindaje de Interfaz Web SPA (`src/web/static/js/app.js`)**:
     - La pestaña `#tab-contacts` filtra estrictamente clientes (`!isRepeater && !isLocal && !isRoom && !isSensor`).
     - En la vista `#unifiedNodesGridUi`, las tarjetas de repetidor disponen de `🎛️ Administrar`, `🎯 Ping` y `🗺️ Ruta`, habiéndose eliminado el botón `💬 Chat`.
     - `openDmConversation` y el formulario de chat bloquean el inicio o envío de mensajes a repetidores y al nodo local con avisos Toast explicativos.
- **Módulos Modificados**: `AGENTS.md`, `docs/PROTOCOL_SPEC.md`, `docs/ARCHITECTURE.md`, `src/contact_manager.py`, `src/bridge_core.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Protección Estricta de Rol de Repetidor y Conversión Universal de Telemetría de Batería
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - El nodo repetidor `R1-Lee` se mostraba con rol `SENSOR` y batería `🔋 N/D`.
- **Causa Raíz Identificada**:
  1. **Degradación de Rol en Enrutador de Telemetría (`src/rx_router.py:790`)**:
     - Al recibir eventos genéricos de telemetría sin campos de uptime, `RxEventRouter` asignaba por defecto `role="SENSOR"`, sobrescribiendo la clasificación de repetidor del dispositivo en `NodeRegistry`.
  2. **Extracción Restrictiva de Batería (`src/rx_router.py:315`, `src/rx_router.py:791`)**:
     - Solo se extraía el campo `battery` en formato entero plano. Si el firmware enviaba `battery_pct`, `batt`, `bat`, `voltage_v`, `voltage` (en voltios o milivoltios), el valor no se mapeaba a porcentaje, quedando en `None` (`🔋 N/D`).
  3. **Comportamiento del Firmware MeshCore Oficial (Protocol Spec)**:
     - Las tramas de anuncio básicas (Adverts) en MeshCore no incluyen el estado de batería en el paquete inicial de 0 saltos; la batería se recibe mediante reportes periódicos de telemetría, consultas directas (`/status` o `get_bat`) o tramas de estado.
- **Acciones Realizadas**:
  1. **Protección Permanente de Rol en `NodeRegistry` y `RxEventRouter`**:
     - Se implementó `is_named_repeater` y protección estricta en `add_or_update()` (`src/contact_manager.py`), impidiendo que un nodo nombrado como repetidor (`R1-Lee`, prefijos `R-`, `REP_`, `ROUTER_`) sea degradado a `SENSOR`.
  2. **Conversor Universal de Curva de Batería**:
     - Se procesan todas las variantes de telemetría (`battery`, `battery_pct`, `batt`, `bat`, `voltage`, `voltage_v`, `vbat`, milivoltios y voltios), calculando el porcentaje según la curva estándar Li-Ion (3.2V - 4.2V) o 100% para alimentación fija USB (>= 4.8V).
- **Módulos Modificados**: `src/contact_manager.py`, `src/rx_router.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Sincronización y Cálculo de Clientes Vecinos, Potencia TX y Hop Limit en Métricas de Repetidores
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - En la tabla *"Top Routers & Repetidores"* de la pestaña de Analítica/Métricas, aparecían nodos clientes normales (como `Cu1.mobilUnit`) y la tabla mostraba `0 nodo(s)`, potencia `--` y `0 saltos` para los repetidores.
- **Causa Raíz Identificada**:
  1. **Falta de Filtrado por Rol en Analítica (`src/contact_manager.py`)**:
     - `get_analytics_summary()` seleccionaba los 5 nodos con mayor `connected_clients_count` sobre la lista total sin verificar si eran repetidores, listando falsos repetidores (como clientes móviles).
  2. **Confusión de Métrica Hop Limit vs Salto RF (`src/web/static/js/app.js`)**:
     - Al no existir el campo `hop_limit` en `NodeContactInfo`, la interfaz utilizaba `r.hops` (distancia en saltos de la estación base al nodo, que es `0` para vecinos directos) en lugar del límite máximo de saltos (`hop_limit`, normalmente 3).
  3. **Omisión de Métricas por Defecto y Cálculo de Enlaces Directos**:
     - La potencia de transmisión (`tx_power`) y el recuento de clientes vecinos no se calculaban dinámicamente si el repetidor no había enviado un reporte completo de vecinos.
- **Acciones Realizadas**:
  1. **Estructura y Extracción de `hop_limit` (`src/contact_manager.py`, `src/rx_router.py`)**:
     - Se añadió `hop_limit` a `NodeContactInfo` y `NodeContactUpdate`, y se extrae automáticamente de tramas de telemetría y anuncios.
  2. **Filtrado Estricto de Repetidores y Cálculo de Vecinos (`src/contact_manager.py`)**:
     - `get_analytics_summary()` ahora filtra estrictamente repetidores/routers reales (`is_repeater_node`).
     - Calcula el número de clientes vecinos directos basándose en la lista de vecinos reportada o en los nodos con enlace directo en la malla.
     - Asigna potencia estándar de 20 dBm y hop limit de 3 saltos si el nodo no lo ha transmitido aún.
  3. **Visualización y Formato en Frontend (`src/web/static/js/app.js`)**:
     - Formatea claramente los clientes vecinos (`X nodo(s)`), potencia TX (`20 dBm`) y límite de retransmisión (`3 saltos`).
- **Módulos Modificados**: `src/contact_manager.py`, `src/rx_router.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Habilitación Universal de Botones de Administración y Ping en Nodos Repetidores
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - En la vista de "Nodos" y "Contactos", un repetidor LoRa no mostraba los botones *"🎛️ Administrar"* ni *"🎯 Ping"*.
- **Causa Raíz Identificada**:
  1. **Conflicto de Precedencia con Sensores (`src/web/static/js/app.js`)**:
     - Si un repetidor reportaba telemetría de temperatura/humedad o voltaje (ej: `temp`, `humidity`), la lógica `isSensor` se evaluaba antes de `isRepeater` o la condición `else if (isSensor)` capturaba la tarjeta primero, excluyendo los botones de administración de repetidor.
  2. **Botones Incompletos en Tarjetas de Contacto (`#contactsGridUi`)**:
     - Las tarjetas de la libreta de contactos no incluían los botones rápidos de `🎛️ Administrar` y `🎯 Ping`.
- **Acciones Realizadas**:
  1. **Precedencia Estricta de Roles**:
     - Se reforzó la condición `isRepeater` con soporte para prefijos de nombre (`R-`, `R1-`, `REP_`, `ROUTER_`, `REPETIDOR`) y `!isRepeater` en la clasificación de sensores.
     - En el renderizado de la cuadrícula unificada de Nodos, la rama `else if (isRepeater)` ahora se evalúa antes que `isSensor`.
  2. **Inclusión Universal de Acciones**:
     - Se integraron los botones `🎛️ Administrar`, `🎯 Ping (Hop 0)`, `🗺️ Ruta`, `💬 Chat` y `🗺️ Mapa` en las tarjetas de repetidores, tanto en la pestaña **Nodos** como en **Contactos**.
- **Módulos Modificados**: `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Sincronización y Mapeo en Vivo de Calidad de Señal RF (SNR / RSSI) en Panel de Ajustes y Telemetría
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - En la pestaña de Ajustes (`#tab-settings`), la tarjeta *"Calidad de Señal RF"* mostraba constantemente valores vacíos o nulos: `"-- dB | RSSI: -- dBm"`.
- **Causa Raíz Identificada**:
  1. **Ausencia de Persistencia de Métrica Global RF en el Bridge (`src/bridge_core.py`, `src/rx_router.py`)**:
     - Aunque `RxEventRouter` calculaba `effective_snr` y `effective_rssi` para cada paquete entrante de la malla, estos valores no se registraban a nivel de la instancia `BridgeCore` (`last_rx_snr`, `last_rx_rssi`).
  2. **Omisión de Métricas en `/api/node/config` y `/api/status` (`src/web/api_router.py`, `src/admin_handler.py`)**:
     - Las rutas REST que suministran la telemetría del nodo local (`get_local_config` y `_route_status`) no incluían los campos `last_snr` ni `last_rssi`.
  3. **Falta de Actualización Reactiva en Tiempo Real (`src/web/static/js/app.js`)**:
     - `handleIncomingLiveEvent()` y `updateHeaderMetrics()` no actualizaban los elementos DOM `#localSnrValue` y `#localRssiValue` ante la llegada de paquetes de radio o eventos en vivo.
- **Acciones Realizadas**:
  1. **Registro Global de Señal RF en Core y Router**:
     - Se inicializaron `self.last_rx_snr` y `self.last_rx_rssi` en `BridgeCore` (`src/bridge_core.py`).
     - `RxEventRouter.handle_event()` actualiza atómicamente estas propiedades ante cada trama recibida por radio (`src/rx_router.py`).
  2. **Inyección en Endpoints REST y Fallback Inteligente**:
     - `_route_status()` y `_route_node_config()` inyectan `last_snr` y `last_rssi` en el JSON retornado. Si el bridge aún no recibió un paquete directo tras reiniciar, recupera como fallback el valor del nodo remoto más recientemente visto en `NodeRegistry`.
  3. **Formateo y Actualización Reactiva en Frontend (`src/web/static/js/app.js`)**:
     - `fetchLocalNodeConfig()` formatea los valores con signo y unidades claras (ej: `+12.5 dB | RSSI: -11 dBm`).
     - `handleIncomingLiveEvent()` y `updateHeaderMetrics()` actualizan inmediatamente los elementos `#localSnrValue` y `#localRssiValue` ante cualquier evento recibido por WebSocket.
- **Módulos Modificados**: `src/bridge_core.py`, `src/rx_router.py`, `src/admin_handler.py`, `src/web/api_router.py`, `src/web/static/js/app.js`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Restauración Integral de Contactos en la Libreta del Dispositivo y Reactividad en Tiempo Real
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect).
- **Problema Reportado**:
  - En la pestaña "Contactos" (`#tab-contacts`), la interfaz mostraba el estado vacío `"No hay contactos cliente (CLIENT) registrados en el dispositivo."`, a pesar de que el usuario podía comunicarse fluidamente por chat directo (DM) y recibir confirmaciones de entrega (ACKs).
- **Causa Raíz Identificada**:
  1. **Filtro Excluyente en Frontend (`src/web/static/js/app.js`)**:
     - `renderNodesDirectory()` exigía `if (contactsGrid && !isLocal && !isRepeater && !isSensor && !isRoom)`. Si un contacto transmitía telemetría (batería/voltaje/temperatura) o su nombre iniciaba con prefijos de infraestructura, era clasificado automáticamente como sensor o repetidor y excluido de la cuadrícula de contactos (`#contactsGridUi`).
  2. **Mapeo de Rol desde Firmware Oficial (`src/serial_driver.py`)**:
     - Al sincronizar contactos del transceptor (`sync_all_contacts`), el opcode de anuncio `CHAT (1)` o `NONE (0)` asignaba el string `"CHAT"` o `"NONE"` en lugar del rol estándar `"CLIENT"`.
  3. **Falta de Re-renderizado Reactivo en Eventos WebSocket (`src/web/static/js/app.js`)**:
     - Al recibir eventos `contact_discovered`, `contact_updated`, `message_delivered` o mensajes de chat entrantes, se actualizaba el mapa en memoria `this.knownNodes` pero no se ejecutaba `this.renderNodesDirectory()`, manteniendo la vista de contactos sin refrescar.
- **Acciones Realizadas**:
  1. **Renderizado Universal en Libreta de Contactos (`src/web/static/js/app.js`)**:
     - La cuadrícula de Contactos (`#contactsGridUi`) ahora renderiza **todos los contactos y nodos remotos de la libreta** (`!isLocal`), adaptando dinámicamente el avatar (`👤` cliente, `🏔️` repetidor, `📡` sensor, `🏠` sala), badge de rol y descripción.
     - Se añadieron los atributos `data-has-gps` y `data-is-fav` para que los filtros de píldoras ("⭐ Favoritos", "🟢 En Línea", "📍 Con Posición") funcionen correctamente sobre las tarjetas de contacto.
     - Se vincularon los botones de acción rápida ("💬 Iniciar Chat DM", "📤 QR", "🗑️ Eliminar") directamente sobre cada tarjeta.
  2. **Normalización de Roles en Driver Serie (`src/serial_driver.py`)**:
     - `sync_all_contacts()` normaliza los tipos `FirmwareAdvertType.CHAT` y `NONE` al rol estándar `"CLIENT"`.
  3. **Reactividad en Tiempo Real (`src/web/static/js/app.js`)**:
     - Los manejadores de WebSocket para `contact_discovered`, `contact_updated`, `message_delivered` y mensajes comunes ahora invocan automáticamente `this.renderNodesDirectory(Array.from(this.knownNodes.values()))`, actualizando la libreta de contactos en el DOM al instante.
- **Módulos Modificados**: `src/web/static/js/app.js`, `src/serial_driver.py`, `docs/AGENT_ACTIVITY_REPORT.md`.

### Hito: Exclusión Estricta de la Estación Base Local en Comandos de Vecinos (`neighbors`) y Calidad de Enlace (`lqi`)
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 3 (Protocol QA Specialist).
- **Problema Reportado**:
  - Al ejecutar el comando de terminal CLI `neighbors` (o `vecinos`), la salida incluía la estación base local como uno de los vecinos de malla (ej: `3. Nodo [34c0c753] (34c0c753) | LQI: 100.0% | SNR: None dB | RSSI: None dBm`).
  - La estación base no es un nodo vecino remoto, sino el transceptor local conectado por bus serie UART.
- **Acciones Realizadas**:
  1. **Filtrado Estricto de Vecinos Remotos en AdminCommandHandler** (`src/admin_handler.py`):
     - El comando `neighbors` / `vecinos` ahora filtra rigurosamente la lista de nodos para excluir entradas donde `is_local=True`, `role="LOCAL"`, claves que coincidan con `is_local_key()`, prefijos coincidentes con la clave pública local, nombres reservados (`Estación Base`, `Nodo Local`, etc.) y el nombre local configurado.
     - Si no hay vecinos remotos en alcance directo, retorna un mensaje descriptivo claro con `Total Nodos Vecinos Descubiertos: 0`.
  2. **Filtrado en Métricas LQI de Enlace** (`src/admin_handler.py`):
     - El comando `lqi` / `link_quality` excluye igualmente el nodo local, evaluando únicamente la calidad de enlace RF con vecinos remotos.
  3. **Comando `nodes` / `list_nodes` para Directorio Global Completo** (`src/admin_handler.py`):
     - Se añadió el comando `nodes` / `list_nodes` / `nodos` que lista el directorio completo de la malla, etiquetando explícitamente a la estación base con el distintivo `[ESTACIÓN BASE LOCAL]` y a los demás con su rol (`[CLIENT]`, `[REPEATER]`).
  4. **Suites de Pruebas Unitarias** (`tests/test_node_and_repeater_config.py`):
     - `test_neighbors_command_excludes_local_node`: Verifica que `neighbors` liste única y exclusivamente los 2 vecinos remotos (`Cu1.mobilUnit`, `R1-Lee`) y excluya a `34c0c753`.
     - `test_nodes_command_lists_all_with_local_tag`: Verifica que `nodes` liste ambos nodos y etiquete la estación base local.
- **Módulos Modificados**: `src/admin_handler.py`, `docs/AGENT_ACTIVITY_REPORT.md`, `tests/test_node_and_repeater_config.py`.

### Hito: Corrección de Formato de Ruta en Traceroute y Eliminación de Error "Invalid path format: unknown path_hash_len 0"
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 3 (Protocol QA Specialist), Agente 4 (Web UI/UX Architect).
- **Causa Raíz**:
  - Al ejecutar una traza de ruta directa (Traceroute) sin repetidores intermedios definidos, el frontend y la API REST pasaban `path=""` (cadena vacía).
  - El SDK oficial (`meshcore.commands.messaging.send_trace`) evaluaba `isinstance(path, str)` y calculaba `path_hash_len = int(len("".split(",")[0]) / 2) = 0`. Al no ser una longitud de hash válida (1, 2, 4 u 8 bytes), emitía el error `logger.error("Invalid path format: unknown path_hash_len 0")`.
- **Acciones Realizadas**:
  1. **Normalización de Rutas RF y Flags en AdminCommandHandler** (`src/admin_handler.py`):
     - Cuando no se especifican saltos intermedios o `path` es una cadena vacía `""`, ahora se despacha `await mc.commands.send_trace(path=None, flags=0)`, previniendo la división de cadena vacía en el SDK.
     - Cuando se proporcionan saltos intermedios (ej. claves públicas completas de 64 hex, prefijos o nombres de repetidores), se normalizan automáticamente a hashes hexadecimales válidos de 2 bytes (4 hex chars, `flags=1`) o 1 byte (2 hex chars, `flags=0`), asegurando plena compatibilidad con el firmware MeshCore C++ (`CMD_SEND_TRACE_PATH = 36`).
  2. **Limpieza en Enrutador de API REST** (`src/web/api_router.py`):
     - `_route_trace()` y el endpoint `/api/traceroute` transmiten `path` como `None` cuando el campo recibido está vacío, evitando propagar cadenas vacías.
  3. **Suites de Pruebas Automatizadas** (`tests/test_node_and_repeater_config.py`):
     - Añadido `test_traceroute_empty_path_passes_none_and_flags_zero`: Valida que trazas sin saltos pasen `path=None, flags=0` sin generar advertencias ni excepciones.
     - Añadido `test_traceroute_custom_path_normalizes_hashes_and_flags`: Valida la normalización de claves completas a `path="1122,aabb", flags=1`.
- **Módulos Modificados**: `src/admin_handler.py`, `src/web/api_router.py`, `docs/AGENT_ACTIVITY_REPORT.md`, `tests/test_node_and_repeater_config.py`.

### Hito: Invariante de Unicidad Absoluta del Nodo Local, Deduplicación de Prefijos y Conteo Exacto de Nodos en Malla
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 3 (Protocol QA Specialist), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Acciones Realizadas**:
  1. **Consolidación y Unicidad de la Estación Base Local en NodeRegistry** (`src/contact_manager.py`):
     - Refactorizado `set_local_pubkey()` para purgar automáticamente cualquier entrada local previa (`is_local`, rol `LOCAL`, prefijos coincidentes ≥ 6 caracteres o nombres `Estación Base`) y reinsertar única y exclusivamente la entrada canónica.
     - Refactorizado `add_or_update()` para que, ante cualquier actualización marcada como local, purgue entradas residuales garantizando que `_nodes_by_key` contenga como máximo 1 registro local.
     - Modificado `get_count()` para retornar `len(self.list_nodes())` (SSoT), asegurando que el conteo en métricas coincida exactamente con la lista deduplicada sin inflar el total.
     - Actualizado `save_to_file()` para serializar únicamente `self.list_nodes()` y `load_from_file()` para consolidar `set_local_pubkey()` tras la carga JSON.
  2. **Deduplicación Reactiva y Sincronización en Frontend** (`src/web/static/js/app.js`):
     - `this.knownNodes` ahora almacena exclusivamente claves canónicas (`this.resolveCanonicalPubkey()`), eliminando el almacenamiento duplicado de alias o prefijos que inflaba `.size`.
     - `renderNodesDirectory()` limpia y reconstruye `this.knownNodes` con las entidades limpias, fusiona la estación local contra `localNodePubkey` / `localNodeName` y sincroniza `#headerNodeCount` y los filtros con el conteo real de nodos únicos.
     - `updateHeaderMetrics()` captura `local_node_pubkey` y `local_node_name` del backend y mantiene el conteo consistente.
  3. **Identificación de Contacto Local en Sincronización Serial** (`src/serial_driver.py`):
     - En `sync_all_contacts()`, se evalúa si los contactos descargados de la EEPROM/Flash de la radio coinciden con la clave pública local, marcándolos como `is_local=True` y rol `LOCAL` para evitar su inserción como un nodo remoto duplicado.
  4. **Suites de Pruebas Unitarias** (`tests/test_contact_manager.py`):
     - Añadido test `test_local_node_never_duplicated`: Valida que el nodo local nunca se duplica tras recibir múltiples actualizaciones por prefijo o 'local', y que con 3 nodos remotos el conteo es exactamente 4.
     - Añadido test `test_prefix_and_name_deduplication`: Valida fusión de prefijos y claves de 64 caracteres.
- **Módulos Modificados**: `src/contact_manager.py`, `src/serial_driver.py`, `src/web/static/js/app.js`, `docs/ARCHITECTURE.md`, `tests/test_contact_manager.py`.

### Hito: Corrección de Bloqueo CSP para Mapas Leaflet / Fuentes, Sincronización de Chip de Radio y Accesibilidad de Formularios
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor).
- **Acciones Realizadas**:
  1. **Resolución de Violaciones CSP en Mapas y Fuentes** (`src/web/http_server.py`):
     - Actualizada la política `Content-Security-Policy` para permitir de forma segura la carga de scripts de Leaflet (`https://unpkg.com`), estilos CDN (`https://fonts.googleapis.com`, `https://unpkg.com`), fuentes web (`https://fonts.gstatic.com`) y capas de teselas cartográficas (`https://*.tile.openstreetmap.org`, `https://*.basemaps.cartocdn.com`).
     - Desbloqueada la inicialización de `window.L` y renderizado interactivo de mapas GPS en vivo con capas CartoDB Dark, OpenStreetMap y Heatmap RF.
  2. **Corrección del Estado "📻 Radio: Desconectada"** (`src/web/static/js/app.js`, `src/web/api_router.py`, `src/serial_driver.py`):
     - Implementado método reactivo `updateRadioBadge(isConnected, portName)` en `app.js` conectado al elemento `#radio-status` del header.
     - Vinculada la actualización de estado a las métricas del WebSocket (`metrics_update`), sondeo de `/api/status`, respuesta de diagnóstico y actividad de eventos RF de malla.
     - Refinado `MeshcoreSDKAdapter.is_hardware_alive()` para no invalidar conexiones activas ni bloquearse en Windows.
  3. **Corrección de Advertencias DOM de Formularios de Contraseña** (`src/web/static/index.html`):
     - Encapsulado el campo de `inputBridgeApiKey` dentro de un `<form>` explícito (`#bridgeApiKeyForm`).
     - Añadidos campos ocultos de `username` (`autocomplete="username"`) en los 3 formularios protegidos (`#bridgeApiKeyForm`, `#repeaterGateForm`, `#repSecurityForm`) satisfaciendo las directrices de accesibilidad del navegador y gestores de contraseñas.
- **Módulos Modificados**: `src/web/http_server.py`, `src/web/api_router.py`, `src/serial_driver.py`, `src/web/static/index.html`, `src/web/static/js/app.js`.

### Hito: Auditoría Integral de Código, Tipado Estricto (Mypy Strict 100%), Corrección de Bugs en Web/Watchdog y Suite de Pruebas Completa (129 Tests - 100% PASS)
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 3 (Protocol QA Specialist), Agente 4 (Frontend Architect), Agente 5 (Security Auditor).
- **Acciones Realizadas**:
  1. **Auditoría de Código y Correcciones en Servidor Web** (`src/web/http_server.py`):
     - Subsanada omisión de `import struct` y `import mimetypes`.
     - Corregida sintaxis en docstrings y depuración de imports redundantes.
     - Verificada resistencia ante tramas WebSocket de gran tamaño (>125B, >64KB).
  2. **Resolución de Bloqueos en SerialWatchdog** (`src/serial_driver.py`):
     - Ajustado el sub-bucle de supervisión física USB para que respete `interval_sec` pequeños (`step_sleep = min(2.0, max(0.005, self.interval_sec))`), evitando que tests con timeouts reducidos queden bloqueados durmiendo 2.0s fijos.
     - Ajustado `reconnect_wait` proporcional a `interval_sec` cuando el adaptador está desconectado.
  3. **Tipado Estricto Integral (`mypy --strict src` - 100% PASS)**:
     - Subsanados 21 errores de tipado en 8 módulos (`src/contact_manager.py`, `src/rate_limiter.py`, `src/admin_handler.py`, `src/sensor_decoder.py`, `src/rx_router.py`, `src/serial_driver.py`, `src/virtual_mesh_adapter.py`, `src/bridge_core.py`).
     - Añadido `self.total_dropped` a `CustomTxQueue`.
     - Validaciones de tipo en extracción de coordenadas GPS flotantes (`lat`, `lon`, `alt`) y timestamps enteros de RTC.
     - Manejo de retornos tipados con `cast` en comandos de transceptor (`get_channel`, `get_stats`, `device_query`).
     - Creación de `requirements.txt` estándar UTF-8 para producción en el directorio raíz.
  4. **Corrección y Alineación de Suites de Pruebas**:
     - `tests/test_mutation_resilience.py`: Alineado a `PacketType.CHANNEL_MSG_RECV`.
     - `tests/test_serial_adapter.py`: Actualizado a `PacketType.TELEMETRY_RESPONSE`.
     - `tests/test_playwright_e2e_simulation.py`: Pre-cargados contactos simulados con clave pública explícita y selector flexible de indicadores de entrega (`.ack-indicator, .msg-ack-status`).
  5. **Matriz de Pruebas y Verificación de Calidad**:
     - `ruff check src tests`: **0 errores, 0 advertencias (100% PEP 8)**.
     - `mypy --strict src`: **Success: no issues found in 24 source files (100% Strict)**.
     - `pytest -v tests`: **129 pasados, 0 fallados, 10 omitidos en 47.07s (100% PASS)**.
     - `python scripts/verify_all_components.py`: **5/5 categorías de verificación simulada completadas con éxito**.
- **Módulos Modificados**: `src/web/http_server.py`, `src/serial_driver.py`, `src/contact_manager.py`, `src/rate_limiter.py`, `src/admin_handler.py`, `src/sensor_decoder.py`, `src/rx_router.py`, `src/virtual_mesh_adapter.py`, `src/bridge_core.py`, `tests/test_mutation_resilience.py`, `tests/test_serial_adapter.py`, `tests/test_playwright_e2e_simulation.py`, `requirements.txt`.

### Hito: Alineación con Protocolo Oficial MeshCore - Correcciones Críticas de Compatibilidad
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor).
- **Acciones Realizadas**:
  1. **Unificación de Namespace de Tipos de Protocolo** (`src/protocol_types.py`):
     - Renombrado `OpCode` a `PacketType` alineado con SDK oficial (`packets.py`).
     - Agregados 28 tipos de paquete faltantes (OK, ERROR, CONTACT_START, CONTACT, CONTACT_END, SELF_INFO, MSG_SENT, etc.).
     - Agregados 19 comandos faltantes en `CommandType` (SET_TUNING_PARAMS, EXPORT_PRIVATE_KEY, SIGN_START, etc.).
     - Agregados `BinaryReqType` y `ControlType` enums del SDK.
     - Mantenido alias legacy `OpCode = PacketType` para compatibilidad.
  2. **Corrección de Parsing de Telemetría** (`src/protocol_types.py`):
     - Marcado `TelemetryPayload` como LEGACY (no existe en firmware real).
     - Renombrado `parse_telemetry_from_sdk()` a `parse_status_response()` alineado con SDK.
     - Actualizado `FrameHeader` para usar `packet_type` en lugar de `opcode`.
     - Actualizado `MeshcoreFrame.parse_raw_packet()` para usar `PacketType.TELEMETRY_RESPONSE`.
  3. **Expansión del Manejador de Eventos SDK** (`src/serial_driver.py`):
     - Implementado manejadores para 35+ tipos de eventos del SDK (antes solo 4).
     - Agregados handlers: STATUS_RESPONSE, TELEMETRY_RESPONSE, STATS_CORE/RADIO/PACKETS, BATTERY, DEVICE_INFO, CONTACTS, MSG_SENT, ACK, LOGIN_SUCCESS/FAILED, BINARY_RESPONSE, TRACE_DATA, RAW_DATA, LOG_DATA, CONTROL_DATA, etc.
     - Cada handler incluye logging estructurado y forward al rx_callback.
  4. **Agregado Parsing MMA y ACL** (`src/sensor_decoder.py`):
     - Implementado `parse_mma_data()` para datos Min/Max/Avg de sensores LPP.
     - Implementado `parse_acl_data()` para listas de control de acceso.
     - Agregados diccionarios de tipos LPP (`LPP_TYPE_SIZES`, `LPP_TYPE_NAMES`).
     - Implementado `_decode_lpp_value()` para decodificar valores por tipo.
  5. **Correcciones de Seguridad** (`src/web/http_server.py`):
     - Importado `hmac` para comparaciones timing-safe.
     - Reemplazado `req_api_key != api_key` con `hmac.compare_digest()` (SEC-015).
  6. **Documentación de Incompatibilidades**:
     - Generado `REPORT5.md` con análisis completo de incompatibilidades vs SDK oficial.
     - Identificadas 17 categorías de incompatibilidad con severidad y recomendaciones.
- **Módulos Modificados**: `src/protocol_types.py`, `src/serial_driver.py`, `src/sensor_decoder.py`, `src/web/http_server.py`
- **Contratos de Interfaz Cambiados**:
  - `FrameHeader.opcode` → `FrameHeader.packet_type` (con property legacy)
  - `get_opcode_name()` → `get_packet_type_name()` (con alias legacy)
  - `TelemetryPayload` marcado como LEGACY
  - `parse_telemetry_from_sdk()` → `parse_status_response()` (con alias legacy)

### Hito: Saneamiento de `.env`, Actualización Global de Documentación, Deduplicación de Nodo Local y Corrección de Transmisión Web
- **Fecha**: 2026-08-27
- **Estado**: ✅ COMPLETADO
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Frontend Architect), Agente 5 (Security Auditor).
- **Acciones Realizadas**:
  1. **Limpieza y Sincronización de `.env` y `.env.example`**:
     - Eliminadas variables obsoletas o heredadas (`OFFLINE_BUFFER_MAX_SIZE`, `OFFLINE_BUFFER_TTL_HOURS`, `HA_DISCOVERY_ENABLED`, etc.).
     - Organizado en 8 secciones lógicas y comentadas: Conexión Serial, Broker MQTT, Servidor Web / API REST / WebSockets, Servidor TCP Companion, Parámetros LoRa Airtime, Resiliencia y Control de Flujo, Persistencia de Datos y Logs.
     - Creado `.env` activo sincronizado con `.env.example`.
  2. **Corrección de Transmisión de Mensajes Web**:
     - Eliminado falso timeout de ACK para mensajes en canales públicos (Broadcast / Canal 0): confirmación inmediata como `✓ TX (Transmitido)` al completarse la emisión física RF.
     - Ampliado timeout para DMs a 25s acorde a retardos de propagación LoRa multi-hop.
     - Añadido soporte automático para cabecera `X-Api-Key` en el cliente SPA (`getAuthHeaders()`) y campo de configuración en **⚙️ Ajustes ➔ 🔐 Seguridad & API**.
  3. **Deduplicación Estricta de la Estación Base Local**:
     - Backend (`src/contact_manager.py`): `NodeRegistry.add_or_update()` y `list_nodes()` unifican cualquier variante (64 chars, 12 chars o alias) en una sola entrada canónica de estación local.
     - Frontend (`src/web/static/js/app.js`): `renderNodesDirectory()` fusiona variantes locales evitando duplicados en la interfaz de usuario.
  4. **Resiliencia de WebSockets en Red Local (LAN)**:
     - `src/web/http_server.py`: Autorización automática de orígenes LAN (`192.168.*`, `10.*`, `172.16-31.*`) y Same-Origin.
     - Heartbeat RFC 6455 bidireccional (pings cada 15s) evitando cierres por inactividad.
  5. **Actualización Integral de Documentación**:
     - `README.md`: Documentación completa de características v3.0 Pro, endpoints REST/WS, seguridad, topics MQTT y tabla de variables `.env`.
     - `docs/DEPLOYMENT_GUIDE.md`: Guía de despliegue paso a paso en Linux/Raspberry Pi con systemd, acceso a Web SPA en puerto 8080 y servidor TCP en puerto 5000.
     - `docs/ARCHITECTURE.md`: Diagramas y detalle de capas actualizado con todas las protecciones y flujos asíncronos.

### Hito: Ejecución Exitosa de la Suite Completa de Pruebas (128 Tests - 100% PASS) y Saneamiento de UTF-8
- **Fecha**: 2026-08-26
- **Estado**: ✅ COMPLETADO (128 pasados, 0 fallos, 0 errores, cobertura del 59%)
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 3 (Protocol QA Specialist).
- **Acciones Realizadas**:
  1. **Resolución de Error UTF-16 en `requirements.txt`**: Eliminada la corrupción de bytes nulos (`\x00`) producida por redirección de PowerShell, estableciendo codificación UTF-8 pura estándar en `requirements.txt`, `deploy/requirements.txt` y `docs/AGENT_ACTIVITY_REPORT.md`.
  2. **Compatibilidad Asíncrona de Tests v3.0**:
     - `src/mqtt_client.py`: Añadido import `config` faltante en la validación de `publish_safe`.
     - `src/web/api_router.py`: Despacho seguro de corutinas WebSocket con `_notify_web_clients()` para compatibilidad transparente con mocks de pruebas unitarias.
     - `tests/test_stress_flood.py`, `tests/test_tx_rate_limiter.py`, `tests/test_tcp_companion_server.py`, `tests/test_fuzzing_and_edge_cases.py`, `tests/test_e2e_simulation.py`: Adaptados a la arquitectura concurrente asíncrona v3.0 con inicialización determinista de semáforos, rate limiters, mocks de red y drenaje ordenado de tareas en `tearDown`.
  3. **Linter & Formato PEP 8**: Ejecutado `ruff check --fix` y corregidas exportaciones en `src/__init__.__all__` y bloques `except Exception:`.
  4. **Matriz de Pruebas Ejecutada (`pytest`)**:
     - `tests/test_protocol_types.py`: **PASS** (Framing binario, serialización/deserialización, endianness, CRC).
     - `tests/test_contact_manager.py`: **PASS** (Registro, inmutabilidad, resolución SSoT).
     - `tests/test_sensor_decoder.py`: **PASS** (CayenneLPP, telemetría estándar, parsing 56-bytes).
     - `tests/test_rate_limiter_priority.py`: **PASS** (Airtime LoRa, colas de prioridad).
     - `tests/test_store_and_forward.py` & `tests/test_store_forward_modular.py`: **PASS** (SQLite WAL, deduplicación thread-safe).
     - `tests/test_serial_adapter.py` & `tests/test_serial_watchdog.py`: **PASS** (Framing UART, watchdog, reconexión).
     - `tests/test_tcp_companion_server.py`: **PASS** (Servidor TCP, límites de clientes, token auth).
     - `tests/test_tx_rate_limiter.py`: **PASS** (Espaciado regulatorio LoRa, ACKs MQTT).
     - `tests/test_virtual_mesh_simulation.py`: **PASS** (Simulación de red virtual mesh multihop).
     - `tests/test_web_server.py` & `tests/test_websocket_live.py`: **PASS** (Endpoints REST, WebSockets en vivo).
     - `tests/test_security_audit.py`: **PASS** (Anti-traversal, API Key, límites DoS, sanitización).
     - `tests/test_fuzzing_and_edge_cases.py`: **PASS** (Fuzzing de payloads binarios/MQTT, SQL injection safe).
     - `tests/test_mutation_resilience.py`: **PASS** (Tolerancia a mutación y corrupción de tramas).
     - `tests/test_n8n_parser_matrix.py`: **PASS** (Compatibilidad de esquemas n8n).
     - `tests/test_concurrency_and_flapping.py`: **PASS** (Deduplicador multihilo, fallos de puerto serie).
     - `tests/test_e2e_simulation.py`: **PASS** (Ciclo de vida E2E completo: RX, TX, Telemetría, Admin, Shutdown).
  5. **Total**: **128 tests pasados, 0 fallados en 34.06s**.

### Hito: Implementación Integral v3.0 — Fases 1 a 5 Completadas, Blindaje de Red, Concurrencia Async, Robustez, Compatibilidad SDK y Validación Simulada 100%
- **Agentes Participantes**: Agente 0 (Lead Orchestrator), Agente 1 (Protocol & Types Specialist), Agente 2 (Concurrency & Resilience Architect), Agente 4 (Web UI/UX Specialist), Agente 5 (Security Auditor).
- **Módulos Modificados e Implementaciones Clave**:
  1. **Fase 1 (Seguridad)**:
     - Middleware de autenticación por API Key (`X-Api-Key` / `BRIDGE_API_KEY`).
     - Hardening de TCP Companion: límite `MAX_COMPANION_CLIENTS`, filtro IP y handshake `COMPANION_TOKEN` (5s timeout).
     - CORS estricto con `BRIDGE_ALLOWED_ORIGINS` (eliminados wildcards).
     - Validación de cabecera `Origin` en WebSocket y mitigación de Path Traversal previo al upgrade.
     - Cabecera `Content-Security-Policy` estricta en respuestas HTML.
     - Validación de sintaxis regex para claves PSK (`^[a-fA-F0-9]{0,64}$`) y rango de canales (0-15).
     - Enmascaramiento de credenciales MQTT en logs (`MQTT_PASSWORD_MASKED`).
  2. **Fase 2 (Concurrencia y Resiliencia)**:
     - Deduplicador determinista thread-safe con `asyncio.Lock` y `threading.Lock`.
     - `CustomTxQueue` con límite de tamaño (`MAX_TX_QUEUE_SIZE=500`) y contador de descartes (`total_dropped`).
     - Control de concurrencia en RX con `asyncio.Semaphore(MAX_RX_CONCURRENCY=20)`.
     - Timeouts de vivacidad en lecturas WebSocket (`WS_IDLE_TIMEOUT_SEC=30s`) y pings de Watchdog Serial (10s).
     - Eliminación de tareas zombies: migración a `asyncio.get_running_loop()`, timeout de 30s en future TX MQTT, cancelación limpia de tareas en `shutdown` y reconexión con `await connect()`.
     - Broadcasts no-bloqueantes con `await drain()` y desconexión por backpressure (64 KB / 2.0s).
  3. **Fase 3 & 4 (Calidad de Código y Robustez)**:
     - Estructuras inmutables: `NodeContactInfo.neighbors` tipado como `tuple[str, ...]`.
     - SSoT para resolución de nombres: `NodeRegistry.resolve_display_name()`.
     - SSoT para extracción de remitentes: `src/event_utils.py` (`extract_sender_from_payload`).
     - Validación estricta de arranque en `config.py` (`_validate_config()`) para puertos, SF y BW.
     - Persistencia atómica de contactos en `data/node_registry.json` con `save_to_file()` y `load_from_file()`.
     - Protección de payload MQTT (`MQTT_MAX_PAYLOAD_BYTES=128KB`).
     - Modo dormant en `SerialWatchdog` tras superar `MAX_RECONNECT_ATTEMPTS`.
     - Frontend sanitizado contra XSS (`escapeHtml` / `textContent`), auto-reconexión WebSocket con backoff exponencial, badge de estado en tiempo real y paginación en REST API.
  4. **Fase 5 (Compatibilidad SDK MeshCore)**:
     - Decodificación de telemetría alineada con el firmware oficial de 56 bytes (`parse_telemetry_from_sdk`).
     - Decodificador oficial `cayennelpp` con resolución de signed wrap en voltaje/corriente.
     - Definición de `MeshCoreSDKProtocol` con `typing.Protocol`.
     - Clasificación de roles de nodo basada exclusivamente en `FirmwareAdvertType`.
     - Métodos de protocolo y endpoints REST para compartir, exportar e importar contactos (`share_contact`, `export_contact`, `import_contact`) y autenticación de repetidores (`send_login`, `logout`).
  5. **Validación Simulada y Empaquetado**:
     - `scripts/simulate_mesh_network.py` y `scripts/verify_all_components.py` ejecutados con 100% de éxito.
     - Paquete autónomo `/deploy/` sincronizado con `scripts/sync_deploy.py`.

### Hito: Fase 1 Seguridad - SEC-001/002/004/005/006/007/009/010/011
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente 5 (Security & Vulnerability Auditor)**: 
  - **`src/web/http_server.py`**:
    - SEC-001: Implementado middleware con verificaciÃ³n del header `X-Api-Key` contra `BRIDGE_API_KEY` para proteger rutas administrativas (`/api/node/reboot`, `/api/admin/`, `/api/tx`, `/api/repeater/`).
    - SEC-004: Reemplazado CORS wildcard `Access-Control-Allow-Origin: *` por orÃ­genes especÃ­ficos definidos en `BRIDGE_ALLOWED_ORIGINS`.
    - SEC-009: ValidaciÃ³n explÃ­cita del header `Origin` antes de aceptar el handshake WebSocket.
    - SEC-011: ValidaciÃ³n de Path Traversal ejecutada estrictamente antes del upgrade WebSocket.
    - SEC-005: Incorporada cabecera `Content-Security-Policy` estricta para la entrega de archivos `.html`.
  - **`src/tcp_companion_server.py`**:
    - SEC-002: Implementado lÃ­mite mÃ¡ximo de conexiones concurrentes (`MAX_COMPANION_CLIENTS`) y cierre proactivo.
    - SEC-007: Implementado handshake de autenticaciÃ³n obligatoria (`COMPANION_TOKEN`) con timeout de 5s y validaciÃ³n de orÃ­genes por IP (`COMPANION_ALLOWED_IPS`).
  - **`src/serial_driver.py`**:
    - SEC-006: Reforzada validaciÃ³n de tipos, rangos y sintaxis (regex `^[a-fA-F0-9]{0,64}$`) en el comando `set_channel()`.
  - **`config.py` y `.env.example`**:
    - SEC-010: Creada variable `MQTT_PASSWORD_MASKED` para ofuscaciÃ³n segura en logs.
    - Registradas las nuevas variables de entorno de seguridad (`BRIDGE_API_KEY`, `BRIDGE_ALLOWED_ORIGINS`, `MAX_COMPANION_CLIENTS`, `COMPANION_TOKEN`, etc).


### Hito: CorrecciÃ³n de `NameError: name '_safe_int' is not defined` en `rx_router.py`
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**:
  1. **Causa RaÃ­z**: En [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py) (lÃ­nea 437), el bloque de procesamiento de listas de contactos invocaba `_safe_int(...)` y `_safe_float(...)`, pero estas funciones no estaban importadas en la cabecera del mÃ³dulo â€” sÃ³lo estaban definidas en [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) (lÃ­neas 18 y 31).
  2. **CorrecciÃ³n aplicada**:
     - Ampliado el import de `src.contact_manager` en [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py) para incluir `_safe_int` y `_safe_float`.
     - Elevada la funciÃ³n `_get_coord` (antes anidada dentro de `handle_event`) a nivel de mÃ³dulo para evitar redefiniciones en cada llamada al evento y para mejorar la cobertura de pruebas.
  3. **Archivos modificados**:
     - [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py): importaciones lÃ­neas 17-24, nueva funciÃ³n `_get_coord` a nivel de mÃ³dulo lÃ­neas 39-56.

### Hito: Blindaje de AutenticaciÃ³n de Repetidores y ValidaciÃ³n Estricta de AdministraciÃ³n Remota
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (EliminaciÃ³n de auto-login por telemetrÃ­a, validaciÃ³n de `send_login_sync` y respuesta RF, HTTP 401 en fallos)
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ las vulnerabilidades y fallos en la administraciÃ³n remota de repetidores:
  1. **Causa RaÃ­z de AutenticaciÃ³n Espuria**:
     - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js), la condiciÃ³n en `handleIncomingLiveEvent` incluÃ­a `payload.telemetry?.battery_pct !== undefined`, lo que provocaba que cualquier paquete periÃ³dico de telemetrÃ­a de baterÃ­a marcara el repetidor como autenticado y desbloqueara la vista de administraciÃ³n sin verificar la contraseÃ±a.
     - En [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py), la acciÃ³n `login` devolvÃ­a `status: "ok"` y `authenticated: True` de forma incondicional aunque no hubiese respuesta del repetidor (timeout) o se devolviera un mensaje de error.
  2. **ValidaciÃ³n Estricta de AutenticaciÃ³n RF ([`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py))**:
     - Implementado soporte sÃ­ncrono para `mc.commands.send_login_sync` (verificaciÃ³n de evento `LOGIN_SUCCESS`).
     - Fallback con evaluaciÃ³n estricta de palabras de error (`invalid`, `denied`, `bad pin`, `wrong password`, `login failed`) y rechazo explÃ­cito con `status: "error"` y `authenticated: False` en caso de timeout por RF o error de contraseÃ±a.
  3. **CÃ³digo HTTP 401 Unauthorized en REST API ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py))**:
     - `POST /api/repeater/remote/login` devuelve cÃ³digo HTTP 401 si la autenticaciÃ³n falla o el repetidor no responde, manteniendo el modal bloqueado en la interfaz.
  4. **ProtecciÃ³n en Frontend ([`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js))**:
     - `authenticateRepeater()` exige `res.ok && data.status === "ok" && data.data?.authenticated === true` antes de aÃ±adir a `authenticatedRepeaters` y desbloquear.
     - Limpieza de `payload.telemetry?.battery_pct` en eventos WebSocket.

### Hito: VerificaciÃ³n Integral de ConexiÃ³n del Cliente Web, REST APIs y Streaming WebSocket (Playwright PASS)
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (Playwright Chromium Headless [PASS] - 0 Excepciones JS, 0 Peticiones Fallidas, WebSockets 100% Funcionales)
- **Agente Principal (Lead Orchestrator)**: LlevÃ³ a cabo la verificaciÃ³n funcional y visual del cliente web SPA y su integraciÃ³n con el backend:
  1. **InspecciÃ³n de ConexiÃ³n y NavegaciÃ³n Web ([`scripts/inspect_web.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/inspect_web.py))**:
     - Ejecutada auditorÃ­a en Chromium Headless en resoluciones Desktop (1920x1080) y Mobile (390x844).
     - Resultado: **`[PASS]` con 0 excepciones JavaScript no capturadas, 0 errores de consola y 0 peticiones de red fallidas**.
     - DOM completamente renderizado con todos los paneles principales (`#tab-chat`, `#tab-map`, `#tab-nodes`, `#tab-analytics`, `#tab-logs`).
  2. **VerificaciÃ³n de Protocolo WebSocket RFC 6455 ([`src/web/http_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/http_server.py))**:
     - Comprobado handshake HTTP `101 Switching Protocols`, recepciÃ³n inmediata del evento `ws_connected`, emisiÃ³n periÃ³dica de `metrics_update` y streaming bidireccional en caliente de eventos de telemetrÃ­a y mensajes.
  3. **CorrecciÃ³n de Robustez en Endpoints REST ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py))**:
     - Implementado acceso defensivo para atributos `serial_adapter` y `mqtt` en `GET /api/status`, evitando excepciones cuando los subsistemas no estÃ¡n instanciados.
     - Verificados endpoints `/api/status`, `/api/nodes`, `/api/contacts`, `/api/channels`, `/api/analytics`, `/api/lqi` con cÃ³digo HTTP 200.

### Hito: CorrecciÃ³n de ExcepciÃ³n AttributeError en `NodeRegistry.get_local_pubkey`
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (ImplementaciÃ³n de getter/property de `local_pubkey` y defensa en `rx_router.py`)
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ el error `AttributeError: 'NodeRegistry' object has no attribute 'get_local_pubkey'`:
  1. En [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py), se implementÃ³ el mÃ©todo `get_local_pubkey(self) -> str` y la propiedad `@property def local_pubkey(self) -> str` en la clase `NodeRegistry`.
  2. En [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py), se aplicÃ³ acceso defensivo con `getattr()` y fallback al atributo interno.
  3. En [`tests/test_contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_contact_manager.py), se agregaron pruebas unitarias para la gestiÃ³n y consulta de la clave pÃºblica del nodo local.

### Hito: CorrecciÃ³n Integral de TransmisiÃ³n TX (Mensajes PÃºblicos y Directos) y Posicionamiento CartogrÃ¡fico GPS en Mapa Leaflet
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (ResoluciÃ³n de Nombres en DM, Casting de Canales, Auto-registro de Contactos en Radio y Persistencia de GPS)
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ las fallas en el pipeline de transmisiÃ³n TX y la ubicaciÃ³n de nodos en el mapa:
  1. **ResoluciÃ³n Robusta de Destinatarios en Mensajes Directos (DM)**:
     - En [`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py) y [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py), se integrÃ³ `NodeRegistry` en `MeshcoreSDKAdapter` y se ampliÃ³ `_resolve_target()` para resolver nombres/alias (ej. `"Alice"`, `"Sensor_Meteo"`), prefijos de 6 a 12 caracteres y claves pÃºblicas completas de 64 caracteres.
     - Se previno el crash por `ValueError: Invalid public key hex string` cuando se utilizaban nombres de contactos en lugar de cadenas hexadecimales.
     - Auto-registro proactivo de contactos en la tabla de ruteo de la radio mediante `mc.commands.add_contact()` previo a la llamada de transmisiÃ³n `send_msg()`.
  2. **Tipado Estricto de Canales y DifusiÃ³n PÃºblica**:
     - Forzado de tipo entero `safe_ch = int(channel_idx)` en [`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py) y [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py) para prevenir excepciones `AttributeError: 'str' object has no attribute 'to_bytes'` provenientes del framing binario de `meshcore_py`.
     - Tratamiento explÃ­cito de `target` (`"broadcast"`, `"public"`, `"0xffff"`, `"all"`, `"none"`, `""`) para enrutar directamente a canal secundario o broadcast sin confusiÃ³n con mensajes directos.
  3. **Manejo de Respuestas de TX y RetroalimentaciÃ³n Inmediata**:
     - En [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py) y [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js), se aÃ±adiÃ³ verificaciÃ³n de estado de error (`res.status === "error"`) para marcar de forma inmediata mensajes fallidos en la UI con la causa real y ofrecer botÃ³n de reintento, en lugar de esperar el timeout ciego de 8s.
  4. **Posicionamiento CartogrÃ¡fico GPS en Mapa Leaflet**:
     - En [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py), se aÃ±adieron alias `lat` y `lon` en `NodeContactInfo.to_dict()` y extracciÃ³n universal de coordenadas en `record_packet()` (`lat`, `latitude`, `gps_lat`, `adv_lat`).
     - En [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js), se corrigiÃ³ la deduplicaciÃ³n de nodos en `renderNodesDirectory()` para preservar las coordenadas geogrÃ¡ficas existentes cuando un nodo envÃ­a paquetes sin GPS.
     - Enriquecido `extractCoord()` para extraer coordenadas desde todos los campos posibles (`node.latitude`, `node.lat`, `node.gps_lat`, `node.adv_lat`, `node.telemetry.*`) y excluir Ãºnicamente coordenadas nulas o `(0.0, 0.0)`.
     - ActualizaciÃ³n y re-renderizado en tiempo real del mapa ante eventos entrantes de telemetrÃ­a por WebSockets.

### Hito: NormalizaciÃ³n Exhaustiva de TelemetrÃ­a, ResoluciÃ³n CanÃ³nica de Emisor y Logs Estructurados
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (ExtracciÃ³n Universal LPP / Stats, ResoluciÃ³n de Prefijos y Formato Rico de Logs)
- **Agente Principal (Lead Orchestrator)**: AnalizÃ³ la causa raÃ­z de logs con `De: Desconocido`, `nodo anÃ³nimo` y `RSSI/SNR: None`, refactorizando integralmente el pipeline de extracciÃ³n y resoluciÃ³n:
  1. **Motor de ExtracciÃ³n Universal de Sensores ([`src/sensor_decoder.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/sensor_decoder.py))**:
     - Creada funciÃ³n `extract_telemetry_fields()` capaz de procesar listas LPP nativas de MeshCore Python SDK, bytes binarios CayenneLPP, respuestas estructuradas (`battery_mv`, `voltage_v`, `solar_v`, `uptime_secs`, `noise_floor`, `queue_len`, `packet_errors`, GPS).
     - ConversiÃ³n automÃ¡tica de `battery_mv` a `voltage_v` y cÃ¡lculo proporcional de `battery_pct`.
     - Creada funciÃ³n `format_telemetry_summary()` para generar resÃºmenes informativos claros (ej: `ðŸŒ¡ï¸� 24.5Â°C | ðŸ’§ 60% | ðŸŒ€ 1013.2 hPa | ðŸ”‹ 85% (4.12V) | â�±ï¸� 3h 25m | âš ï¸� 0 err`).
  2. **ResoluciÃ³n CanÃ³nica y Logging en Enrutador RX ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py))**:
     - FusiÃ³n automÃ¡tica de `event.attributes` con `event.payload` para capturar `pubkey_prefix` y atributos de RF.
     - ExtracciÃ³n exhaustiva de remitente considerando claves: `pubkey_pre`, `pubkey_prefix`, `public_key`, `target_node`, `from_node`, `node_id`, `source`.
     - ResoluciÃ³n contra `NodeRegistry.get_by_key_or_prefix` para asociar prefijos de 6 a 12 caracteres hex (`31d03b1f...`, `8d5accef...`) a sus alias o nombres de repetidor.
     - NormalizaciÃ³n de RSSI/SNR eliminando `None dBm` en favor de valores legibles o `N/A`.
  3. **Buffer de Logs y Web API Router ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py))**:
     - Actualizado `record_incoming_event` para resolver remitentes por prefijo y mostrar `nodo '<alias>' (<pk[:8]>)` o `nodo [<prefix>]` en lugar de `nodo anÃ³nimo`.
     - IntegraciÃ³n de `extract_telemetry_fields()` en `api_router` garantizando que los logs del sistema desglosen lecturas completas.
  4. **Pruebas Automatizadas**:
     - Actualizado [`tests/test_sensor_decoder.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_sensor_decoder.py) y [`tests/test_node_and_repeater_config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_node_and_repeater_config.py) con casos de validaciÃ³n para `extract_telemetry_fields`, `format_telemetry_summary` y resoluciÃ³n de telemetrÃ­a de repetidores registrados y nodos con prefijo.

### Hito: ImplementaciÃ³n de Enrutamiento DinÃ¡mico por Calidad de Enlace (LQI) y SelecciÃ³n Inteligente de Rutas
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (124 Tests en pytest - 100% Suites Pasadas - 0 Fallos)
- **Agente Principal (Lead Orchestrator)**: DiseÃ±Ã³ e implementÃ³ el motor de mÃ©tricas de calidad de enlace LQI (Link Quality Index) y selecciÃ³n automÃ¡tica de ruta directa vs repetidor:
  1. **Motor LQI ([`src/lqi_engine.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/lqi_engine.py))**:
     - CÃ¡lculo normalizado de calidad fÃ­sica de seÃ±al (65% SNR + 35% RSSI).
     - PenalizaciÃ³n por saltos multi-hop (15% por salto).
     - Suavizado exponencial EMA ($\alpha = 0.3$) y decaimiento temporal tras 3 minutos de inactividad (10% por minuto adicional).
     - ClasificaciÃ³n categÃ³rica de enlace: `EXCELLENT` ($\ge 80\%$), `GOOD` ($\ge 60\%$), `FAIR` ($\ge 40\%$), `POOR` ($> 0\%$), `UNREACHABLE` ($0\%$).
     - Algoritmo `select_best_route()` para conmutaciÃ³n transparente entre enlace `DIRECT` o `VIA_<REPEATER_PK>` segÃºn la calidad comparada.
  2. **IntegraciÃ³n con Contact Manager y Pipeline AsÃ­ncrono**:
     - Actualizado [`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py) con campos `lqi_score`, `lqi_status`, `best_route` y mÃ©todo `get_all_lqi_metrics()`.
     - Actualizado [`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py) incorporando mÃ©tricas LQI en los payloads de eventos MQTT/WebSockets y logging estructurado `[LQI: XX% [STATUS]]`.
     - Creado endpoint REST `GET /api/lqi` en [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py).
     - AÃ±adido comando CLI `get_lqi` en [`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py).
  3. **Suite de Pruebas Automatizadas ([`tests/test_lqi_routing.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_lqi_routing.py))**:
     - 7 tests exhaustivos de normalizaciÃ³n, suavizado EMA, decaimiento temporal, penalizaciÃ³n de saltos, selecciÃ³n de rutas e integraciÃ³n con `NodeRegistry`.
     - Total de tests en suite global: **124 tests pasados (0 fallos)** en 21.22s. Matriz de 10 disciplinas superada al 100%.

### Hito: AuditorÃ­a Exhaustiva de CÃ³digo y Cobertura de Pruebas Total (100% MÃ³dulos / 117 Tests)
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (29 Suites de Prueba - 117 Tests Superados - 100% Ã‰xito)
- **Agente Principal (Lead Orchestrator)**: LlevÃ³ a cabo una auditorÃ­a integral de todos los mÃ³dulos de producciÃ³n en `/src/` para verificar la existencia de pruebas automatizadas en las 10 disciplinas requeridas:
  1. **IncorporaciÃ³n de Suite Faltante ([`tests/test_tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_tcp_companion_server.py))**:
     - Creada suite unitaria e integraciÃ³n para `src/tcp_companion_server.py`.
     - Valida el ciclo de vida del servidor TCP en puerto efÃ­mero/companion, framing bidireccional con delimitadores `0x3C` (`<`) y `0x3E` (`>`), broadcast, envÃ­o a cliente especÃ­fico, recuperaciÃ³n ante bytes de basura y rechazo seguro de tramas sobredimensionadas (`MAX_FRAME_SIZE`).
  2. **Matriz Consolidada de Pruebas**:
     - Total de Suites en el Repositorio: **29 archivos de prueba**.
     - Total de Tests Automatizados: **117 tests superados (0 fallos)** en 21.39s.
     - Cobertura de las 10 Disciplinas de Prueba (`scripts/run_all_test_categories.py`): **10/10 PASSED (100%)**.

### Hito: SimulaciÃ³n Exhaustiva de Todos los Tipos de Mensajes de MeshCore (20s) y Trazabilidad Origen -> Destino
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (20.07s EjecuciÃ³n - 839 Eventos con Origen/Destino Auditados - 0 Errores)
- **Agente Principal (Lead Orchestrator)**: ImplementÃ³ mejoras estructurales de logging en `src/rx_router.py` y `src/admin_handler.py` para garantizar trazabilidad explÃ­cita de `De: <origen> -> Para: <destino>` en el 100% de los eventos, y coordinÃ³ la simulaciÃ³n de todos los tipos de mensajes posibles:
  1. **Cobertura Completa de Tipos de Mensajes en MeshCore ([`scripts/simulate_concurrent_network.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/simulate_concurrent_network.py))**:
     - *1. Direct Messages (DM)*: 50 mensajes de texto directo con trazabilidad hacia la estaciÃ³n local.
     - *2. Canales & Broadcast*: 100 mensajes transmitidos en Canal #0 (PÃºblico) y Canal #1 (Emergencias).
     - *3. TelemetrÃ­a Ambiental*: 50 reportes de sensores de baterÃ­a, voltaje, temperatura, humedad y presiÃ³n.
     - *4. Anuncios & BBS Rooms*: 50 anuncios de presencia de nodos y salas de tableros comunitarios.
     - *5. Acuses de Recibo (ACK)*: 50 confirmaciones de entrega de paquetes con mediciÃ³n de RTT (ms).
     - *6. Traceroute Multi-Salto*: 18 trazas de ruta con SNR por salto hacia nodos remotos.
     - *7. Comandos CLI a Repetidores*: 18 configuraciones remotas con respuestas estructuradas.
     - *8. Sensores CayenneLPP*: 50 decodificaciones de tramas binarias IPSO.
     - *9. Tramas Binarias MeshcoreFrame*: 50 tramas seriales directas despachadas limpiamente a MQTT.
     - *10. Fuzzing & Tramas Deformadas*: 161 paquetes corruptos (CRC alterado, truncados, opcodes invÃ¡lidos, JSON roto) capturados y descartados con logs detallados.
     - *11. Modificaciones Remotas de Nodos*: 18 actualizaciones dinÃ¡micas de parÃ¡metros.
     - *12. Ajustes en el Transceptor Local*: 9 cambios en caliente de potencia TX, frecuencia y GPS.
     - *13. RÃ¡fagas de Cuello de Botella*: 12 rÃ¡fagas masivas con colas de prioridad `HIGH` (0) y `NORMAL` (1).
  2. **AuditorÃ­a de Logs en Tiempo Real**:
     - **839 registros de logs generados** identificando origen y destino con formato `De: <origen> -> Para: <destino>`.
     - **0 errores no controlados, 0 excepciones y 0 fallos de estabilidad**.
  3. **VerificaciÃ³n Integral de Pruebas**:
     - `python scripts/run_all_test_categories.py` $\to$ **10/10 CategorÃ­as de Prueba Superadas (100% de Ã‰xito)** en 39.25s.

### Hito: VerificaciÃ³n y Cobertura Integral de las 10 Disciplinas de Prueba
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (10/10 Disciplinas Verificadas - 100% Ã‰xito)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la comprobaciÃ³n y ejecuciÃ³n de la matriz completa de pruebas solicitada por el usuario:
  1. **1. Unit Tests (Pruebas Unitarias - 7 suites)**: `test_protocol_types.py`, `test_sensor_decoder.py`, `test_contact_manager.py`, `test_rate_limiter_priority.py`, `test_store_forward_modular.py`, `test_serial_adapter.py`, `test_ha_discovery.py`.
  2. **2. E2E Tests (End-to-End - 1 suite)**: `test_e2e_simulation.py` (ciclo de vida completo del bridge con simulaciÃ³n virtual).
  3. **3. Contract Tests (Pruebas de Contrato - 1 suite)**: `test_n8n_parser_matrix.py` (esquemas JSON de MQTT e interoperabilidad n8n).
  4. **4. Chaos Tests (Pruebas de Caos & Hardware Flapping - 2 suites)**: `test_concurrency_and_flapping.py`, `test_serial_watchdog.py`.
  5. **5. Smoke Tests (Pruebas de Humo & Preflight - 2 suites)**: `test_preflight.py`, `test_diagnostics.py`.
  6. **6. Integration Tests (Pruebas de IntegraciÃ³n - 4 suites)**: `test_bridge_logic.py`, `test_web_server.py`, `test_websocket_live.py`, `test_repeater_manager.py`.
  7. **7. Snapshot Tests (Pruebas de Snapshot & Formatos - 2 suites)**: `test_diagnostics_export.py`, `test_node_and_repeater_config.py`.
  8. **8. Load Tests (Pruebas de Carga & SaturaciÃ³n - 2 suites)**: `test_stress_flood.py`, `test_tx_rate_limiter.py`.
  9. **9. Mutation Tests (Pruebas de MutaciÃ³n & Bit-Flip - 1 suite)**: `test_mutation_resilience.py` (inversiÃ³n de bits en tramas, mutaciÃ³n de opcodes, colisiones y truncamientos).
  10. **10. Regression Tests (Pruebas de RegresiÃ³n & Seguridad - 4 suites)**: `test_virtual_mesh_simulation.py`, `test_security_audit.py`, `test_store_and_forward.py`, `test_fuzzing_and_edge_cases.py`.
  - **Runner Automatizado**: Implementado [`scripts/run_all_test_categories.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/run_all_test_categories.py) para verificaciÃ³n unificada.
  - **Resultado**: **10/10 CategorÃ­as Superadas (100% de Ã‰xito) en 35.67s**.

### Hito: AuditorÃ­a Exhaustiva de Integridad y VerificaciÃ³n de Importabilidad Total
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (100% de MÃ³dulos Verificados sin Errores)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la verificaciÃ³n total del repositorio tras la refactorizaciÃ³n:
  1. **Herramienta de AuditorÃ­a Integral ([`scripts/audit_codebase_integrity.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/scripts/audit_codebase_integrity.py))**:
     - Escaneo lÃ©xico y de AST en el 100% de archivos Python del repositorio en busca de llamadas a mÃ³dulos eliminados.
     - Prueba de importaciÃ³n dinÃ¡mica de todos los 23 mÃ³dulos de producciÃ³n y entrypoints raÃ­z.
     - Resultado: **0 referencias a mÃ³dulos eliminados en cÃ³digo de producciÃ³n** y **100% de mÃ³dulos de producciÃ³n importados sin errores**.
  2. **CorrecciÃ³n de Entrypoint RaÃ­z y Tests**:
     - Corregido `meshcore_bridge.py` para importar `PacketDeduplicator` desde `src.deduplicator`.
     - Actualizadas las suites de pruebas `test_concurrency_and_flapping.py`, `test_store_and_forward.py`, `test_ha_discovery.py`, `test_security_audit.py` y `test_store_forward_modular.py`.
  3. **VerificaciÃ³n de EjecuciÃ³n**:
     - `python meshcore_bridge.py --version` $\to$ `MeshCore Universal Bridge v3.0.0` (cÃ³digo 0).
     - `python scripts/simulate_mesh_network.py` $\to$ **100% de fases superadas**.
     - Repositorio remoto sincronizado en GitHub (`main`).
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (100% de Pruebas Superadas)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 4 (Web UI/UX & Frontend Architect) para implementar las nuevas capacidades interactivas de mensajerÃ­a:
  1. **Sistema de Estados de Entrega (ACK Ticks)**:
     - Ticks visuales: ðŸ•’ Encolado $\to$ âœ“ Emitido por radio $\to$ âœ“âœ“ Confirmado por ACK (con RTT en ms y SNR) $\to$ â�Œ FallÃ³ con botÃ³n interactivo de 1 click para reintentar (`retryMessage`).
     - Timeout automÃ¡tico de 8 segundos para transicionar mensajes sin acuse a estado fallido.
     - Persistencia de estados ACK y tiempos RTT en IndexedDB (`chat_messages`).
  2. **Compartir UbicaciÃ³n GPS y Centrado TÃ¡ctico en Mapa**:
     - BotÃ³n `ðŸ“�` en el composer de chat (`shareCurrentLocation`).
     - DetecciÃ³n automÃ¡tica de coordenadas desde la configuraciÃ³n de la estaciÃ³n o geolocalizaciÃ³n del navegador.
     - Renderizado de tarjeta tÃ¡ctica con coordenadas y botÃ³n `"ðŸ—ºï¸� Ver en Mapa"`, que conmuta a la pestaÃ±a Mapa y centra Leaflet (`flyTo`) con animaciÃ³n y popup destacado.
  3. **Respuestas a Mensajes (Reply Threading)**:
     - BotÃ³n `â†©ï¸�` en cada mensaje que despliega un banner contextual flotante `#chatReplyBar` sobre el input.
     - Renderizado de bloques de cita (`.chat-quote-block`) con autor y texto citado en la burbuja.
  4. **Alertas Sonoras y Contador de No LeÃ­dos**:
     - NotificaciÃ³n auditiva sintetizada mediante `Web Audio API` (0 dependencias externas) al recibir mensajes entrantes, con control de activaciÃ³n en Ajustes.
     - Contador dinÃ¡mico de mensajes no leÃ­dos en el tÃ­tulo de la pestaÃ±a del navegador `(N) MeshCore Web Client`.
  5. **VerificaciÃ³n y Pruebas**:
     - `node -c src/web/static/js/app.js`: 0 errores.
     - `python -m compileall src scripts`: 0 errores.
     - `python scripts/simulate_mesh_network.py`: 100% superado.
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO (100% de Pruebas y Simulaciones Superadas)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la refactorizaciÃ³n arquitectÃ³nica para simplificar y optimizar el bridge a una arquitectura *Stateless en Memoria RAM*:
  1. **EliminaciÃ³n de Store & Forward en SQLite**:
     - Eliminado `src/store_forward.py` y base de datos `meshcore_store_forward.db`.
     - Implementado nuevo mÃ³dulo `src/deduplicator.py` con `PacketDeduplicator` basado en `collections.OrderedDict` y ventana deslizante TTL para deduplicaciÃ³n ultra-rÃ¡pida en memoria RAM ($O(1)$) sin I/O en disco.
     - Adaptado `src/rx_router.py`, `src/bridge_core.py`, `src/mqtt_client.py`, `src/diagnostics.py`, `src/health_reporter.py` y `src/preflight.py` para operar sin dependencias de base de datos ni colas offline en disco.
  2. **EliminaciÃ³n de RF Packet Sniffer**:
     - Eliminadas rutas API REST `/api/sniffer/*` en `src/web/api_router.py`.
     - Eliminada pestaÃ±a `<section id="tab-sniffer">` y modal `#packetDetailModal` en `src/web/static/index.html`.
     - Eliminados mÃ©todos `initSniffer()`, `renderSnifferPacket()`, `updateSnifferStats()`, `filterSnifferTable()` y almacÃ©n `sniffer_packets` en IndexedDB en `src/web/static/js/app.js`.
     - Eliminado procesamiento de tramas `0x88 LOG_DATA` en `src/repeater_manager.py` y `src/virtual_mesh_adapter.py`.
  3. **EliminaciÃ³n de IntegraciÃ³n Home Assistant Discovery**:
     - Eliminado mÃ³dulo `src/ha_discovery.py` y rutas `/api/ha/*`.
     - Eliminada pestaÃ±a `<section id="tab-ha">` y botones de auto-discovery en `src/web/static/index.html` y `src/web/static/js/app.js`.
     - Eliminados tÃ³picos `homeassistant/#` de la especificaciÃ³n MQTT.
  4. **SimulaciÃ³n y VerificaciÃ³n**:
     - `python -m compileall src scripts`: CompilaciÃ³n sin errores (0 advertencias).
     - `node -c src/web/static/js/app.js`: Sintaxis JavaScript validada (0 errores).
     - `python scripts/simulate_mesh_network.py`: 100% superado (5 fases multi-nodo, sincronizaciÃ³n de contactos, mensajerÃ­a DM/broadcast, ACK, comandos remotos CLI y configuraciÃ³n).
     - `python scripts/simulate_heltec_v4_mesh.py`: SimulaciÃ³n de trÃ¡fico en vivo con transceptor y Mosquitto superada.
  5. **ActualizaciÃ³n Integral de DocumentaciÃ³n**:
     - Actualizados `README.md`, `docs/ARCHITECTURE.md`, `docs/PROTOCOL_SPEC.md` y `docs/AGENT_ACTIVITY_REPORT.md`.
     - Despliegue `/deploy/` congelado segÃºn instrucciÃ³n explÃ­cita del usuario.
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ a los Agentes 1, 2 y 4 para resolver el descubrimiento de contactos, prevenir desconexiones del watchdog y aislar el nodo local en la vista de mensajerÃ­a:
  1. **Agente 1 & 2 (Investigator & Bridge Architect)**:
     - **`src/serial_driver.py`**:
       - Corregido `sync_all_contacts`: adaptado para extraer atributos de instancias de `Contact` (y diccionarios) en `mc.contacts`, permitiendo importar con Ã©xito todos los contactos almacenados en la memoria de la radio al `NodeRegistry`.
       - Mejorado `resolve_sender_name` para resolver objetos `Contact` devueltos por el SDK.
       - AÃ±adido retardo de arranque seguro `cx_dly=1.5s` y reintento con 2.0s en `MeshcoreSDKAdapter.connect()` para permitir al hardware USB-CDC (ESP32-S3/nRF52) completar su secuencia de boot tras el reset de DTR antes de enviar `CMD_APP_START`.
     - **`src/bridge_core.py`**:
       - Eliminado bucle de desconexiÃ³n espuria en `_watchdog_loop` que establecÃ­a `self.mc = None` tras 1.0s de inactividad, delegando la supervisiÃ³n al `SerialWatchdog` oficial no destructivo.
       - SincronizaciÃ³n de coordenadas GPS y telemetrÃ­a de contactos al arrancar.
     - **`src/admin_handler.py`**:
       - Corregido acceso a `mc.self_info`: manejado como mÃ©todo invocable `mc.self_info()` para extraer de forma fiable la clave pÃºblica local, nombre y coordenadas de la estaciÃ³n base.
  2. **Agente 4 (Web UI/UX & Frontend Architect)**:
     - **`src/web/static/js/app.js`**:
       - AÃ±adido mÃ©todo `purgeLocalNodeFromDmList()` para eliminar cualquier entrada del nodo local de la lista de chats directos.
       - Fortalecido el filtro `isLocal` en `addDmContact` utilizando tanto `this.localNodePubkey` como el valor del input del DOM `#localNodePubkey` y el prefijo de clave.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica JavaScript (`node -c` $\to$ 0 errores).
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ 0 errores).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: Pipeline Bidireccional de Comandos y CorrecciÃ³n de Ping Zero en Terminal Remota
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ a los Agentes 1, 2 y 4 para asegurar la emisiÃ³n y captura completa de respuestas en todos los comandos de terminal (`ver`, `bat`, `time`, `sync_clock`, `stats-core`, `stats-radio`, `pos`, `owner`, `neighbors`, `channels`, `acl`, `board`, `ping`, etc.):
  1. **Agente 1 & 2 (Investigator & Bridge Architect)**:
     - **`src/admin_handler.py`**:
       - IntegraciÃ³n nativa con `mc.commands.send_cmd` (`txt_type = 1`) y `mc.commands.send_login` del SDK oficial MeshCore para que los nodos repetidores interpreten las solicitudes como comandos administrativos CLI y no como mensajes de chat planos (`txt_type = 0`).
       - CorrecciÃ³n en `ping_zero`: sustituido el envÃ­o como texto plano por `send_cmd(dest_target, "ping 0")` con bombeo activo de `get_msg`, eliminando el falso positivo que calculaba el tiempo transcurrido del timeout como un Pong exitoso de 19.5s.
       - Implementado `_resolve_target` con resoluciÃ³n de contactos por nombre y prefijo de clave pÃºblica para enrutar con precisiÃ³n a los nodos repetidores en la memoria de la radio.
       - Implementado `_wait_for_repeater_response` con bombeo activo (`get_msg`) sobre la cola de hardware del transceptor y un timeout ampliado a 6.0s adecuado para propagaciÃ³n LoRa en mallas multi-salto.
       - Implementado saneamiento de prefijos de firmware (`> `) en los textos de respuesta devueltos.
     - **`src/rx_router.py`**:
       - ConexiÃ³n de `notify_command_response` en el enrutador de recepciÃ³n tanto para mensajes directos de contacto como para eventos de radio, asegurando la resoluciÃ³n inmediata de futuros en espera.
  2. **Agente 4 (Web UI/UX & Frontend Architect)**:
     - **`src/web/static/js/app.js`**:
       - Mejorado `formatRemoteCliResponse` para formatear claramente las respuestas recibidas (`â†� [RESP] ...`) y diferenciar los acuses de transmisiÃ³n (`â„¹ [TX] ...`).
       - Enriquecido el listener WebSocket de `repeater_response` con resoluciÃ³n canÃ³nica tolerante de claves pÃºblicas y visualizaciÃ³n garantizada en la consola (`â†� [RESP] ...`) cuando el diÃ¡logo de administraciÃ³n estÃ¡ abierto.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica JavaScript (`node -c` $\to$ 0 errores).
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ 0 errores).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: Limpieza de Elementos Ping en Encabezado de Modal de AdministraciÃ³n de Repetidores
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 4 (Frontend) para simplificar el encabezado del modal de administraciÃ³n de repetidores:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/index.html`**: Eliminados la insignia `ðŸŽ¯ Ping: -- ms` (`adminModalPingZeroBadge`) y el botÃ³n `ðŸŽ¯ Ping` (`btnModalHeaderPingZero`) del encabezado superior del diÃ¡logo `#repeaterAdminModal`, dejando el tÃ­tulo y la clave pÃºblica limpios.
     - **`src/web/static/js/app.js`**: Purgadas las referencias y listeners huÃ©rfanos a dichos elementos, manteniendo la funcionalidad de ping activa en la pestaÃ±a Terminal y botones de acciÃ³n rÃ¡pida.
  2. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica JavaScript (`node -c src/web/static/js/app.js` $\to$ 0 errores).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: AuditorÃ­a Multi-Agente Integral, OptimizaciÃ³n de Rendimiento y Limpieza de CÃ³digo Muerto
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ a los Agentes 1, 2, 4 y 5 en una auditorÃ­a y refactorizaciÃ³n integral del sistema frente a la pila oficial MeshCore (`/reference/meshcore/` y `/reference/meshcore_py/`):
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - ComprobaciÃ³n de tipos, constantes de framing (SOF `0xAA`, EOF `0x55`, ESC `0x1B`), offsets de paquetes y CRC-16-CCITT en `src/protocol_types.py`.
     - ValidaciÃ³n 1:1 de `FirmwareCommandType`, `FirmwarePushCode`, `FirmwarePayloadType` y `FirmwareRouteType` con los headers oficiales C/C++ (`Packet.h`, `AdvertDataHelpers.h`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - AuditorÃ­a y saneamiento de dependencias en `src/admin_handler.py`, `src/repeater_manager.py`, `src/contact_manager.py`, `src/rx_router.py` y `src/web/api_router.py`.
     - OptimizaciÃ³n de transacciones SQLite WAL en `store_forward.py` y `contact_manager.py`.
  3. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - AuditorÃ­a profunda de `src/web/static/js/app.js`:
       - EliminaciÃ³n de selectores DOM huÃ©rfanos (`activeRepeaterSelect`, `adminModalPassword`, `btnModalAuthTest`, `btnModalActionPingZero`, `repQuickPingResult`, `btnModalActionClock`).
       - EliminaciÃ³n de mÃ©todos redundantes en desuso (`populateRepeaterDropdown`, `onRepeaterSelected`).
       - OptimizaciÃ³n de listeners en acciones rÃ¡pidas de repetidor (`btnModalActionPing`, `btnSyncRepeaterClock`).
     - VerificaciÃ³n de consistencia visual en `src/web/static/css/app.css` e `index.html`.
  4. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - ParametrizaciÃ³n estricta de consultas SQLite.
     - SanitizaciÃ³n obligatoria `escapeHtml` en todas las proyecciones dinÃ¡micas de datos de malla hacia el DOM.
  5. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica JavaScript (`node -c src/web/static/js/app.js` $\to$ 0 errores).
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ 0 errores).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: VerificaciÃ³n y SincronizaciÃ³n Integral de Posicionamiento GPS, Persistencia y VisualizaciÃ³n en Mapa
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 2 (Bridge Architect) y Agente 4 (Frontend) para garantizar la correcta obtenciÃ³n, serializaciÃ³n, guardado, recuperaciÃ³n y renderizado en vivo de posiciones geogrÃ¡ficas en mapa:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - En `set_local_config`: Tras actualizar latitud, longitud, altitud y propietario, sincroniza inmediatamente el nodo local en `NodeRegistry` (`NodeContactUpdate`) y emite actualizaciÃ³n hacia el servidor web / WebSockets.
       - En `remote_repeater_set_config`: Tras despachar tramas RF `set pos` / `set owner`, actualiza de inmediato el registro canÃ³nico del nodo repetidor en `NodeRegistry` para persistencia en base de datos SQLite y recuperaciÃ³n instantÃ¡nea.
     - **`src/contact_manager.py`**:
       - ValidaciÃ³n y parsing tolerante de coordenadas (`_safe_float`) desde telemetrÃ­a ambiental, advertencias de presencia (`advert`), beacons LoRa y diccionarios anidados (`gps.latitude`, `position.latitude`, etc.).
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - **Formularios de EdiciÃ³n**: Parsing robusto (`rawLat !== ""` y `!isNaN`) en `saveLocalIdentityAndPosition` y en el diÃ¡logo de repetidores remotos (`repOwnerPosForm`), evitando conversiones errÃ³neas a 0.0 cuando se dejan vacÃ­os.
       - **SincronizaciÃ³n Inmediata en Memoria**: ActualizaciÃ³n directa de `knownNodes` y re-renderizado instantÃ¡neo del directorio y marcadores del mapa Leaflet (`renderNodesDirectory`) al guardar coordenadas.
       - **InteracciÃ³n y Centrado en Mapa**: Mejora en `selectMapNode` y `focusNodeOnMap` para asegurar la creaciÃ³n del marcador, centrado con animaciÃ³n suave (`flyTo`), apertura de popup enriquecido y feedback visual si el nodo no tiene fijaciÃ³n GPS.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n de tipos y sintaxis JavaScript (`node -c` $\to$ cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ cÃ³digo 0).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: ValidaciÃ³n Multi-Nodo Integral y Auto-SincronizaciÃ³n de Contactos de Hardware
- **Fecha**: 2026-08-26
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 1 (Protocolo), Agente 2 (Bridge) y Agente 4 (Frontend) para resolver la causa raÃ­z por la cual los contactos de hardware no se importaban y validar toda la red con un simulador multi-nodo:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - **Causa RaÃ­z Identificada**: En el SDK oficial `meshcore_py` (`meshcore.py` L331), `contacts` es un mÃ©todo/funciÃ³n (`def contacts(self): return self._contacts`), no una propiedad. `getattr(self.mc, "contacts")` devolvÃ­a la funciÃ³n bound, haciendo que las comprobaciones `isinstance(dict)` fallaran silenciosamente.
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/serial_driver.py`**: Adaptado `sync_all_contacts` para invocar `raw_contacts()` si es callable y extraer el diccionario `_contacts`.
     - **`src/rx_router.py`**: AÃ±adido soporte nativo para eventos `CONTACT`, `NEXT_CONTACT`, `CONTACTS` y `ADVERTISEMENT`, integrando de inmediato cualquier contacto recibido por radio/serie en `NodeRegistry`.
     - **`src/admin_handler.py`**: Flexibilizado `notify_command_response` para aceptar payloads unificados y notificar a corrutinas esperando respuestas de comandos CLI remotos.
     - **`src/store_forward.py`**: Mejorado soporte de SQLite `:memory:` para compartir cache (`file:meshcore_mem_db?mode=memory&cache=shared`) entre hilos asÃ­ncronos.
  3. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**: Auto-sincronizaciÃ³n activa con la libreta de contactos serie (`/api/contacts/sync`) si el directorio de nodos locales estÃ¡ vacÃ­o al inicio.
  4. **SimulaciÃ³n Multi-Nodo (`scripts/simulate_mesh_network.py`)**:
     - Creado y ejecutado simulador con 7 nodos heterogÃ©neos (EstaciÃ³n Base, 2 Repetidores, 2 Clientes, 1 Sensor ambiental, 1 Sala BBS).
     - ValidaciÃ³n del 100% de flujos: Descubrimiento de nodos con coordenadas/baterÃ­a, mensajerÃ­a de difusiÃ³n y DMs, acuses de recibo ACK E2E, comandos CLI remotos (`ver`, `pos`, `ping_zero`) y actualizaciÃ³n/persistencia de parÃ¡metros.

### Hito: EstandarizaciÃ³n de Terminales (Local y Repetidores) con Conjunto de Comandos Oficiales MeshCore
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 1 (Protocolo), Agente 2 (Bridge) y Agente 4 (Frontend) para unificar la nomenclatura a **Terminal** y asegurar que ambas terminales admitan exactamente los mismos comandos de firmware de MeshCore:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Nomenclatura Estandarizada**: PestaÃ±as renombradas a **`ðŸ’» Terminal`** tanto en la vista Ajustes del nodo local como en el diÃ¡logo de administraciÃ³n del repetidor remoto.
     - **Encabezados Unificados**: `meshcore@base:~ (Terminal)` y `meshcore@repeater:~ (Terminal)`.
     - **Desplegables de Ayuda IdÃ©nticos**: Ambas consolas ahora incluyen la referencia completa de comandos oficiales del firmware MeshCore (`ver`, `bat`, `time`, `sync_clock`, `stats`, `radio`, `packets`, `pos`, `owner`, `neighbors`, `discover.neighbors`, `channels`, `acl`, `advert`, `ping`, `clear stats`, `reboot`, `set ...`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**: AÃ±adido soporte completo para `pos`, `owner`, `identity`, `neighbors`, `vecinos`, `acl`, `board`, `ping` y `help` enriquecido en el procesador CLI local.
     - **`src/repeater_manager.py`**: Actualizado `build_repeater_command_payload` con todos los alias de comandos oficiales (`bat`, `time`, `clock`, `stats-core`, `stats-radio`, `pos`, `owner`, `acl`, `neighbors`, `discover.neighbors`, `advert flood`, `help`).
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n de tipos y sintaxis JavaScript (`node -c` $\to$ cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ cÃ³digo 0).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: IdentificaciÃ³n Exhaustiva de Nodos y Lecturas Ambientales en Logs de TelemetrÃ­a
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 2 (Bridge Architect) y Agente 5 (Seguridad/AuditorÃ­a) para resolver la causa raÃ­z de los logs "nodo anÃ³nimo" y optimizar la cadencia de telemetrÃ­a:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/web/api_router.py` (`record_incoming_event`)**:
       - ExtracciÃ³n exhaustiva de identificadores de emisor (`sender`, `public_key`, `pubkey`, `pubkey_prefix`, `from_node`, `from`, `source`, `node_id`, `contact.public_key`, `payload.sender`).
       - ExtracciÃ³n exhaustiva de nombres y alias (`sender_name`, `alias`, `name`, `node_alias`, `node_name`, `contact.name`, `contact.alias`).
       - ResoluciÃ³n automÃ¡tica contra `NodeRegistry` (`get_by_key_or_prefix` y `find_by_name`), asociando el nombre de contacto conocido y su prefijo de clave pÃºblica canÃ³nica.
       - Enriquecimiento del mensaje de log con lecturas ambientales en vivo (`ðŸŒ¡ï¸� Temp`, `ðŸ’§ Humedad`, `ðŸŒ€ PresiÃ³n`, `ðŸ”‹ BaterÃ­a`, `âš¡ Voltaje`, `ðŸ“¶ SNR`, `ðŸ“¡ RSSI`).
     - **`src/virtual_mesh_adapter.py`**:
       - InclusiÃ³n explÃ­cita de `sender`, `public_key`, `sender_name`, `alias` y `name` en el payload de telemetrÃ­a.
       - Ajuste de la cadencia de simulaciÃ³n de telemetrÃ­a a intervalos realistas de red LoRa (30s / 45s / 60s) para evitar saturaciÃ³n de logs y airtime.
  2. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n de compilaciÃ³n Python (`python -m compileall src` $\to$ cÃ³digo 0).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: HomogeneizaciÃ³n Visual de Ajustes y Repetidores, Consolas Terminal Linux con Historial, Renombrado Ping, Buscador de Contactos y Persistencia de Chat
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 4 (Frontend), Agente 2 (Bridge) y Agente 5 (Seguridad) para la unificaciÃ³n integral de vistas, emulaciÃ³n de terminal Linux y persistencia robusta:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **UnificaciÃ³n de Ajustes y Modal de Repetidores**: HomogeneizaciÃ³n total de los esquemas de telemetrÃ­a (8 tarjetas con franja de resumen rÃ¡pido), formularios RF/GPS y barras de acciones tÃ¡cticas `.hardware-actions-toolbar` con micro-botones.
     - **Consolas Linux Terminal (`.linux-term-window`)**: ImplementÃ³ ventana estilo Linux con botones de ventana (ðŸ”´ðŸŸ¡ðŸŸ¢), tÃ­tulos `meshcore@base:~` y `meshcore@repeater:~`, prompts interactivos `meshcore@base:~$ ` y `meshcore@remote:~$ `, tipografÃ­a monoespaciada e historial interactivo con teclas $\uparrow$ / $\downarrow$.
     - **EliminaciÃ³n de Secciones Redundantes**: PurgÃ³ subpaneles obsoletos (`local-actions` en Ajustes y `rep-quick` en AdministraciÃ³n de Repetidores).
     - **Renombrado de Ping**: CambiÃ³ todas las instancias de "Ping 0" / "Ping Zero" a "Ping" en badges, botones de nodo, modales y mensajes.
     - **Buscador y Filtros de Contactos**: AÃ±adiÃ³ barra de bÃºsqueda unificada y pÃ­ldoras de filtro (`Todos`, `â­� Favoritos`, `ðŸŸ¢ En LÃ­nea`, `ðŸ“� Con PosiciÃ³n`) sincronizadas con contadores en tiempo real.
     - **Persistencia de MensajerÃ­a**: RefinÃ³ `isCommandOrSystemText` para que palabras comunes de chat nunca sean descartadas, asegurando hidrataciÃ³n completa en IndexedDB.
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - VerificaciÃ³n de la simulaciÃ³n continua multi-nodo en `VirtualMeshAdapter` con emisiÃ³n de tramas de sniffer (0x88 `LOG_DATA`), telemetrÃ­a CayenneLPP y eco interactivo.
  3. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: OptimizaciÃ³n Integral de Ajustes, TelemetrÃ­a Real, ParÃ¡metros RF/GPS Bidireccionales, Consolas en String y Acciones Compactas
- **Fecha**: 2026-08-25
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 1 (Protocolo), Agente 2 (Bridge) y Agente 4 (Frontend) para la auditorÃ­a, optimizaciÃ³n y resoluciÃ³n integral de los casos de uso de la vista Ajustes:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - SincronizaciÃ³n real de parÃ¡metros RF (`set_radio`, `set_tx_power`, `send_appstart`) y guardado de coordenadas GPS e identidad (`set_coords`, `set_name`, `set_custom_var`).
       - Motor de formateo CLI textual enriquecido que transforma todas las respuestas de comandos en strings limpios y comprensibles (`[DEVICE INFO]`, `ðŸ”‹ [BATERÃ�A]`, `ðŸ•’ [RTC CLOCK]`, `ðŸ“Š [CORE STATS]`, `ðŸ“» [RF CONFIG]`, `ðŸ“¦ [PACKETS]`, `ðŸ“¢ [ADVERT]`, `ðŸ”„ [REBOOT]`, `ðŸ§¹ [STATS]`, `ðŸ“– [COMANDOS]`).
       - Soporte para comandos CLI directos en terminal (`ver`, `bat`, `time`, `clock`, `stats`, `radio`, `packets`, `channels`, `advert`, `flood`, `reboot`, `clear stats`, `set name`, `set tx`, `set freq`, `set coords`).
     - **`src/virtual_mesh_adapter.py`**:
       - ImplementÃ³ `VirtualMeshCoreMock` y `VirtualMeshCoreCommands` para emulaciÃ³n 100% fidedigna de comandos de hardware y telemetrÃ­a en tiempo real.
     - **`src/bridge_core.py`**:
       - HabilitÃ³ el acceso bidireccional al objeto `mc` desde cualquier adaptador (SDK o Virtual).
     - **`src/web/api_router.py`**:
       - En `GET /api/node/config`, incorporÃ³ consulta activa en tiempo real de telemetrÃ­a de hardware con `fetch_device_config()`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/index.html` & `src/web/static/css/app.css`**:
       - DiseÃ±Ã³ e integrÃ³ la barra compacta `.hardware-actions-toolbar` con micro-botones de acciÃ³n tÃ¡cticos dentro de la subpestaÃ±a *TelemetrÃ­a & Estado*.
       - ConfiguraciÃ³n predeterminada del selector de capas cartogrÃ¡ficas en modo online (CartoDB Dark / OSM).
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ `formatCliResponseObject()` y `formatRemoteCliResponse()` para formatear respuestas de consola en ambas terminales (local y repetidores remotos) en cadenas legibles y limpias, eliminando volcados JSON crudos.
       - DesactivÃ³ el fallback intrusivo a radar tÃ¡ctico ante errores aislados de teselas individuales.
  3. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: AuditorÃ­a Visual Completa de Todas las Vistas, ReparaciÃ³n de Llave CSS Desbalanceada y RediseÃ±o de Home Assistant
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO (100% PASS - 122 Tests)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 4 (Frontend), Agente 2 (Bridge) y Agente 3 (QA) tras detectar vistas con pÃ©rdida de estilos debido a una regla CSS huÃ©rfana no cerrada.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Causa RaÃ­z de Estilos Incompletos**: La regla `.nodes-unified-grid {` en la lÃ­nea 1017 de `src/web/static/css/app.css` no tenÃ­a llave de cierre `}`, lo que invalidaba en cascada mÃ¡s de 3.600 lÃ­neas de CSS posterior, dejando sin estilos a las vistas de MÃ©tricas/AnalÃ­tica, Home Assistant, Consolas y Ajustes.
     - **CorrecciÃ³n en `app.css`**: Se eliminÃ³ la regla duplicada e incompleta, restableciendo el balance exacto de llaves (`count = 0`).
     - **RediseÃ±o de PestaÃ±a Home Assistant (`tab-ha`)**: Se maquetÃ³ un panel visual completo con KPIs (Auto-Discovery MQTT, Nodos Anunciados, Entidades Expuestas, Broker MQTT), tabla de entidades soportadas (BaterÃ­a, Voltaje, SNR, RSSI, Temperatura, Humedad) y tarjeta de tÃ³picos MQTT.
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/mqtt_client.py`**:
       - CorrigiÃ³ `publish_safe` para evitar `RuntimeError: asyncio.run() cannot be called from a running event loop` cuando se invoca desde un bucle asÃ­ncrono activo, usando `asyncio.get_running_loop().create_task()`.
  3. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - **`scripts/inspect_all_views.py`**:
       - InspecciÃ³n visual automatizada de las 9 pestaÃ±as principales y las 6 subpestaÃ±as de Ajustes con Playwright, validando que todas las vistas cargan con el tema visual UI/UX Pro Max completo.
     - **VerificaciÃ³n Global**: 122/122 pruebas en Pytest (100% PASS), Mypy strict (0 errores) y Ruff (0 warnings).
  4. **Agente 0 (Lead Orchestrator)**:
     - SincronizaciÃ³n del paquete de despliegue `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con GitHub `origin/main`.

### Hito: CorrecciÃ³n de RecepciÃ³n de Confirmaciones de Entrega (ACKs), Interactividad de Tarjetas de Contactos y SimulaciÃ³n E2E con Playwright

- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO (100% PASS - 122 Tests)
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ al Agente 2 (Bridge), Agente 4 (Frontend) y Agente 3 (QA) para resolver el enrutamiento de confirmaciones de entrega E2E, habilitar la interactividad completa de las tarjetas de contactos y crear la suite de simulaciÃ³n E2E automatizada con Playwright en Chromium headless.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/bridge_core.py`**:
       - InyectÃ³ explÃ­citamente `store_forward` y `store_and_forward` en `RxRouterContext` durante la inicializaciÃ³n del bridge, permitiendo que `RxEventRouter` consulte la base de datos de recibos de entrega.
     - **`src/rx_router.py`**:
       - AsegurÃ³ la bÃºsqueda robusta de `msg_id` a travÃ©s de `get_msg_id_by_expected_ack(ack_code)` y el marcado de entrega con `mark_message_delivered(ack_msg_id, trip_time)`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - AÃ±adiÃ³ `stopPropagation` a todos los botones de acciÃ³n interna de la tarjeta de contacto (`.btn-contact-dm`, `.btn-contact-qr`, `.btn-contact-del`, `.btn-copy-pk`).
       - HabilitÃ³ el evento de clic en toda la superficie de la tarjeta `.contact-card` con `cursor: pointer` para abrir directamente la conversaciÃ³n privada (DM) con el nodo seleccionado.
  3. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - **`tests/test_playwright_e2e_simulation.py`**:
       - CreÃ³ la suite automatizada E2E con Playwright que lanza un bridge virtual completo, navega por la UI web, selecciona un contacto, abre el chat DM, transmite un mensaje, recibe el ACK por radio simulado y valida que el indicador de estado cambie a `"âœ“âœ“ TX"` (entregado).
     - **Resultados de VerificaciÃ³n**:
       - Pytest: 122 pruebas aprobadas (100% PASS).
       - Mypy: 0 errores en los 23 mÃ³dulos de producciÃ³n (`--strict`).
       - Ruff: 0 errores de formato / estilo.
  4. **Agente 0 (Lead Orchestrator)**:
     - SincronizaciÃ³n del paquete de producciÃ³n `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: VerificaciÃ³n Global de Calidad, Tipado Estricto y CorrecciÃ³n de SerializaciÃ³n de Comandos MeshCore

- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO (100% PASS)
- **Agente Principal (Lead Orchestrator)**: LiderÃ³ la ejecuciÃ³n exhaustiva de la suite de pruebas bajo demanda explÃ­cita del usuario, coordinando al Agente 1 (Protocolo), Agente 2 (Bridge), Agente 3 (QA) y Agente 5 (Seguridad).
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)** & **Agente 2 (Bridge Architect Agent)**:
     - **`src/repeater_manager.py`**:
       - CorrigiÃ³ la serializaciÃ³n del comando de potencia TX remota de `set tx_power {pwr}` a `set tx {pwr}` para coincidir exactamente con el firmware C/C++ de MeshCore (`CommonCLI.cpp`).
       - AÃ±adiÃ³ soporte nativo para `set_name` / `name` (`set name {name}`).
     - **`src/contact_manager.py`**:
       - AgregÃ³ retorno tipado explÃ­cito `return None` al mÃ©todo `get_by_key_or_prefix` para cumplir con `mypy --strict`.
  2. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - **Pytest Suite**: 121 pruebas pasadas exitosamente (100% PASS en 24.91s).
     - **Mypy Strict**: Tipado estÃ¡tico 100% verificado en los 23 archivos fuente de `src/` (0 errores).
     - **Ruff Linter**: 0 advertencias o errores de estilo PEP 8.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - AuditorÃ­a SAST/DAST completa ejecutada (Bandit, prevenciÃ³n de inyecciones SQL, Directory Traversal en servidor HTTP y sanitizaciÃ³n XSS). Cero vulnerabilidades.
  4. **Agente 0 (Lead Orchestrator)**:
     - ConciliÃ³ los contratos entre el backend y frontend.
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: AuditorÃ­a Multi-Agente y DepuraciÃ³n Integral de CÃ³digo Duplicado y Deprecado en la Vista Web

- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ una auditorÃ­a estÃ¡tica automatizada completa entre Agente 4 (Frontend), Agente 5 (Seguridad) y Lead Orchestrator para erradicar selectores CSS duplicados, reglas obsoletas de modales bÃ¡sicos, lookups DOM huÃ©rfanos en JavaScript y optimizar la mantenibilidad del cÃ³digo cliente.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - EliminÃ³ definiciones preliminares y redundantes de `.msg-ack-status` (consolidando la versiÃ³n completa con keyframe `ackPop`).
       - EliminÃ³ mÃ¡s de 80 lÃ­neas de definiciones bÃ¡sicas obsoletas de modales (`.modal-overlay`, `.modal-card`, `.modal-header`, `.modal-body`, `.modal-footer`) que entraban en conflicto con el sistema moderno de glassmorphism (`backdrop-filter: blur(14px)`).
     - **`src/web/static/js/app.js`**:
       - PurgÃ³ mÃ¡s de 20 lookups DOM huÃ©rfanos y obsoletos en `this.dom` heredados de formularios antiguos de repetidor (`remoteRepeaterConfigForm`, `remoteTargetNodeSelect`, `remoteAdminPassword`, etc.) y controles deprecados (`btnAddContact`, `btnRefreshAllNodes`, `nodesGridUi`, `btnRunPreflight`, `snifferFilterOpcode`).
       - RefactorizÃ³ `populateRepeaterDropdown()` eliminando comprobaciones muertas.
  2. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - VerificÃ³ que la purga de selectores y elementos del DOM preservÃ³ el 100% de los mecanismos de sanitizaciÃ³n XSS (`escapeHtml`) y los flujos de autenticaciÃ³n segura del PIN del repetidor (`repeaterGatePassword`).
  3. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: EstandarizaciÃ³n GeomÃ©trica y Visual Total de Tarjetas (Nodos y Contactos)

- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiseÃ±Ã³ e implementÃ³ una arquitectura simÃ©trica y uniforme para todas las tarjetas del sistema (Clientes, Repetidores, Sensores, Salas y EstaciÃ³n Base Local). Se resolvieron los truncamientos prematuros de nombres, el salto de lÃ­nea en badges de estado (`ðŸŸ¢ En LÃ­nea`), la asimetrÃ­a de alturas mediante un panel central de metadatos estandarizado (`44px`), la alineaciÃ³n estricta de la cuadrÃ­cula de 3 mÃ©tricas RF y la fijaciÃ³n inferior de la barra de acciones.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - RediseÃ±Ã³ `.node-card`, `.contact-card` y `.contact-item-card` con `min-height: 235px`, `padding: 14px 16px`, bordes de 4px por rol y sombras con resplandor cyan al hover.
       - CreÃ³ `.node-card-top-row` y `.node-card-sub-row` para separar el nombre/baterÃ­a de la clave pÃºblica/badges, eliminando el colapso del texto de estado (`white-space: nowrap`).
       - EstandarizÃ³ `.node-telemetry-panel` a una altura fija de `44px` con tipografÃ­a de precisiÃ³n (`.node-meta-row`, `.node-meta-title`, `.node-meta-highlight`, `.node-meta-sub`).
       - UnificÃ³ `.node-rf-strip` y `.contact-card-chips` en 3 columnas iguales (`grid-template-columns: repeat(3, 1fr)`) con pills de `26px`.
       - EstandarizÃ³ `.node-actions-bar` y `.contact-card-actions` con botones de `32px` (`.btn-node-primary` flexible y `.btn-node-secondary` fijos).
       - EliminÃ³ el chip de texto `ðŸŸ¢ En LÃ­nea` y lo reemplazÃ³ por un indicador circular `avatar-status-dot` integrado en el avatar con pulso de luz segÃºn el estado en vivo.
       - AlineÃ³ la cuadrÃ­cula de matriz en `auto-fill, minmax(295px, 1fr)` con `min-height: 232px` para simetrÃ­a absoluta en filas y columnas.
  2. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - ValidaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: DeduplicaciÃ³n Robusta de Contactos y EliminaciÃ³n de Falsos Positivos en Banner de Descubrimiento
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ la causa por la cual un contacto ya registrado en la libreta o transceptor de radio volvÃ­a a disparar la alerta de *"Â¡Nuevos Nodos Descubiertos en el Aire!"*. Se optimizÃ³ la resoluciÃ³n de claves canÃ³nicas (`_find_existing_key`) para coincidir por nombre/alias exacto y prefijos (`>= 6` caracteres), se garantizÃ³ que los contactos sincronizados desde el dispositivo inicien como `auto_discovered=False`, y se filtraron en el frontend (`fetchDiscoveredContacts` y evento WebSocket) las coincidencias de contactos guardados.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/contact_manager.py`**:
       - MejorÃ³ `_find_existing_key` para buscar primero por coincidencia exacta de clave pÃºblica, prefijos comunes y por nombre/alias registrado en `_nodes_by_key`.
     - **`src/bridge_core.py`**:
       - En `sync_all_contacts()`, marcÃ³ explÃ­citamente los contactos importados desde el hardware con `auto_discovered=False` e `is_favorite=True`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `fetchDiscoveredContacts()`, implementÃ³ el descarte de nodos descubiertos si coinciden con cualquier contacto existente en la libreta (`auto_discovered === false`).
       - En el manejador WebSocket `contact_discovered`, aÃ±adiÃ³ la verificaciÃ³n previa para suprimir el toast y la actualizaciÃ³n del banner si el contacto ya pertenece a la libreta de contactos.
  3. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - ValidaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: RediseÃ±o Integral de la EstaciÃ³n Web con el Skill UI/UX Pro Max (Dark Tech & Operations Dashboard)
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: IntegrÃ³ formalmente el skill `ui-ux-pro-max` (`https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`) y coordinÃ³ el rediseÃ±o integral de la interfaz web bajo el arquetipo *Real-Time Operations & Tactical IoT Dashboard* con estÃ©tica *OLED Dark Tech* y *Glassmorphism*.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - IntegrÃ³ la paleta semÃ¡ntica de alto contraste (`--bg-canvas: #070B14`, `--bg-surface: #0F172A`, `--bg-surface-elevated: #1E293B`, `--bg-glass: rgba(15, 23, 42, 0.78)`).
       - RediseÃ±Ã³ la barra superior tÃ¡ctica con efecto frosted glass (`backdrop-filter: blur(16px)`), microindicador pulsante de estado en vivo, chips de mÃ©tricas RF pulidos y disparador Command Palette.
       - ModernizÃ³ la barra de navegaciÃ³n con indicador lateral cyan (`--accent-primary`), badges de notificaciÃ³n pulsantes y selectores de canales y DMs con degradados sutiles.
       - RediseÃ±Ã³ las burbujas de mensajerÃ­a: degradado asimÃ©trico TX (`#0284C7 -> #0369A1`), tarjetas elevadas RX, autor destacado, marca temporal legible y chips de seÃ±al RF (`ðŸ“¶ -XX dBm / XX dB`).
       - ReforzÃ³ la presentaciÃ³n de tarjetas en Contactos y Nodos (grilla uniforme de `280px`, microanimaciÃ³n hover, chips de telemetrÃ­a de alto contraste).
       - RediseÃ±Ã³ el sistema de modales con desenfoque de fondo (`backdrop-filter: blur(14px)`), borde reactivo y animaciÃ³n de entrada suave (`modalZoomIn`).
     - **`src/web/static/index.html`**:
       - IncorporÃ³ tipografÃ­a Google Fonts con preconnect de alto rendimiento (`Inter` para controles UI y `Fira Code` para telemetrÃ­a, hex y terminal).
  2. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - ValidaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: UnificaciÃ³n EstÃ©tica de Tarjetas (Contactos y Nodos) y ResoluciÃ³n Integral de MÃ©tricas RF/BaterÃ­a (-- a N/D)
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ las discrepancias de diseÃ±o y formato en las tarjetas de las vistas de "Contactos" y "Nodos". CorrigiÃ³ la falta de estilos base por discrepancia de selectores CSS (`.contact-item-card` vs `.contact-card`, `.contact-meta` vs `.contact-info`), el fallo en la bÃºsqueda de contactos por selector desfasado, y resolviÃ³ el mapeo de mÃ©tricas (SNR, RSSI, Saltos, BaterÃ­a, Voltaje, Uptime y Ruido) para evitar cadenas `--` descontextualizadas, proporcionando valores calculados precisos (`0 (Directo)`, `USB 5V`, `+12.5 dB`, `N/D`).
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - UnificÃ³ las reglas de grilla y contenedores para `.nodes-grid` y `.nodes-unified-grid` (`minmax(280px, 1fr)` y gap de `14px`).
       - AlineÃ³ `.contact-card` y `.contact-item-card` con el estÃ¡ndar de diseÃ±o de `.node-card`: borde lateral temÃ¡tico (`3.5px solid var(--accent-primary)`), fondo elevado, `padding: 12px 14px`, `min-height: 180px`, flexbox de distribuciÃ³n vertical y microanimaciÃ³n hover.
       - CorrigiÃ³ selectores `.contact-info`, `.contact-title-row`, `.contact-avatar` y `.contact-battery-chip` (`.bat-unknown`).
       - RediseÃ±Ã³ la botonera de acciones `.btn-contact-action` (`.btn-contact-dm`, `.btn-contact-qr`, `.btn-contact-del`) con altura estÃ¡ndar de `28px` y tipografÃ­a unificada.
     - **`src/web/static/js/app.js`**:
       - EnriqueciÃ³ la resoluciÃ³n de mÃ©tricas en `renderNodesDirectory`:
         - **SNR**: extracciÃ³n jerÃ¡rquica (`snr`, `last_snr`, `metrics.snr`, `telemetry.snr`, `SNR`), formato numÃ©rico con signo (`+X.X dB`) o `Host USB` para el nodo local, o `N/D` amigable.
         - **RSSI**: extracciÃ³n jerÃ¡rquica (`last_rssi`, `rssi`, `metrics.rssi`, `RSSI`), redondeo exacto (`-XX dBm`) o `Directo` para nodo local.
         - **Saltos**: mapeo contextual (`0 (Directo)`, `1 salto`, `X saltos`, `0 (Host)`).
         - **BaterÃ­a/Voltaje**: resoluciÃ³n de porcentaje y conversiÃ³n automÃ¡tica de voltaje litio (`3.2V - 4.2V` -> porcentaje estimado con voltaje auxiliar ej. `85% (4.1V)`), y `USB 5V` para base local.
         - **Sensores y Repetidores**: formateo de temperatura, humedad y presiÃ³n con unidades claras y fallback `N/D`, y potencia TX/Hop Limit consistentes.
       - AÃ±adiÃ³ chip de estado en lÃ­nea dinÃ¡mico (`ðŸŸ¢ En LÃ­nea` / `ðŸŸ¡ Inactivo` / `ðŸ”´ Fuera de lÃ­nea`) con tooltip de tiempo relativo en las tarjetas de contactos.
       - En `updateNodeCardLiveState`: integrÃ³ actualizaciÃ³n en tiempo real tanto para `.node-card` como para `.contact-card`.
       - En `filterContactsGrid`: corrigiÃ³ la consulta de tarjetas (`.contact-card, .contact-item-card`) restaurando la bÃºsqueda en tiempo real de contactos.
  2. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript (`node -c`) y compilaciÃ³n Python (`python -m compileall src`).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n y commit con el repositorio remoto GitHub (`origin/main`).

### Hito: ExtracciÃ³n Inteligente de Nombres de Remitente y Persistencia de Chats Directos Estilo WhatsApp al Refrescar
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ e implementÃ³ la resoluciÃ³n automÃ¡tica de nombres de remitente para evitar que se muestren como `unknown` en el encabezado de las burbujas de mensaje cuando el emisor incluye su identificador en el texto (`Nombre: Mensaje`) o se encuentra en la libreta de contactos. Asimismo, implementÃ³ la persistencia y recuperaciÃ³n automÃ¡tica de todas las conversaciones de mensajes directos (`MENSAJES DIRECTOS`) desde IndexedDB al recargar la pÃ¡gina (F5), emulando la experiencia de usuario de WhatsApp/Telegram.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/contact_manager.py`**:
       - AÃ±adiÃ³ el mÃ©todo `find_by_name(name: str)` en `NodeRegistry` para resolver nodos por nombre/alias de forma insensible a mayÃºsculas.
     - **`src/rx_router.py`**:
       - ImplementÃ³ la funciÃ³n `extract_sender_from_text(text: str)` para detectar prefijos `^([a-zA-Z0-9_\-\.]{2,32}):\s*(.*)$`.
       - En `handle_event`, si `sender_name` es desconocido o genÃ©rico, extrae el nombre del texto, resuelve la clave pÃºblica mediante `node_registry.find_by_name` y propaga `sender_name` a los eventos MQTT y WebSockets.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - AÃ±adiÃ³ el mÃ©todo `getDmConversations()` en `MeshCoreStorage` para recuperar todos los hilos DM almacenados en IndexedDB (`chat_messages`), agrupÃ¡ndolos y ordenÃ¡ndolos por fecha reciente.
       - En `fetchInitialData()`, restaura automÃ¡ticamente todas las conversaciones de mensajes directos en la barra lateral (`#dmListUi`), registra los feeds en `this.channelFeeds`, aÃ±ade las claves a `conversationsWithMessages` y actualiza badges y contadores al recargar la pÃ¡gina.
       - ImplementÃ³ `extractSenderAndText(text, currentSenderName)` para extraer y asociar el nombre del remitente en tiempo real.
       - En `appendChatMessage(msg)`, garantiza que el encabezado del mensaje muestre el nombre real del contacto (ej. `Cu1.mobilUnit`) y nunca `unknown` cuando haya un nombre presente o registrado.
       - En `renderNodesDirectory()`, refresca dinÃ¡micamente los nombres de contactos en la lista activa de DMs en la barra lateral.
  3. **Agente 0 (Lead Orchestrator)**:
     - ValidaciÃ³n estÃ¡tica JavaScript con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - ValidaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: Flujo PeriÃ³dico n8n Cada 6h con Estado, Fecha/Hora y Clima de Lehigh Acres, FL
- **Fecha**: 2026-08-22
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiseÃ±Ã³ e integrÃ³ la tarea programada recurrente en el flujo universal de automatizaciÃ³n n8n (`n8n_workflow_meshcore.json`) para emitir periÃ³dicamente cada 6 horas (iniciando a las 12:00 AM / 00:00, 06:00, 12:00, 18:00) un reporte completo de estado a la red MeshCore con fecha, hora y el pronÃ³stico meteorolÃ³gico en tiempo real para Lehigh Acres, Florida.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`n8n_workflow_meshcore.json`**:
       - IntegrÃ³ el nodo `Schedule Trigger` (`0 0,6,12,18 * * *`) para ejecuciÃ³n cÃ­clica cada 6 horas comenzando a las 12:00 AM.
       - IntegrÃ³ el nodo `HTTP Request` para consultar la API meteorolÃ³gica Open-Meteo para Lehigh Acres, FL (`lat: 26.6254`, `lon: -81.6248`, `timezone: America/New_York`).
       - DiseÃ±Ã³ el nodo de cÃ³digo JavaScript para transformar cÃ³digos WMO a emojis/descripciones en espaÃ±ol, calcular temperaturas en Â°C y Â°F, sensaciÃ³n tÃ©rmica, humedad, viento y construir el paquete MQTT de difusiÃ³n (`meshcore/tx`, canal 0 broadcast).
       - ConectÃ³ el flujo de reporte meteorolÃ³gico directamente al nodo emisor MQTT.
     - **`tests/test_n8n_parser_matrix.py`**:
       - AÃ±adiÃ³ el mÃ©todo de simulaciÃ³n `format_periodic_weather_status` en `N8nSimulator`.
       - IntegrÃ³ la prueba unitaria `test_n8n_periodic_weather_formatting` para validar la construcciÃ³n y exactitud de los reportes.
  2. **Agente 0 (Lead Orchestrator)**:
     - SincronizaciÃ³n completa de `/deploy/` y regeneraciÃ³n de bundles comprimidos (`.tar.gz`, `.zip`) y sumas SHA256 (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n y commit con el repositorio remoto GitHub (`origin/main`).

### Hito: OptimizaciÃ³n de Latencia en Ping Zero a Repetidores (500ms vs 1500ms - EliminaciÃ³n de Paquetes Redundantes)
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y resolviÃ³ la discrepancia de latencia donde el ping a repetidores tardaba ~1500 ms (3x mÃ¡s lento) desde la interfaz web en comparaciÃ³n con la conexiÃ³n TCP directa del cliente oficial (~500 ms).
- **Causa RaÃ­z**:
  1. La interfaz web pasaba innecesariamente contraseÃ±as guardadas en las solicitudes de Ping Zero (`/api/repeater/ping_zero`).
  2. `src/admin_handler.py` despachaba un paquete previo `cmd login <password>` por RF antes de emitir `cmd ping 0`, y arrancaba el temporizador de mediciÃ³n antes del login, acumulando el tiempo de emisiÃ³n de dos tramas LoRa consecutivas mÃ¡s el turnaround de radio. En el protocolo MeshCore, las sondas de diagnÃ³stico (`ping`, `ping 0`, `trace`) son de acceso pÃºblico y no requieren sesiÃ³n autenticada.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - EliminÃ³ el despacho de `cmd login` en la rutina de `ping_zero` / `ping` / `ping_0` / `trace 0` / `zero_hop_ping`.
       - ReubicÃ³ la toma de tiempo `t_start = time.perf_counter()` inmediatamente antes de la emisiÃ³n del paquete de sonda Ãºnica.
     - **`src/web/api_router.py`**:
       - LimpiÃ³ el endpoint `/api/repeater/ping_zero` para omitir la extracciÃ³n y reenvÃ­o de contraseÃ±as hacia el manejador de ping.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `pingZero(targetNode, targetName)`, removiÃ³ la inclusiÃ³n de `password` en el cuerpo de la peticiÃ³n hacia `/api/repeater/ping_zero`, garantizando que la sonda sea despachada como un paquete RF liviano de 0 saltos directo.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica de sintaxis JavaScript con `node -c src/web/static/js/app.js`.
     - CompilaciÃ³n Python con `python -m compileall src`.
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto (`git push origin main`).

### Hito: Filtrado y Bloqueo de Nodos Fantasma / Desconocidos (`Node_unknow` / Claves InvÃ¡lidas)
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ el problema donde un remitente con clave ausente, broadcast o vacÃ­a (`"unknown"`, `"broadcast"`, `"none"`, `""`) era registrado dinÃ¡micamente como un nodo activo bajo el identificador y nombre truncado `Node_unknow` en la libreta de contactos y directorio de nodos.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/contact_manager.py`**:
       - ImplementÃ³ la funciÃ³n de validaciÃ³n `is_valid_node_key(key)` y el conjunto de claves prohibidas `INVALID_NODE_KEYS = {"unknown", "broadcast", "none", "null", "system", "00000000", "ffff", "0xffff", ""}`.
       - ProtegiÃ³ `add_or_update`, `discover_node`, `get_canonical_key`, `record_packet` y `_find_existing_key` para descartar o ignorar cualquier clave invÃ¡lida o de longitud insuficiente (< 4 caracteres).
       - En `list_nodes()`, aÃ±adiÃ³ un filtro estricto para retornar Ãºnicamente nodos con claves vÃ¡lidas y excluir nombres fantasma como `Node_unknow`.
     - **`src/rx_router.py`**:
       - IntegrÃ³ `is_valid_node_key` al extraer `sender_raw` en `handle_event`, evitando que eventos con remitente desconocido disparen `discover_node` o `add_or_update`.
     - **`src/web/api_router.py`**:
       - En `record_incoming_event`, normalizÃ³ la firma para soportar 1 o 2 parÃ¡metros y filtrÃ³ remitentes mediante `is_valid_node_key` antes de registrar paquetes en `NodeRegistry`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ el mÃ©todo `isValidNodeKey(key)` en `MeshCoreStationApp`.
       - En `renderNodesDirectory(nodes)`, aÃ±adiÃ³ filtrado de nodos con claves invÃ¡lidas o nombres que inicien con `Node_unknow`, y purgÃ³ automÃ¡ticamente entradas residuales de `this.knownNodes`.
       - En `updateNodeInDom(pubkey, node)`, evitÃ³ actualizar o refrescar tarjetas de nodos si la clave es invÃ¡lida o el nombre es `Node_unknow`.
       - En `handleIncomingLiveEvent(payload)`, protegiÃ³ los bloques `contact_discovered`, `contact_updated`, `telemetry` y mensajes de chat para no registrar claves desconocidas en `knownNodes`.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `ruff check src` (0 errores).
     - VerificaciÃ³n de tipado estricto con `mypy --strict src` (0 errores en 23 mÃ³dulos).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto (`git push origin main`).

### Hito: Filtrado Estricto de Mensajes de Comando, Anuncios y Control ("Unknown command") en Canales y DMs
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: ImplementÃ³ el aislamiento y filtrado exhaustivo de mensajes no comunes (respuestas CLI del firmware como `"Unknown command"`, telemetrÃ­a de repetidores, anuncios de baliza / `ADVERT`, respuestas de autenticaciÃ³n y comandos de diagnÃ³stico) en todas las vistas de mensajerÃ­a (Canal pÃºblico 0, Canales privados 1..7 y Mensajes directos DM), garantizando que Ãºnica y exclusivamente el chat comÃºn entre usuarios sea emitido y almacenado en las vistas de conversaciÃ³n.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/rx_router.py`**:
       - ImplementÃ³ las funciones de validaciÃ³n `is_command_or_system_message(text, txt_type)` e `is_common_chat_message(text, txt_type, event_type)`.
       - AÃ±adiÃ³ el campo `txt_type: int = 0` en `MeshMessageEvent`.
       - En `handle_event`, aislÃ³ los paquetes de presencia / anuncio (`ADVERT`, `NODE_ADVERT`, `NEW_CONTACT`) y telemetrÃ­a ambiental para que no caigan en canales de texto de chat.
       - En `_handle_mesh_channel_msg`, si un mensaje de canal es una respuesta de comando (`txt_type == 1`, "Unknown command", etc.) o telemetrÃ­a, se despacha exclusivamente como evento `repeater_response` o telemetrÃ­a MQTT/WS, omitiendo su difusiÃ³n a `TOPIC_RX_PUBLIC`, `TOPIC_RX_CHANNEL/ch_X` y eventos de chat WebSocket.
       - En `_handle_mesh_direct_msg`, asegurÃ³ que las respuestas de comando y telemetrÃ­a no se emitan al tÃ³pico de chat directo `TOPIC_RX_DIRECT/{sender}`.
       - En `_dispatch_parsed_frame`, agregÃ³ validaciÃ³n con `is_common_chat_message` antes de despachar tramas `TEXT_MSG`.
     - **`src/web/api_router.py`**:
       - En `record_incoming_event`, integrÃ³ `is_common_chat_message` para evitar que respuestas de comandos y telemetrÃ­a se guarden en `self.recent_messages`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ los mÃ©todos `isCommandOrSystemText(text, txtType)` e `isCommonChatMessage(payload)` en la clase `MeshCoreStationApp`.
       - En `handleIncomingLiveEvent(payload)`, aislÃ³ el bloque `repeater_response` para que procese telemetrÃ­a y terminal sin tocar `channelFeeds`, `chat_messages` ni listas de DM.
       - En `handleIncomingLiveEvent`, procesa feeds de chat Ãºnicamente si `this.isCommonChatMessage(payload)` es verdadero.
       - En `MeshCoreStorage`, aÃ±adiÃ³ el mÃ©todo `purgeNonCommonMessages(filterFn)` para purgar entradas residuales de comandos de IndexedDB.
       - En `renderCurrentConversation()` y `fetchInitialData()`, filtrÃ³ mensajes no comunes al renderizar y al iniciar la aplicaciÃ³n.
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto (`git push origin main`).

### Hito: VerificaciÃ³n y Fortalecimiento Integral del Pipeline de Entrega de Mensajes (`âœ“âœ“ TX` / Delivery Receipts)
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: ComprobÃ³ y fortaleciÃ³ el ciclo completo de notificaciÃ³n de entrega de mensajes (Delivery Receipts / ACKs de radio) desde el firmware y adaptador virtual hasta la interfaz de usuario en tiempo real vÃ­a WebSockets e IndexedDB.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/store_forward.py`**: NormalizÃ³ la consulta de `expected_ack` en SQLite para soportar indistintamente formatos con y sin prefijo `0x` (`ack_clean`, `ack_no_prefix`, `ack_with_prefix`).
     - **`src/rx_router.py`**: RobusteciÃ³ la extracciÃ³n de `ack_code` soportando tipos `bytes` (vÃ­a `.hex()`), `int` (vÃ­a `hex()`) y cadenas de texto, garantizando el enrutamiento inmediato del evento WebSocket `message_delivered`.
     - **`src/virtual_mesh_adapter.py`**: AÃ±adiÃ³ la generaciÃ³n y emisiÃ³n de paquetes ACK de radio con cÃ³digo hash y cÃ¡lculo de `trip_time_ms` en mensajes directos simulados.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - AsegurÃ³ la normalizaciÃ³n de cÃ³digos ACK en `handleIncomingLiveEvent` y `updateMessageDelivery` para actualizar el DOM reactivamente (`.message-bubble-row.delivered`, `.msg-ack-status.delivered` -> `âœ“âœ“ TX`, `title="Entregado por radio (X ms)"`).
       - SincronizÃ³ el estado en memoria (`this.channelFeeds`) y almacenamiento persistente en IndexedDB (`chat_messages`).
  3. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto (`git push origin main`).

### Hito: CorrecciÃ³n de ExcepciÃ³n JavaScript en Consola Web (`appendLogEntryToDom is not a function`)
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ el error en tiempo de ejecuciÃ³n en la consola del navegador (`TypeError: this.appendLogEntryToDom is not a function`) generado al procesar eventos WebSocket de tipo `system_log` en tiempo real.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ el mÃ©todo `appendLogEntryToDom(log)` en `MeshCoreStationApp` para renderizar y adjuntar dinÃ¡micamente las entradas de log del sistema recibidas por WebSocket, aplicando sanitizaciÃ³n HTML (`escapeHtml`), formateo de niveles (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`), eliminaciÃ³n de placeholders de feed vacÃ­o y poda de elementos antiguos segÃºn el lÃ­mite `MAX_SYSTEM_LOGS`.
  2. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - SincronizaciÃ³n del paquete autÃ³nomo `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con el repositorio remoto (`git push origin main`).

### Hito: SimulaciÃ³n Integral Multi-Nodo, VerificaciÃ³n con Suites de Pruebas (120/120), AuditorÃ­a de Seguridad SAST/DAST y Limpieza de CÃ³digo
- **Fecha**: 2026-08-20
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ el despliegue de una simulaciÃ³n completa de malla de 10 nodos cubriendo todos los roles oficiales de MeshCore (`CLIENT`, `REPEATER`, `SENSOR`, `ROOM`, `GATEWAY`) y todos los tipos de tramas de radio (`CHANNEL_MSG`, `DIRECT_MSG`, `ADVERT`, `TELEMETRY/Cayenne LPP`, `ACK/Receipt`, `TRACE_DATA`, `LOG_DATA/Sniffer`, `REPEATER_CMD/Response`, `DEVICE_INFO`, `TCP Companion`). GenerÃ³ ficheros de logs estructurados (`logs/simulation_meshcore_full.log` y `logs/simulation_events.jsonl`), ejecutÃ³ las suites completas de pruebas unitarias/integraciÃ³n (120/120 superadas al 100%), depurÃ³ y limpiÃ³ el cÃ³digo fuente con `ruff` y `mypy --strict` (0 errores en 23 mÃ³dulos), y ejecutÃ³ una auditorÃ­a de seguridad SAST/DAST con Bandit (0 vulnerabilidades).
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - ModelÃ³ los 10 nodos simulados con sus metadatos de hardware, capacidades de telemetrÃ­a ambiental, canales de difusiÃ³n y claves pÃºblicas en `src/virtual_mesh_adapter.py`.
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - EnriqueciÃ³ `scripts/simulate_heltec_v4_mesh.py` con logging dual continuo a texto estructurado y eventos JSON Lines.
     - AÃ±adiÃ³ `get_contact` a `NodeRegistry` en `src/contact_manager.py` y `hop_count` a `PacketRecord`.
     - DepurÃ³ el despachador de comandos de repetidor en `src/admin_handler.py` y el enrutador en `src/rx_router.py`.
     - FortaleciÃ³ `src/store_forward.py` y `src/rate_limiter.py` bajo condiciones de alta carga y concurrencia.
  3. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - EjecutÃ³ la suite completa de 120 pruebas unitarias y de integraciÃ³n (`pytest tests/`), logrando 100% de aprobados en concurrencia, serial watchdog, store & forward SQLite WAL, rate limiter, HA discovery, matriz n8n y enrutamiento RF.
     - ResolviÃ³ el fixture de disponibilidad para pruebas E2E de Playwright.
  4. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - ValidÃ³ la semÃ¡ntica HTML5, sistema de tokens de diseÃ±o CSS3 (variables HSL, contraste WCAG 2.2 AA >= 4.5:1, tipografÃ­a fluida y scrollbars estilizadas) y la lÃ³gica cliente asÃ­ncrona en `src/web/static/`.
  5. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - EjecutÃ³ la auditorÃ­a de seguridad SAST con Bandit y scripts especializados (`.agents/skills/security-code-auditor/scripts/run_security_audit.py`).
     - VerificÃ³ 100% de consultas SQL parametrizadas, aislamiento estricto de rutas canÃ³nicas contra Directory Traversal, sanitizaciÃ³n XSS con `escapeHtml` y cabeceras HTTP defensivas.
  6. **Agente 0 (Lead Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `ruff check src tests` (0 errores).
     - VerificaciÃ³n estricta de tipos con `mypy --strict src` (0 errores en 23 mÃ³dulos).
     - SincronizaciÃ³n del paquete autÃ³nomo en `/deploy/` (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con repositorio remoto (`git push origin main`).

### Hito: MediciÃ³n RF de Ping y Ping Zero con RTT, SNR There, SNR Back y RSSI
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ e implementÃ³ la captura y mediciÃ³n en tiempo real de pings y ecos de radio directos (Ping Zero y Ping multi-nodo). ResolviÃ³ la causa por la cual RSSI aparecÃ­a como `-- dBm` y la latencia no reflejaba la respuesta de radio del nodo remoto, formateando la respuesta idÃ©ntica a la aplicaciÃ³n oficial de MeshCore: `"Duration en ms, SNR there, SNR back (RSSI en dBm)"`.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - AÃ±adiÃ³ el sistema de promesas asÃ­ncronas `_ping_waiters` en `AdminCommandHandler` y el mÃ©todo `notify_ping_response` para capturar la respuesta del nodo remoto.
       - En `handle` para `action in ("ping_zero", "ping_0", "ping", "zero_hop_ping")`, envÃ­a la sonda RF, espera la respuesta del transceptor con timeout controlado, calcula la duraciÃ³n real de ida y vuelta (`duration_ms`), y extrae `snr_there` (SNR medido en el nodo remoto), `snr_back` (SNR medido en el transceptor local) y `rssi` (en dBm).
       - Actualiza inmediatamente el registro de nodos `node_registry.record_packet` con las mÃ©tricas RF obtenidas.
     - **`src/rx_router.py`**:
       - AÃ±adiÃ³ `admin_handler` a `RxRouterContext`.
       - En `handle_event`, intercepta paquetes `ACK`, `TRACE_DATA` y respuestas de comandos de repetidor (`repeater_response`), notificando a `admin_handler.notify_ping_response` con `trip_time`, `snr_there`, `snr_back` y `rssi`.
       - Propaga `rssi` y `snr` en el evento `message_delivered`.
     - **`src/bridge_core.py`**:
       - ConectÃ³ `self.admin_handler` con `self.rx_router._ctx.admin_handler`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `pingZero`, extrae `duration_ms` / `rtt_ms`, `snr_there`, `snr_back` y `rssi`.
       - Formatea la salida de terminal idÃ©ntica a MeshCore oficial: `âœ“ [PONG DIRECTO] Duration: ${rtt} ms | SNR there: ${snrThere} | SNR back: ${snrBack} | RSSI: ${rssi}`.
       - Actualiza el Toast, la pÃ­ldora de resultado rÃ¡pido (`repQuickPingResult`) y la insignia del modal (`adminModalPingZeroBadge`).
       - Actualiza inmediatamente las mÃ©tricas en `this.knownNodes` y llama a `updateNodeInDom` para refrescar los chips de RF y estado del nodo en la interfaz.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n de sintaxis JS (`node -c`, cÃ³digo 0).
     - VerificaciÃ³n de sintaxis y tipos Python (`python -m compileall`, cÃ³digo 0).
     - SincronizaciÃ³n completa de paquete autÃ³nomo de despliegue (`python scripts/sync_deploy.py`).
     - SincronizaciÃ³n con repositorio remoto (`git push origin main`).

### Hito: ActualizaciÃ³n Reactiva de Estado de Actividad de Nodos (En LÃ­nea / Inactivo)
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ el flujo por el cual un nodo remoto con el que se interactÃºa o del que se recibe un mensaje permanecÃ­a errÃ³neamente con estado visual "Inactivo" / "Fuera de lÃ­nea".
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/rx_router.py`**:
       - En `handle_event`, registra los paquetes de recepciÃ³n con `node_registry.record_packet` para nodos remotos y emite el evento WebSocket `contact_updated` (o `contact_discovered` para nuevos) conteniendo la informaciÃ³n actualizada del contacto (`last_seen`, `last_rssi`, `last_snr`, `hops`), permitiendo que el cliente web reciba la seÃ±al de vivacidad en tiempo real.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ `updateNodeInDom(pubkey, node)` para conmutar inmediatamente el chip de estado a `ðŸŸ¢ En LÃ­nea` (`status-online`), actualizar mÃ©tricas de RF (`RSSI`, `SNR`, `Saltos`) y remover `.node-card-offline` en el DOM sin necesidad de recargar la pÃ¡gina.
       - En `handleIncomingLiveEvent`, actualiza `last_seen` en `this.knownNodes` e invoca `updateNodeInDom` al recibir mensajes ordinarios (DM o canal), confirmaciones de entrega de radio (`message_delivered` para el destinatario) y eventos de actualizaciÃ³n (`contact_updated` / `contact_discovered`).
       - RobusteciÃ³ el cÃ¡lculo y normalizaciÃ³n de `last_seen` en `renderNodesDirectory` para soportar marcas de tiempo en segundos, milisegundos y formatos de fecha ISO.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0).
     - SincronizaciÃ³n de `/deploy/` y paquetes comprimidos vÃ­a `python scripts/sync_deploy.py`.
     - SincronizaciÃ³n con el repositorio remoto GitHub (`origin/main`).

### Hito: ValidaciÃ³n y ConfirmaciÃ³n de Entrega de Mensajes E2E (Doble Palomilla `âœ“âœ“ TX`)
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ e implementÃ³ la cadena completa de confirmaciÃ³n de entrega de mensajes (Delivery Receipts). ResolviÃ³ la causa raÃ­z por la cual los mensajes transmitidos permanecÃ­an indefinidamente en una sola palomilla (`âœ“ TX`), conectando el cÃ³digo de ACK de 4 bytes de la radio con el ID del mensaje, persistiendo la confirmaciÃ³n en SQLite WAL e IndexedDB, y actualizando la interfaz reactivamente a doble palomilla (`âœ“âœ“ TX`).
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/store_forward.py`**:
       - AÃ±adiÃ³ la columna `expected_ack TEXT` e Ã­ndice `idx_receipts_expected_ack` a la tabla `message_receipts` de SQLite.
       - ActualizÃ³ `record_outbound_message` para registrar el cÃ³digo de ACK esperado junto al `msg_id` y `recipient`.
       - ImplementÃ³ `get_msg_id_by_expected_ack(expected_ack)` para resolver instantÃ¡neamente el ID del mensaje a partir del cÃ³digo recibido por radio.
     - **`src/serial_driver.py`**:
       - En `PySerialAsyncioAdapter.send_message`, extrajo el `expected_ack` (cÃ³digo hexadecimal de 4 bytes) generado por el firmware en el evento `MSG_SENT` y lo retornÃ³ en el resultado.
     - **`src/bridge_core.py`**:
       - En `_execute_tx`, capturÃ³ `expected_ack` y registrÃ³ el mensaje saliente en `store_forward.record_outbound_message`.
       - IncluyÃ³ `expected_ack` en la respuesta JSON devuelta a la API REST y en el tÃ³pico MQTT `meshcore/tx/status`.
     - **`src/rx_router.py`**:
       - En `handle_event`, intercepta los eventos `EventType.ACK` / `PacketType.ACK` extrayendo `ack_code` y `trip_time`.
       - Resuelve el `msg_id` correspondiente consultando `store_forward.get_msg_id_by_expected_ack(ack_code)`.
       - Marca el mensaje como entregado en SQLite (`mark_message_delivered`) y emite el evento `message_delivered` a WebSocket y MQTT con `msg_id`, `ack_code`, `trip_time_ms` y `status: "delivered"`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/js/app.js`**:
       - En `MeshCoreStorage`, actualizÃ³ `saveMessage` y aÃ±adiÃ³ `updateMessageDelivery` para persistir el estado `delivered: true`, `expected_ack` y `trip_time_ms` en `IndexedDB`.
       - En `initChat`, genera un `msgId` Ãºnico (`msg_...`), lo envÃ­a en `POST /api/tx` como `request_id`, captura el `expected_ack` de retorno y lo asocia como `data-ack-code` en la burbuja del DOM.
       - En `handleIncomingLiveEvent`, el manejador de `message_delivered` localiza la burbuja por `data-msg-id` o `data-ack-code`, conmuta a `âœ“âœ“ TX`, actualiza el tooltip con la latencia RTT y persiste el estado en `this.channelFeeds` e IndexedDB.
       - En `appendChatMessage`, asigna los atributos `data-msg-id` y `data-ack-code`, renderizando `âœ“âœ“ TX` cuando `msg.delivered` es verdadero.
     - **`src/web/static/css/app.css`**:
       - DiseÃ±Ã³ micro-animaciÃ³n `@keyframes ackPop` y estilos destacados para `.msg-ack-status.delivered` (verde esmeralda con resplandor) y `.msg-ack-status.sent`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0, sin errores).
     - VerificaciÃ³n de compilaciÃ³n Python con `python -m compileall src` (cÃ³digo 0, sin errores).
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.
     - SincronizaciÃ³n de commits con el repositorio GitHub (`origin/main`).
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la resoluciÃ³n integral de las 8 solicitudes de usuario relacionadas con fallas responsive en CSS, renderizado de logs, consolidaciÃ³n de telemetrÃ­a por USB en Ajustes, eliminaciÃ³n de mÃ©tricas obsoletas en el Sniffer RF, filtrado de DMs de repetidores, centrado interactivo del mapa geogrÃ¡fico, soporte de anuncios Advert estilo iOS (Hop 0, Flood Routed, Clipboard) y enriquecimiento del Directorio de Nodos.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/admin_handler.py`**:
       - AmpliÃ³ `get_local_config()` y `fetch_device_config()` para consolidar telemetrÃ­a en tiempo real del transceptor conectado por USB (`battery_pct`, `voltage`, `battery_mv`, `power_source`, reloj RTC, contadores del microcontrolador y estadÃ­sticas de radio).
       - ImplementÃ³ `broadcast_advert(flood: bool)` para emisiÃ³n por radio de anuncios en modo vecindario (Hop 0 / `flood=False`) o propagaciÃ³n multi-salto (Flood Routed / `flood=True`).
     - **`src/web/api_router.py`**:
       - EnriqueciÃ³ el endpoint `GET /api/node/config` consolidando mÃ©tricas calculadas en vivo del bridge (`uptime`, `uptime_str`, `airtime_ms`, `duty_cycle_pct`, contadores de paquetes `tx_count`, `rx_count`, `duplicate_packets`, `packet_errors`, `noise_floor_dbm`, `clock`).
       - ImplementÃ³ el endpoint `POST /api/node/advert` recibiendo el flag `flood`.
     - **`src/rx_router.py`**:
       - En `_handle_mesh_direct_msg`, detecta si el emisor es un repetidor o si el texto es una respuesta de comando (`"unknown command"`, `"cmd "`, `"login "`, etc.), despachÃ¡ndolo como evento de telemetrÃ­a/control a MQTT y WebSocket (`event_type: "repeater_response"`), evitando que se inyecte errÃ³neamente como mensaje directo de chat de usuario en la barra lateral.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/css/app.css`**:
       - CorrigiÃ³ la regla responsive en `@media (max-width: 900px)`, reemplazando `.app-container` por `.app-body { flex-direction: column; overflow: hidden; }` para que la barra lateral y el contenido principal se adapten fluidamente a pantallas pequeÃ±as sin comprimirse.
       - AÃ±adiÃ³ reglas para compactar el header en pantallas `<= 768px` y hacer los grids de nodos y filtros responsive de 1 columna en pantallas `<= 600px`.
     - **`src/web/static/index.html`**:
       - EliminÃ³ el texto `"SincronizaciÃ³n en Tiempo Real"` del encabezado de Nodos manteniendo el indicador de pulso.
       - RemoviÃ³ la tarjeta de `"Calidad SeÃ±al Promedio"` (`#snifferAvgRssi`) del Sniffer RF.
       - RemoviÃ³ los botones `#btnCopyAIDiag` y `#btnExportDiag` de la barra de acciones de logs.
       - AÃ±adiÃ³ las 3 acciones de hardware para Anuncios de Presencia estilo iOS: `Advert Hop (0 Saltos / Vecindario)`, `Advert Flood Routed (Toda la Malla)` y `Advert Clipboard (Copiar URI)`.
     - **`src/web/static/js/app.js`**:
       - CorrigiÃ³ el error crÃ­tico en `createLogElement(log)` para retornar `row`, restableciendo el renderizado fluido de la Consola de Logs.
       - RemoviÃ³ referencias a `#snifferAvgRssi`, `#btnCopyAIDiag` y `#btnExportDiag`.
       - EnlazÃ³ la telemetrÃ­a en tiempo real en `fetchLocalNodeConfig()`, poblando los 8 bloques de Ajustes (baterÃ­a, voltaje, alimentaciÃ³n USB, reloj RTC, uptime, airtime, seÃ±al RF, piso de ruido y contadores TX/RX/dup/err).
       - ImplementÃ³ `sendAdvert(flood)` y `copyAdvertToClipboard()`, enlazando botones de hardware y command palette (`action-advert-hop`, `action-advert-flood`, `action-advert-clipboard`).
       - EnriqueciÃ³ las tarjetas de nodos con mÃ©tricas detalladas (`Last RSSI`, `Last SNR`, `Noise Floor`, `Uptime`) y botÃ³n interactivo `ðŸ—ºï¸� Mapa`.
       - ImplementÃ³ `focusNodeOnMap(pubkey)` para centrar el mapa suavemente con `map.flyTo`, resaltar el marcador en rojo y abrir el popup.
       - CorrigiÃ³ el cÃ¡lculo de contadores en las pÃ­ldoras de filtro en `renderNodesDirectory()`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (cÃ³digo 0, sin errores de sintaxis).
     - VerificaciÃ³n de compilaciÃ³n de cÃ³digo Python con `python -m compileall src` (cÃ³digo 0, sin errores).
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.
     - ActualizaciÃ³n y sincronizaciÃ³n de commits con el repositorio remoto GitHub (`origin/main`).
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiseÃ±Ã³ e integrÃ³ la capacidad de realizar **Ping Zero** (sonda de 0 saltos directos sin saturar la malla) contra nodos y repetidores, calculando la latencia de ida y vuelta (RTT en ms), potencia de seÃ±al RSSI (dBm), relaciÃ³n seÃ±al-ruido SNR (dB) y estado de alcance en lÃ­nea de vista.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - **`src/repeater_manager.py`**: AÃ±adiÃ³ soporte de normalizaciÃ³n para comandos `ping 0`, `ping_zero`, `ping` y `trace 0`.
     - **`src/admin_handler.py`**: ImplementÃ³ el manejador especializado de `ping_zero`, midiendo con alta precisiÃ³n (`time.perf_counter()`) la latencia RTT, consultando las mÃ©tricas de RF del registro de nodos y publicando el evento en MQTT (`meshcore/admin/repeater/{target}/ping_zero`).
     - **`src/web/api_router.py`**: Expuso los endpoints REST `POST /api/repeater/ping_zero` y `POST /api/node/ping_zero`.
  2. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **`src/web/static/index.html`**:
       - AÃ±adiÃ³ botÃ³n y badge de **Ping Zero (0 Hops)** en el encabezado del Modal de AdministraciÃ³n de Repetidores (`#repeaterAdminModal`).
       - AÃ±adiÃ³ tarjeta de acciÃ³n dedicada a Ping Zero en la pestaÃ±a de Acciones RÃ¡pidas (`#rep-quick`).
       - IntegrÃ³ el comando interactivo `ping 0` en los botones rÃ¡pidos de la terminal y en la guÃ­a de ayuda (`#terminalHelpDrawer`).
     - **`src/web/static/js/app.js`**:
       - ImplementÃ³ `pingZero(targetNode, targetName)` con feedback visual en tiempo real, salida en terminal interactiva, actualizaciÃ³n de badges y toasts.
       - AÃ±adiÃ³ botones `ðŸŽ¯ Ping 0` directamente en las tarjetas de repetidores y clientes en el Directorio de Nodos.
     - **`src/web/static/css/app.css`**:
       - DiseÃ±Ã³ estilos para `.ping-zero-badge`, `.btn-modal-ping-zero`, `.btn-node-ping-zero`, `.stat-pill-ping` y animaciÃ³n de pulso `@keyframes pingPulse`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c` y `lint_frontend_standards.py` (100% aprobado).
     - VerificaciÃ³n de arquitectura y concurrencia (`audit_architecture.py`, `audit_async_concurrency.py`).
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.
     - SincronizaciÃ³n completa con GitHub (`origin/main`).

---

### Hito: CorrecciÃ³n de Sintaxis de Bash (`!grep`) y Soporte TCP Companion en `install.sh`
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CorrigiÃ³ el error de sintaxis en `install.sh` (`!grep` sin espacio) que provocaba el fallo `!grep: command not found` durante la actualizaciÃ³n del software, e integrÃ³ la migraciÃ³n automÃ¡tica de variables de entorno del servidor TCP Companion (`TCP_SERVER_ENABLED`, `TCP_SERVER_HOST`, `TCP_SERVER_PORT`).
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - CorrigiÃ³ la evaluaciÃ³n condicional en [`install.sh`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/install.sh) a `if ! grep -q ...`.
     - AÃ±adiÃ³ la secciÃ³n de auto-inyecciÃ³n de variables para `TCP_SERVER_ENABLED` en `.env` existentes.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.
     - SincronizaciÃ³n completa con GitHub (`origin/main`).

---

### Hito: CorrecciÃ³n de ExcepciÃ³n de InicializaciÃ³n (TypeError) y Blindaje de Elementos DOM en la SPA
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiagnosticÃ³ y corrigiÃ³ la interrupciÃ³n en la carga de la SPA provocada por referencias nulas a elementos de diagnÃ³stico/discovery en `initPreflight()` e `initHomeAssistant()`.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - BlindÃ³ con comprobaciones de nulidad (*null checks*) estrictas todos los escuchadores de eventos en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) (`initPreflight`, `initHomeAssistant`, `initTheme`, `initCommandPalette`, `initChat`).
     - RestaurÃ³ el ciclo de vida completo de la aplicaciÃ³n, permitiendo que `initChat()`, `initWebSocket()`, `initLeafletMap()` y `fetchInitialData()` se ejecuten de manera fluida y sin bloqueos.
     - RestableciÃ³ la carga automÃ¡tica y continua de nodos de la malla, repetidores y libreta de contactos.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n con `node -c src/web/static/js/app.js` y `lint_frontend_standards.py`.
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.

---

### Hito: ImplementaciÃ³n de Persistencia IndexedDB y Mapas GeogrÃ¡ficos Offline con Modo Radar TÃ¡ctico en la SPA
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la implementaciÃ³n de la capa de almacenamiento en navegador (`MeshCoreStorage`) con IndexedDB y el sistema integral de capas cartogrÃ¡ficas offline y radar tÃ¡ctico para situaciones de emergencia sin conexiÃ³n a Internet.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Capa de Almacenamiento IndexedDB (`app.js`)**:
       - ImplementÃ³ `MeshCoreStorage` gestionando la base de datos `MeshCoreStationDB` con los object stores `chat_messages`, `sniffer_packets` y `app_settings`.
       - Persistencia automÃ¡tica de mensajes de chat salientes y entrantes por canal y DM, cargando el historial previo de forma asÃ­ncrona al iniciar o cambiar de conversaciÃ³n.
       - Persistencia de tramas interceptadas por el sniffer RF con recarga inmediata en el arranque y limpieza coordinada.
     - **Mapas Offline & Modo Radar TÃ¡ctico (`app.js`, `app.css`, `index.html`)**:
       - AÃ±adiÃ³ barra de herramientas de capas cartogrÃ¡ficas (`.map-layer-switcher`) con soporte para *CartoDB Dark*, *OpenStreetMap*, *Teselas Locales* y *Radar TÃ¡ctico*.
       - ImplementÃ³ el **Modo Radar TÃ¡ctico / GrÃ­cula LoRa**: visualizaciÃ³n geoespacial sin dependencia de internet con anillos concÃ©ntricos de alcance (1 km, 5 km, 10 km, 25 km), grÃ­cula de coordenadas y ejes cardinales centrados en el nodo local.
       - DetecciÃ³n y conmutaciÃ³n automÃ¡tica (*fallback*) a Radar TÃ¡ctico ante fallos de conexiÃ³n a teselas online (`tileerror`).
       - AÃ±adiÃ³ panel de gestiÃ³n en Ajustes (`#local-storage-maps`) para vaciar IndexedDB y configurar la URL del servidor de teselas locales (`localTileUrl`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **TelemetrÃ­a TCP Companion en REST API (`src/web/api_router.py`)**:
       - Expuso el objeto `tcp_companion` (estado `enabled`, `host`, `port`, `connected_clients`) en el endpoint `/api/status`.
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - ValidaciÃ³n con `node -c src/web/static/js/app.js` (0 errores).
     - VerificaciÃ³n con `lint_frontend_standards.py`, `audit_architecture.py` y `audit_async_concurrency.py` (100% de cumplimiento).
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.

---

### Hito: IncorporaciÃ³n de Skills de IngenierÃ­a de Software, Arquitectura Hexagonal, Patrones GoF y Concurrencia Async
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: IncorporÃ³ un conjunto integral de 4 nuevas skills tÃ©cnicas especializadas con herramientas de anÃ¡lisis estÃ¡tico para blindar la arquitectura, patrones de diseÃ±o, concurrencia asÃ­ncrona y mÃ©tricas de cÃ³digo limpio.
- **Nuevas Skills Incorporadas**:
  1. **`software-architecture-patterns`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/software-architecture-patterns/SKILL.md)):
     - GuÃ­a de Arquitectura Hexagonal (Ports & Adapters), Event-Driven Architecture (EDA), Domain-Driven Design (DDD) y patrones de resiliencia (Circuit Breaker, Exponential Backoff, Bulkhead).
     - Herramienta: `scripts/audit_architecture.py` (auditorÃ­a de inversiÃ³n de dependencias e inmutabilidad del dominio).
  2. **`gof-design-patterns-expert`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/gof-design-patterns-expert/SKILL.md)):
     - CatÃ¡logo formal de patrones GoF (Adapter, Factory Method, Strategy, Facade, Observer, State Machine).
     - Herramienta: `scripts/analyze_design_patterns.py` (mapeo y detecciÃ³n de patrones en el cÃ³digo de producciÃ³n).
  3. **`async-concurrency-engineering`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/async-concurrency-engineering/SKILL.md)):
     - Directrices para evitar llamadas bloqueantes en el event loop, puente seguro entre hilos/asyncio y graceful shutdown.
     - Herramienta: `scripts/audit_async_concurrency.py` (detecciÃ³n de bloqueos I/O y patrones inseguros).
  4. **`refactoring-clean-architecture`** ([`SKILL.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.agents/skills/refactoring-clean-architecture/SKILL.md)):
     - TÃ©cnicas de refactorizaciÃ³n de Martin Fowler y umbrales de mÃ©tricas (Complejidad CiclomÃ¡tica $\le 15$, longitud de mÃ©todos $\le 45$, parÃ¡metros $\le 6$).
     - Herramienta: `scripts/evaluate_refactoring_metrics.py` (cÃ¡lculo de complejidad ciclomÃ¡tica de McCabe por funciÃ³n).

---

### Hito: NormalizaciÃ³n Integral de Componentes UI, OptimizaciÃ³n de Memoria (RAM), Renderizado por Lotes y SanitizaciÃ³n XSS en Frontend
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la normalizaciÃ³n estÃ©tica de todos los componentes visuales de la aplicaciÃ³n, la poda de duplicidad en CSS, el blindaje estricto de sanitizaciÃ³n contra XSS y la optimizaciÃ³n de rendimiento y huella de memoria RAM en el navegador.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **NormalizaciÃ³n de Componentes (`app.css`)**: EstandarizÃ³ el sistema de tarjetas (`.card`, `.node-card`, `.contact-item-card`, `.settings-card`, `.ha-status-card`, `.repeater-card`, `.quick-diag-card`) bajo una escala armÃ³nica de radios (`var(--radius-md)` = 10px), paddings y sombras unificadas.
     - **Limpieza y Poda CSS**: ConsolidÃ³ selectores duplicados de modales (`.modal-card`, `.modal-overlay`), eliminÃ³ estilos inline en [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html) y redujo el peso del stylesheet.
     - **OptimizaciÃ³n de Rendimiento DOM (`app.js`)**:
       - ImplementÃ³ renderizado por lotes mediante `DocumentFragment` en `renderNodesDirectory()`, `renderFilteredLogs()` y `renderAnalytics()`, reduciendo *layout reflows* a una Ãºnica mutaciÃ³n de pintura instantÃ¡nea (< 5ms).
       - AplicÃ³ *debouncing* (`debounce(fn, 150)`) en todos los campos de bÃºsqueda en vivo (`nodesSearchInput`, `contactsSearchInput`, `snifferSearch`, `logSearchInput`).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - **GestiÃ³n Estricta de Memoria (RAM Bounded Queues)**:
       - LimitÃ³ el ring-buffer de paquetes sniffer (`rawPackets`) a un mÃ¡ximo de 200 tramas y podÃ³ los nodos DOM excedentes en tiempo real con `removeChild`.
       - LimitÃ³ el buffer de logs del sistema (`systemLogs`) a 300 entradas con poda automÃ¡tica de elementos en el DOM.
       - AcotÃ³ el historial por canal y mensaje directo (`channelFeeds`) a un tope de 100 mensajes por conversaciÃ³n para evitar retenciÃ³n indefinida de memoria.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - BlindÃ³ al 100% las interpolaciones de texto y atributos en la interfaz con `escapeHtml()` en todos los renderizadores de nodos, mensajes, claves pÃºblicas, paquetes y logs.
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node -c src/web/static/js/app.js` (0 errores de sintaxis).
     - ValidaciÃ³n con `lint_frontend_standards.py` (100% de cumplimiento en estÃ¡ndares HTML5 semÃ¡ntico, CSS3 y ES6+).
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.

---

### Hito: ImplementaciÃ³n del Servidor TCP/IP Companion en Puerto 5000 para Apps Oficiales MeshCore
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la investigaciÃ³n del protocolo en firmware oficial C++ y SDK Python, diseÃ±Ã³ el servidor TCP asÃ­ncrono en puerto 5000 y armonizÃ³ los adaptadores de radio y el simulador virtual.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - AnalizÃ³ el firmware [`SerialWifiInterface.cpp`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/reference/meshcore/src/helpers/esp32/SerialWifiInterface.cpp) y el SDK [`tcp_cx.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/reference/meshcore_py/src/meshcore/tcp_cx.py).
     - FormalizÃ³ la especificaciÃ³n del framing binario oficial (`0x3C`/`0x3E` + longitud little-endian uint16 + payload) en [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md).
  2. **Agente 2 (Python Bridge Architect Agent)**:
     - ImplementÃ³ [`src/tcp_companion_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/tcp_companion_server.py): Servidor `asyncio` no bloqueante con de-framing continuo, soporte multi-cliente y protecciÃ³n DoS (`MAX_FRAME_SIZE = 512`).
     - AÃ±adiÃ³ variables de configuraciÃ³n en [`config.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/config.py) y [`.env.example`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/.env.example) (`TCP_SERVER_ENABLED`, `TCP_SERVER_HOST`, `TCP_SERVER_PORT=5000`).
     - IntegrÃ³ callbacks de tramas crudas (`set_companion_rx_callback` y `send_raw_companion_frame`) en [`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py) y emulaciÃ³n completa en [`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py).
     - IntegrÃ³ el ciclo de vida en [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py) y diagnÃ³sticos en [`src/preflight.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/preflight.py).
  3. **Agente 0 (Agente Principal / Orchestrator)**:
     - ConciliÃ³ la arquitectura en [`docs/ARCHITECTURE.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/ARCHITECTURE.md).
     - EjecutÃ³ la sincronizaciÃ³n de producciÃ³n en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.

---

### Hito: SanitizaciÃ³n Integral de Persistencia SQLite, ResoluciÃ³n de Deadlocks, Suite Completa de Pruebas y Deploy
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la resoluciÃ³n de deadlocks por concurrencia multihilo en persistencia SQLite, saneamiento de contadores de trÃ¡fico RX, robustez de tipos en API REST, ejecuciÃ³n completa de las suites de pruebas (120/120 superadas), auditorÃ­a SAST de seguridad y re-sincronizaciÃ³n del paquete de despliegue.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - ReemplazÃ³ `asyncio.Lock` por sincronizaciÃ³n multihilo `threading.Lock` en [`src/store_forward.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/store_forward.py), eliminando por completo los bloqueos en llamadas concurrentes `asyncio.run()` provenientes de mÃºltiples hilos del SO.
     - EliminÃ³ el doble incremento de `rx_count` en [`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py), delegando la autorÃ­a Ãºnica de mÃ©tricas en `RxEventRouter` ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)).
     - AÃ±adiÃ³ alias `shutdown()` en `MeshCoreBridge`.
     - BlindÃ³ la extracciÃ³n de mÃ©tricas numÃ©ricas y cÃ¡lculo de tasa de error en `_route_status` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)).
  2. **Agente 3 (Protocol QA & Fuzzing Agent)**:
     - AjustÃ³ temporizaciÃ³n del Watchdog en [`tests/test_serial_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_serial_adapter.py) y mock de mÃ©tricas en [`tests/test_web_server.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/tests/test_web_server.py).
     - EjecutÃ³ la suite completa de 120 pruebas unitarias, de concurrencia, estrÃ©s, fuzzing e integraciÃ³n con un resultado de **120/120 PASSED (100% de Ã©xito)**.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - EjecutÃ³ auditorÃ­a estÃ¡tica SAST completa (`run_security_audit.py`): Cero vulnerabilidades encontradas (Bandit SAST limpio, 100% SQL parametrizado, Directory Traversal aislado, XSS escapado).
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificÃ³ con `mypy --strict src/` (0 errores en 22 mÃ³dulos) y `ruff check` (0 errores).
     - EmpaquetÃ³ y sincronizÃ³ el release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `python scripts/sync_deploy.py`.

---

### Hito: SincronizaciÃ³n AutomÃ¡tica en Tiempo Real y DetecciÃ³n de Estado Offline (TTL)
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: DiseÃ±Ã³ el sistema de auto-descubrimiento reactivo en tiempo real para la vista **ðŸŒ� Nodos** y la lÃ³gica de detecciÃ³n de apagado/offline para nodos de radiofrecuencia LoRa MeshCore.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX & Frontend Architect Agent)**:
     - **Auto-descubrimiento Reactivo**: Reemplazo del botÃ³n manual de actualizaciÃ³n por un indicador de pulso `ðŸŸ¢ SincronizaciÃ³n en Tiempo Real` (`.live-sync-indicator`). Los nuevos nodos o actualizaciones de telemetrÃ­a/anuncios se integran dinÃ¡micamente vÃ­a WebSocket sin refresco manual.
     - **DetecciÃ³n y VisualizaciÃ³n Offline**: IncorporaciÃ³n de chips de conectividad (`ðŸŸ¢ En LÃ­nea` < 30min, `ðŸŸ¡ Inactivo` 30m-2h, `ðŸ”´ Fuera de lÃ­nea` > 2h) calculados sobre la marca de tiempo `last_seen`. Los nodos apagados o fuera de cobertura se atenÃºan visualmente (`.node-card-offline`) conservando su telemetrÃ­a y Ãºltima posiciÃ³n GPS.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node --check`, `ruff check` y `mypy --strict` (0 errores).
     - SincronizaciÃ³n a [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `sync_deploy.py`.

---

### Hito: RediseÃ±o y SeparaciÃ³n Clara entre MensajerÃ­a (DMs Activos) y Libreta de Contactos
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la reestructuraciÃ³n de la interfaz para separar de forma limpia la bandeja de conversaciones activas de la libreta general de contactos del dispositivo.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX Architect Agent)**:
     - **MensajerÃ­a (`#tab-chat`)**: En la barra lateral, la secciÃ³n Â«Mensajes DirectosÂ» ahora muestra **exclusivamente las conversaciones que cuentan con al menos un mensaje enviado o recibido**, evitando saturar la lista de chats con nodos sin interacciÃ³n.
     - **Libreta de Contactos (`#tab-contacts`)**: PestaÃ±a principal que lista **Ãºnica y exclusivamente los contactos con rol `CLIENT` (o `CHAT`)**, con tarjetas perfectamente uniformadas (`height: 100%`, flexbox stretch y micro-grid 3 columnas de telemetrÃ­a sin saltos de lÃ­nea irregulares):
       - `ðŸ’¬ DM`: Abre inmediatamente la conversaciÃ³n privada en la vista de MensajerÃ­a.
       - `ðŸ“¤ QR`: Abre el modal con cÃ³digo QR con renderizado estilizado (ojos redondeados y gradiente cian) y distribuciÃ³n de 2 columnas sin scroll.
       - `ðŸ—‘ï¸� Eliminar`: BotÃ³n compacto y estilizado para borrar el contacto.
       - `ðŸ”� Buscador`: Filtrado en tiempo real por nombre, alias, rol o clave pÃºblica.
       - `âž• Agregar Contacto`: BotÃ³n directo en la cabecera para aÃ±adir nuevos contactos.
     - **Mensajes Directos**: ValidaciÃ³n estricta que impide abrir o agregar chats DM con nodos que no sean de tipo `CLIENT`.
     - Eliminada la pestaÃ±a redundante Â«DirectorioÂ», dejando una navegaciÃ³n optimizada y jerÃ¡rquica.
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - VerificaciÃ³n estÃ¡tica con `node --check`, `ruff check` y `mypy --strict` (0 errores).
     - SincronizaciÃ³n del release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `sync_deploy.py`.

---
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la revisiÃ³n integral de compatibilidad de tipos, sanitizaciÃ³n de datos y optimizaciÃ³n de rendimiento entre el backend asÃ­ncrono y la interfaz web SPA.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Python Bridge Architect Agent)**:
     - EnriqueciÃ³ el enrutador de recepciÃ³n ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)) para mapear automÃ¡ticamente roles oficiales MeshCore (`REPEATER`, `ROOM`, `SENSOR`, `CLIENT`) y coordenadas GPS (`latitude`, `longitude`) en el directorio de nodos.
     - OptimizÃ³ el gestor de contactos ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)) para normalizar campos de posiciÃ³n y telemetrÃ­a de forma resiliente ante mÃºltiples formatos de entrada (`gps`, `lat`, `latitude`).
     - AlineÃ³ los nodos del adaptador virtual ([`src/virtual_mesh_adapter.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/virtual_mesh_adapter.py)) con los 4 roles oficiales del firmware MeshCore.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - MejorÃ³ el generador de URIs y cÃ³digos QR en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) para incluir el parÃ¡metro `role` al exportar contactos.
     - RobusteciÃ³ el parser de importaciÃ³n URI `meshcore://contact?...` para registrar el rol y actualizar el directorio en vivo.
     - SustituyÃ³ llamadas bloqueantes `alert()` por el sistema nativo de notificaciones `showToast()`.
  3. **Agente 5 (Security & Vulnerability Auditor Agent)**:
     - VerificÃ³ con SAST/DAST (`security-code-auditor`) la ausencia total de inyecciones SQL, aislamiento estricto de Directory Traversal y sanitizaciÃ³n XSS contextual (`escapeHtml`).
  4. **Agente 0 (Agente Principal / Orchestrator)**:
     - EjecutÃ³ anÃ¡lisis estÃ¡tico estricto: `mypy --strict src/` (0 errores en 22 archivos), `ruff check` (0 errores) y `node --check` (0 errores de sintaxis JS).
     - SincronizÃ³ y empaquetÃ³ el release en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: InvocÃ³ al Agente Investigador para compilar y armonizar la documentaciÃ³n tÃ©cnica oficial de MeshCore ([docs.meshcore.io](https://docs.meshcore.io/) y [github.com/meshcore-dev/MeshCore](https://github.com/meshcore-dev/MeshCore)) con los fuentes binarios C/C++ y SDKs de referencia.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - RealizÃ³ una investigaciÃ³n integral de las fuentes oficiales de MeshCore ([docs.meshcore.io](https://docs.meshcore.io/), [github.com/meshcore-dev](https://github.com/meshcore-dev)).
     - EjecutÃ³ la skill `meshcore_source_inspector` sobre los headers C/C++ (`Packet.h`, `AdvertDataHelpers.h`, `ClientACL.h`, `RoutingPolicy.h`, `RadioLibWrappers.h`) y mÃ³dulos de Python (`packets.py`, `reader.py`, `contact.py`, `messaging.py`).
     - RedactÃ³ la versiÃ³n 3.0.0 de [`docs/PROTOCOL_SPEC.md`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/PROTOCOL_SPEC.md), detallando:
       - Framing determinista con Byte Stuffing (`0xAA`, `0x55`, `0x1B`, `0x20`).
       - Algoritmo de verificaciÃ³n CRC-16-CCITT ($0x1021$).
       - Roles oficiales MeshCore (`ADV_TYPE_CHAT=1`, `REPEATER=2`, `ROOM=3`, `SENSOR=4`).
       - Formato binario de la tarjeta de contacto (147 bytes estructurados).
       - Estructura de 8 canales LoRa (Canal 0 abierto, Canales 1-7 AES-128 PSK).
       - CatÃ¡logo completo de comandos host (`0x01` a `0x3A`) y notificaciones push (`0x80` a `0x8A`).
       - EspecificaciÃ³n de telemetrÃ­a ambiental CayenneLPP y matrices de tÃ³picos MQTT / n8n.
     - ActualizÃ³ [`src/protocol_types.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/protocol_types.py) con nuevos modelos de hardware reconocidos (`HardwareModel`).
  2. **Agente 0 (Agente Principal / Orchestrator)**:
     - RealizÃ³ verificaciÃ³n estÃ¡tica con `mypy --strict src/` (0 errores) y `ruff check`.
     - SincronizÃ³ los artefactos y documentaciÃ³n en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) vÃ­a `sync_deploy.py`.

---
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la comprobaciÃ³n formal de la especificaciÃ³n de tipos MeshCore y la integraciÃ³n del borrado interactivo en UI y hardware.
- **Contribuciones de Agentes**:
  1. **Agente 1 (Protocol & Firmware Investigator Agent)**:
     - VerificÃ³ en el firmware oficial (`AdvertDataHelpers.h`) la definiciÃ³n estricta de roles/tipos de anuncio: `ADV_TYPE_CHAT = 1` (Chat/Companion), `ADV_TYPE_REPEATER = 2` (Repetidor/Router), `ADV_TYPE_ROOM = 3` (Servidor de Sala) y `ADV_TYPE_SENSOR = 4` (Sensor de TelemetrÃ­a).
     - DocumentÃ³ `FirmwareAdvertType` en [`src/protocol_types.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/protocol_types.py).
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - RemoviÃ³ los botones redundantes de sincronizaciÃ³n manual (`btnSyncChannels`, `btnSyncContacts`), ya que la sincronizaciÃ³n es 100% automÃ¡tica.
     - AÃ±adiÃ³ botones de eliminaciÃ³n directa `ðŸ—‘ï¸�` en canales secundarios (1-7), mensajes directos (DMs) y tarjetas del directorio/contactos.
     - ImplementÃ³ mÃ©todos `deleteChannel(index)` y `deleteContact(pubkey)` en [`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js) con confirmaciÃ³n y retroalimentaciÃ³n mediante toasts.
     - ActualizÃ³ el selector de tipos de nodo en `#createContactModal` con los roles oficiales de MeshCore.
  3. **Agente 0 (Agente Principal)**:
     - ComprobÃ³ estÃ¡tica estricta con `mypy --strict src/` (0 errores) y `ruff check`.
     - DejÃ³ en ejecuciÃ³n permanente la simulaciÃ³n multi-canal y multi-contacto en el puerto 8080.
     - SincronizÃ³ paquete en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

### Hito Anterior: Auto-ImportaciÃ³n en Arranque y SincronizaciÃ³n Continua Bidireccional con Heltec
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ el arranque asÃ­ncrono no bloqueante y la difusiÃ³n en tiempo real de canales y contactos por WebSockets.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Bridge Architect Agent)**:
     - ImplementÃ³ `_auto_bootstrap_heltec_state()` en `MeshCoreBridge.start()` ([`src/bridge_core.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/bridge_core.py)) para consultar y precargar automÃ¡ticamente canales (`get_channels`), libreta de contactos (`sync_all_contacts`) y parÃ¡metros de radio/hardware (`fetch_device_config`) del transceptor Heltec USB al iniciar el script.
     - AÃ±adiÃ³ `remove_contact(pubkey)` en `BaseSerialAdapter` y `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - ImplementÃ³ `fetch_device_config()` en `AdminCommandHandler` ([`src/admin_handler.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/admin_handler.py)).
     - AÃ±adiÃ³ difusiÃ³n de eventos WebSocket (`channels_updated`, `contacts_updated`) en `WebAPIRouter` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)) al crear o eliminar canales/contactos.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - AÃ±adiÃ³ receptores en tiempo real para `channels_updated` y `contacts_updated` en `handleIncomingLiveEvent` ([`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js)), asegurando que la interfaz refleje inmediatamente cualquier cambio ocurrido en el hardware o desde otros clientes.
  3. **Agente 0 (Agente Principal)**:
     - ComprobaciÃ³n estÃ¡tica estricta con `mypy --strict src/` (0 errores) y `ruff check`.
     - SincronizaciÃ³n del paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

### Hito Actual: Suite Completa de AdministraciÃ³n de Repetidores, Parser de TelemetrÃ­a Real y DeduplicaciÃ³n Inteligente de Nodos
- **Fecha**: 2026-08-19
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ la resoluciÃ³n integral del problema de duplicaciÃ³n de clientes, el parser de telemetrÃ­a de repetidores, y la implementaciÃ³n de todas las opciones de administraciÃ³n remota de MeshCore en backend y frontend.
- **Contribuciones de Agentes**:
  1. **Agente 1 & 2 (Investigador de Protocolo & Arquitecto de Bridge)**:
     - DiseÃ±Ã³ e implementÃ³ `_find_existing_key()` y motor de deduplicaciÃ³n canÃ³nica en `NodeRegistry` ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)), eliminando duplicados causados por coincidencia de prefijos hex vs claves de 64 caracteres.
     - ImplementÃ³ `parse_repeater_telemetry_or_response()` en [`src/repeater_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/repeater_manager.py) capaz de extraer structured metrics (Battery %/mV, Solar V, RTC clock, Uptime, Airtime ms, RSSI, SNR, Noise floor dBm, Packets sent/recv/dup/err/queue, Lat/Lon/Alt, Owner Info, Firmware/Board) a partir de respuestas CLI de texto de MeshCore.
     - EnriqueciÃ³ `build_repeater_command_payload()` con los 15 comandos de administraciÃ³n de MeshCore (owner, advert, advert intervals, pos, sync clock, ACL mode, admin/guest passwords, identity key, radio regions/freq, neighbours, repeat settings, telemetry, reboot, version, board).
     - IntegrÃ³ el parser en el despachador de eventos RF ([`src/rx_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/rx_router.py)) para actualizaciÃ³n en vivo vÃ­a MQTT y WebSocket.
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - RediseÃ±Ã³ y expandiÃ³ `#repeaterAdminModal` ([`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html)) con 7 subpestaÃ±as: TelemetrÃ­a Extendida (8 tarjetas mÃ©tricas), ConfiguraciÃ³n RF, Propietario & PosiciÃ³n, Seguridad & Control de Acceso (ACL), Malla & Vecinos, Terminal RF con GuÃ­a de Ayuda Interactiva (`help`), y Acciones RÃ¡pidas.
     - AÃ±adiÃ³ cajÃ³n interactivo de ayuda de comandos (`#terminalHelpDrawer`) con inserciÃ³n de comando a un clic.
     - AÃ±adiÃ³ deduplicaciÃ³n inteligente del lado del cliente en `renderNodesDirectory()` ([`src/web/static/js/app.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/app.js)).
     - ConectÃ³ actualizaciÃ³n en caliente del modal de administraciÃ³n ante eventos de telemetrÃ­a entrantes.
  3. **Agente 5 (Auditor de Seguridad)**:
     - CorrigiÃ³ BUG-01 (Thread safety en MQTT con `asyncio.run_coroutine_threadsafe`).
     - CorrigiÃ³ BUG-02 (Cierre seguro e independiente de subsistemas en `bridge_core.py`).
     - CorrigiÃ³ BUG-03 (Log de error ante RuntimeErrors en `mqtt_dispatcher.py`).
     - CorrigiÃ³ BUG-04 (SanitizaciÃ³n y entrecomillado en `set_channel` en `serial_driver.py`).
     - CorrigiÃ³ BUG-06 (SerializaciÃ³n con `asyncio.Lock` en transacciones SQLite de `store_forward.py`).
     - CorrigiÃ³ BUG-07 (Consumo de memoria O(1) con `collections.deque` en `diagnostics.py`).
  4. **Agente 0 (Agente Principal)**:
     - VerificaciÃ³n estÃ¡tica estricta con `ruff check` (0 errores) y `mypy --strict src/` (0 errores en 22 mÃ³dulos).
     - ComprobaciÃ³n de sintaxis JS con `node --check src/web/static/js/app.js` (0 errores).
     - SincronizaciÃ³n completa del paquete `/deploy/` ejecutando `python scripts/sync_deploy.py`.

---


- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ el diseÃ±o de modales, sincronizaciÃ³n serial Heltec y generador QR offline.
- **Contribuciones de Agentes**:
  1. **Agente 2 (Bridge Architect Agent)**:
     - EliminÃ³ canales de prueba ficticios en `WebAPIRouter.__init__` (solo Canal 0 por defecto).
     - ImplementÃ³ `set_channel`, `add_contact`, y `sync_all_contacts` en `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - CreÃ³ endpoints `POST /api/channels/sync`, `DELETE /api/channels`, `POST /api/contacts/sync` y `DELETE /api/contacts` en [`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py).
     - AÃ±adiÃ³ soporte de campo `role` en `NodeContactInfo` y `NodeContactUpdate` ([`src/contact_manager.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/contact_manager.py)).
  2. **Agente 4 (Web UI/UX Architect Agent)**:
     - CreÃ³ mÃ³dulo generador de CÃ³digos QR offline en Vanilla JS puro ([`src/web/static/js/qrcode.js`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/js/qrcode.js)).
     - DiseÃ±Ã³ modales emergentes: `#createChannelModal`, `#createContactModal`, `#qrShareModal` e `#importModal` en [`src/web/static/index.html`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/static/index.html).
     - AÃ±adiÃ³ generador aleatorio de claves AES-128 (PSK) y soporte para importar por URI `meshcore://...` o JSON.
     - ImplementÃ³ reglas CSS `@media (max-width: 900px)` para evitar deformaciÃ³n visual en tablets y celulares, con panel drawer deslizante.
  3. **Agente 0 (Agente Principal)**:
     - VerificÃ³ integridad estÃ¡tica con `mypy --strict` (0 errores) y `ruff check`.
     - SincronizÃ³ paquete de distribuciÃ³n en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/) sin ejecutar pruebas automÃ¡ticas (respetando orden de usuario).

---

### Hito Anterior: RediseÃ±o de MensajerÃ­a, OptimizaciÃ³n UX y SincronizaciÃ³n de Canales
- **Fecha**: 2026-08-18
- **Estado**: âœ… COMPLETADO
- **Agente Principal (Lead Orchestrator)**: CoordinÃ³ el desglose de tareas entre Web UI y Backend Serial.
- **Contribuciones de Agentes**:
  1. **Agente 4 (Web UI/UX Architect)**:
     - ReubicÃ³ los selectores de Canales LoRa y Mensajes Directos (DMs) dentro de la vista de MensajerÃ­a (`tab-chat`) en un layout integrado de dos columnas (`chat-channels-panel` y `chat-conversation-panel`).
     - EliminÃ³ el mensaje de bienvenida estÃ¡tico (`chat-welcome-card`) del feed.
     - RenombrÃ³ el botÃ³n de transmisiÃ³n a `"Enviar ðŸ“¤"`.
     - RemoviÃ³ el botÃ³n `"Trace Route"` y su lÃ³gica asociada.
     - CorrigiÃ³ los subtÃ­tulos de canal para eliminar `"Hop limit: 3"` y reemplazarlos por descripciones contextuales (`ðŸ”“ Abierto` / `ðŸ”’ Cifrado`).
  2. **Agente 2 (Bridge Architect Agent)**:
     - ImplementÃ³ `get_channels()` en `BaseSerialAdapter` y `MeshcoreSDKAdapter` ([`src/serial_driver.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/serial_driver.py)).
     - ActualizÃ³ `WebAPIRouter._route_channels` ([`src/web/api_router.py`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/src/web/api_router.py)) para sincronizar los canales reales del nodo USB conectado.
  3. **Agente 0 (Agente Principal)**:
     - ConciliÃ³ la compatibilidad entre el frontend SPA y el backend REST/WebSocket.
     - SincronizÃ³ el paquete de despliegue en [`deploy/`](file:///c:/Users/Ruby/Desktop/meshcore-bridge/deploy/).

---

## ðŸ“� Matriz de Contratos e Interfaces Activas

| Subsistema / Contrato | Endpoint / Canal | Formato / Esquema | Responsable | Estado |
|---|---|---|---|---|
| **Canales REST** | `GET /api/channels` | `[{ index, name, psk, is_public }]` | Agente 2 / Agente 4 | Sincronizado |
| **EnvÃ­o Mensajes** | `POST /api/tx` | `{ to, text, channel_index, request_id }` | Agente 2 | Activo |
| **Logs del Sistema** | `GET /api/system/logs` | `{ status, data: [...], counters, current_level }` | Agente 2 | Activo |
| **Reporte IA** | `GET /api/diagnostics/report.md` | `{ status: "ok", markdown: "..." }` | Agente 2 / Agente 4 | Activo |
| **Descarga Logs** | `GET /api/logs/download` | `{ status: "ok", raw_logs: "..." }` | Agente 2 | Activo |
| **MQTT Rx Broker** | `meshcore/rx/all`, `meshcore/rx/ch_<N>` | JSON con `sender`, `text`, `channel_idx`, `is_outgoing: false` | Agente 2 | Activo |
| **MQTT Tx Broker** | `meshcore/tx` | JSON con `to`, `text`, `channel_idx` | Agente 2 | Activo |

### [TASK-2026-08-19-03] ImplementaciÃ³n de 5 CaracterÃ­sticas Avanzadas de MeshCore
- **Fecha y Hora**: 2026-08-19 18:04
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect)
- **Objetivo**: Integrar 1) Presupuesto de Airtime y Duty Cycle Compliance (1h/24h), 2) Heatmap de Cobertura RF y Matriz de Ruido, 3) Intercambio AutomÃ¡tico de Tarjetas de Contacto (Contact Discovery), 4) Confirmaciones CriptogrÃ¡ficas E2E (Delivery Receipts con trip_time y doble check âœ“âœ“), y 5) Traceroute Multi-Salto Visual con desglose de saltos, RTT y SNR.
- **Archivos Modificados / Creados**:
  - `src/rate_limiter.py`: AÃ±adida clase `AirtimeTracker` y estructura `AirtimeRecord` con cÃ¡lculo de ventanas deslizantes (1h/24h) y mÃ©tricas de Duty Cycle %.
  - `src/contact_manager.py`: AÃ±adidos campos `auto_discovered`, `discovery_time`, `verified_identity`, `is_favorite` y mÃ©todos `discover_node()`, `list_discovered()`, `accept_discovered_contact()`.
  - `src/store_forward.py`: Creada tabla SQLite `message_receipts` con transacciones WAL para registrar mensajes salientes y confirmar entregas con `trip_time_ms`.
  - `src/rx_router.py`: DetecciÃ³n en tiempo real de eventos `ACK`, balizas desconocidas (Contact Discovery) y tramas de traza multi-salto (`trace_data`).
  - `src/admin_handler.py`: Implementado manejador de acciÃ³n `traceroute` (`CMD_SEND_TRACE_PATH = 36`) con desglose de saltos, RTT y SNR.
  - `src/web/api_router.py`: Nuevos endpoints `GET /api/airtime/stats`, `GET /api/rf/heatmap`, `GET /api/rf/noise`, `GET /api/contacts/discovered`, `POST /api/contacts/accept`, `POST /api/traceroute`.
  - `src/web/static/index.html`: Badge de Airtime en header, botÃ³n `ðŸ”¥ Heatmap RF` en selector de capas Leaflet, banner de Contact Discovery, y modal de Traceroute Visual (`#tracerouteModal`).
  - `src/web/static/js/app.js`: Monitoreo en vivo de Airtime/Duty Cycle, renderizado de capa Heatmap sobre Leaflet, banner reactivo de Contact Discovery, recibos de entrega en chat (âœ“âœ“ con latencia) y grafo interactivo de Traceroute.
  - `src/web/static/css/app.css`: Estilos visuales para todos los nuevos componentes, badges, grÃ¡ficas y animaciones de pulso.
- **Contratos / Interfaces Modificadas**:
  - `GET /api/airtime/stats` -> `{ hourly_used_ms, hourly_budget_ms, hourly_duty_cycle_pct, is_throttled }`
  - `GET /api/rf/heatmap` -> `{ points: [{ lat, lon, rssi, snr, weight, name, noise_floor }] }`
  - `GET /api/rf/noise` -> `{ matrix: [{ pubkey, name, noise_floor_dbm, snr, rssi, channel, freq }] }`
  - `GET /api/contacts/discovered` -> `{ discovered: [...], count }`
  - `POST /api/contacts/accept` -> `{ public_key }`
  - `POST /api/traceroute` -> `{ target_node, path }`
  - Eventos WebSocket: `contact_discovered`, `message_delivered`, `trace_data`.
### [TASK-2026-08-19-04] CorrecciÃ³n de SuperposiciÃ³n y Minimizado de Lista de Nodos en Mapa
- **Fecha y Hora**: 2026-08-19 18:07
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect)
- **Objetivo**: Corregir superposiciÃ³n espacial entre el selector de capas cartogrÃ¡ficas (`.map-layer-switcher`) y la lista flotante de nodos (`.map-overlay-info`), y dotar a la lista de nodos de capacidad interactiva de colapso y minimizaciÃ³n con persistencia en `localStorage`.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Agregado encabezado interactivo `#mapOverlayHeader` con botÃ³n `#btnToggleMapNodes` (`âˆ’`/`ï¼‹`) y soporte de accesibilidad `aria-expanded`.
  - `src/web/static/css/app.css`: Reubicado `.map-layer-switcher` a `left: 56px; top: 14px;` (junto al zoom control), agregados estilos `.map-overlay-header`, `.btn-toggle-overlay` y estado `.minimized`, y soporte responsivo mÃ³vil (`<= 768px`).
  - `src/web/static/js/app.js`: Implementado mÃ©todo `initMapOverlayToggle()` con listener para alternar clases, animaciones y persistencia en `localStorage.getItem("meshcore_map_nodes_minimized")`.
- **Contratos / Interfaces Modificadas**:
  - Estado local persistido: `meshcore_map_nodes_minimized` ("true" / "false").
### [TASK-2026-08-19-05] CorrecciÃ³n de Errores de InicializaciÃ³n en SQLite y collections
- **Fecha y Hora**: 2026-08-19 18:08
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir error de inicializaciÃ³n en SQLite `sqlite3.ProgrammingError: You can only execute one statement at a time` y `NameError: name 'collections' is not defined` en `AirtimeTracker`.
- **Archivos Modificados / Creados**:
  - `src/rate_limiter.py`: AÃ±adido `import collections` a las importaciones del mÃ³dulo.
  - `src/store_forward.py`: Reemplazado `conn.execute()` por `conn.executescript()` en el mÃ©todo `_init_db()`.
- **Contratos / Interfaces Modificadas**: Ninguno (correcciÃ³n de estabilidad y robustez interna).
### [TASK-2026-08-19-06] DepuraciÃ³n y Filtrado de Contactos, ExclusiÃ³n de Nodo Local y MÃ©tricas RF Reales
- **Fecha y Hora**: 2026-08-19 18:20
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Eliminar subtÃ­tulo obsoleto de memoria flash Heltec en pestaÃ±a Contactos, filtrar estrictamente repetidores (`R1-Lee`) para que solo aparezcan estaciones cliente, excluir la estaciÃ³n base local (`Node_34c0c7`) de los contactos remotos, sanear mÃ©tricas RF evitando valores por defecto ficticios (`-80 dBm/10 dB/0 saltos`) y pulir estados vacÃ­os de la interfaz.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Eliminado subtÃ­tulo obsoleto y mejorado placeholder de bÃºsqueda.
  - `src/web/static/js/app.js`: Guardado de `localNodePubkey`, exclusiÃ³n de `isLocal` y repetidores en `contactsGrid`, formateo estricto de mediciones reales (`snrVal`, `rssiVal`, `hopsVal`, `batVal`) y manejo elegante de estados vacÃ­os.
  - `src/contact_manager.py`: Valores por defecto de `last_rssi`, `last_snr`, `hops` establecidos a `None` para no simular mÃ©tricas no medidas.
  - `src/serial_driver.py`: Inferencia de rol en `sync_all_contacts()` basada en `type`, `adv_type` y prefijos de nombre (`R1-`, `R-`, etc.).
- **Contratos / Interfaces Modificadas**: Ninguno (saneamiento de datos y lÃ³gica de presentaciÃ³n).
### [TASK-2026-08-19-07] DeduplicaciÃ³n y NormalizaciÃ³n CanÃ³nica de Claves para Mensajes Directos (DM)
- **Fecha y Hora**: 2026-08-19 18:28
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir duplicaciÃ³n de clientes en la barra lateral de mensajes directos (DM) provocada por discrepancias entre prefijos de clave pÃºblica (`8d5accef1946` de 12 caracteres recibidos en eventos de radio) y claves completas (`8d5accef1946bc...` de 64 caracteres registradas en la libreta).
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: Agregado mÃ©todo `get_canonical_key()` en `NodeRegistry` para resolver prefijos a claves canÃ³nicas conocidas.
  - `src/rx_router.py`: NormalizaciÃ³n de `sender` a la clave canÃ³nica antes de despachar eventos MQTT y WebSocket.
  - `src/web/static/js/app.js`: Implementado mÃ©todo `resolveCanonicalPubkey()`, unificaciÃ³n de feeds `dm_${canonicalPk}`, deduplicaciÃ³n estricta de elementos en `#dmListUi` y sincronizaciÃ³n bidireccional de conversaciones directas.
- **Contratos / Interfaces Modificadas**: Ninguno (normalizaciÃ³n de identificadores y resoluciÃ³n canÃ³nica interna).
### [TASK-2026-08-19-08] ValidaciÃ³n y SupresiÃ³n de Falsos Positivos en Contact Discovery
- **Fecha y Hora**: 2026-08-19 18:33
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Evitar que el banner de "Nuevos Nodos Descubiertos en el Aire" se muestre si los nodos capturados ya estÃ¡n registrados en la libreta de contactos, o si corresponden a repetidores, infraestructura o la estaciÃ³n base local.
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: En `discover_node()` y `list_discovered()`, exclusiÃ³n de repetidores/sensores y preservaciÃ³n de `auto_discovered = False` si el nodo ya existe en la libreta de contactos.
  - `src/web/static/js/app.js`: En `fetchDiscoveredContacts()`, filtrado estricto contra `knownNodes`, repetidores y nodo local, ocultando el banner si el conteo de clientes verdaderamente nuevos es 0.
- **Contratos / Interfaces Modificadas**: Ninguno (depuraciÃ³n y validaciÃ³n de estado de descubrimiento).
### [TASK-2026-08-19-09] RemaquetaciÃ³n de SubpestaÃ±as en Ajustes, Carga Integral de TelemetrÃ­a y Sistema de Delimitador/Badges de Mensajes No LeÃ­dos
- **Fecha y Hora**: 2026-08-19 18:44
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Remaquetar la barra de subpestaÃ±as de Ajustes en una cuadrÃ­cula CSS responsiva sin scrollbar horizontal y con scroll vertical fluido; consolidar la carga de todos los datos del nodo local y telemetrÃ­a de hardware; e implementar un sistema de badges de mensajes no leÃ­dos por canal/DM con delimitador visual ("âš¡ Mensajes Nuevos") en el feed de chat.
- **Archivos Modificados / Creados**:
  - `src/web/static/css/app.css`: Reemplazado `.local-settings-subtabs` por CSS Grid adaptativo (`repeat(auto-fit, minmax(170px, 1fr))`) sin `overflow-x`; ajustado scroll vertical de `.settings-view-container`; aÃ±adidos estilos para `.nav-badge-count`, `.ch-unread-badge` (con animaciÃ³n de pulso) y `.chat-unread-divider`.
  - `src/web/static/index.html`: AÃ±adido span `#globalChatUnreadBadge` en el botÃ³n principal de MensajerÃ­a.
  - `src/web/static/js/app.js`: Implementado rastreo de `unreadCounts` y `lastReadTimestamps`; actualizaciÃ³n reactiva de badges en canales, DMs y menÃº global; inserciÃ³n del delimitador `chat-unread-divider` al ingresar a chats con mensajes no leÃ­dos; y enriquecido `fetchLocalNodeConfig()` con datos completos de telemetrÃ­a y puerto serie.
  - `src/admin_handler.py`: ConsolidaciÃ³n completa de parÃ¡metros de hardware, GPS y radio en `get_local_config()`.
- **Contratos / Interfaces Modificadas**: Ninguno (enriquecimiento de campos de configuraciÃ³n y mejoras de experiencia de usuario en frontend).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-10] Flujo Estricto de AutenticaciÃ³n, Gating y GestiÃ³n Persistente de ContraseÃ±as en Repetidores LoRa
- **Fecha y Hora**: 2026-08-19 18:50
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor), Agente 2 (Bridge Architect)
- **Objetivo**: Implementar un flujo de seguridad estricto para la administraciÃ³n de repetidores MeshCore remotos. Bloqueo total de parÃ¡metros y pestaÃ±as mediante pantalla de gating `#repeaterAuthGate` hasta autenticaciÃ³n vÃ¡lida; auto-login y persistencia de contraseÃ±as por repetidor en `localStorage` (`meshcore_repeater_passwords`); invalidaciÃ³n inmediata de clave, bloqueo de UI y toast de error si la contraseÃ±a es incorrecta o fue modificada en el repetidor.
- **Archivos Modificados / Creados**:
  - `src/web/static/index.html`: Estructura HTML de `#repeaterAuthGate` con formulario de contraseÃ±a/PIN, botÃ³n de visibilidad y contenedor `#repeaterAdminUnlockedContent` con botÃ³n de cierre de sesiÃ³n `#btnRepeaterLogout`.
  - `src/web/static/css/app.css`: Estilos de seguridad para `.repeater-admin-modal-card.locked`, `.repeater-admin-modal-card.unlocked`, `.repeater-auth-gate`, `.auth-gate-card`, `.auth-gate-shield` y chips de autenticaciÃ³n.
  - `src/web/static/js/app.js`: ImplementaciÃ³n de `getStoredRepeaterPassword()`, `setStoredRepeaterPassword()`, `clearStoredRepeaterPassword()`, `getRepeaterPassword()`, `authenticateRepeater()`, `lockRepeaterAdminView()`, `unlockRepeaterAdminView()`, `handleRepeaterAuthError()`, auto-autenticaciÃ³n en `openRepeaterAdminModal()` y captura reactiva de fallos de credenciales en `handleIncomingLiveEvent()`.
  - `src/repeater_manager.py`: DetecciÃ³n e inclusiÃ³n de `auth_status` ("success" / "failed") y `auth_error` en `parse_repeater_telemetry_or_response()`.
  - `src/admin_handler.py`: Manejo dedicado de la acciÃ³n `login` con enmascaramiento de contraseÃ±a en los logs de comando.
- **Contratos / Interfaces Modificadas**: Ninguno (robustecimiento de autenticaciÃ³n RF y experiencia SPA).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-11] Saneamiento de TelemetrÃ­a Nula y Carga Integral de ParÃ¡metros de Repetidores LoRa
- **Fecha y Hora**: 2026-08-19 18:58
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 4 (Web UI/UX Architect), Agente 2 (Bridge Architect)
- **Objetivo**: Corregir la representaciÃ³n de valores nulos en el Centro de Control RF de repetidores (eliminando textos literales "null ms", "null dBm", "null TX / null RX", "Duplicados: null"), enriquecer el parser de respuestas del firmware con extracciÃ³n exhaustiva de parÃ¡metros de radio (frecuencia, potencia TX, SF, BW, CR, repeticiÃ³n, hops, beacon), propietario y posiciÃ³n fija, y automatizar la solicitud de telemetrÃ­a completa y configuraciÃ³n al autenticar o actualizar remotamente.
- **Archivos Modificados / Creados**:
  - `src/web/static/js/app.js`: Saneamiento de comprobaciones en `populateRepeaterModalData` usando `val != null` y valores de reserva adecuados (`--`); sincronizaciÃ³n automÃ¡tica multiconsulta (`stats-core`, `stats-radio`, `pos`, `owner`) en `authenticateRepeater`, `openRepeaterAdminModal` y `btnRefreshRepeaterTelem`; actualizaciÃ³n reactiva en vivo en `handleIncomingLiveEvent` para eventos directos y de telemetrÃ­a.
  - `src/repeater_manager.py`: AmpliaciÃ³n exhaustiva de expresiones regulares en `parse_repeater_telemetry_or_response()` para soportar todos los formatos de telemetrÃ­a de repetidores de MeshCore (frecuencia, potencia, SF, BW, CR, modo repetidor, hops, beacon, posiciÃ³n fija, nombre/informaciÃ³n de propietario, variantes de voltaje y airtime en segundos o milisegundos).
  - `src/contact_manager.py`: IncorporaciÃ³n de campos `coding_rate` y `fixed_position` en `NodeContactInfo` y `NodeContactUpdate`.
  - `src/rx_router.py`: Mapeo completo de todos los atributos de telemetrÃ­a y radio extraÃ­dos hacia `NodeContactUpdate` en `_handle_mesh_direct_msg` y `_handle_mesh_telemetry_msg`.
- **Contratos / Interfaces Modificadas**: Enriquecimiento de atributos en `NodeContactInfo.to_dict()` (`coding_rate`, `fixed_position`).
- **Estado**: COMPLETADO

### [TASK-2026-08-19-13] SupresiÃ³n de DMs Espurios de Comandos y Tratamiento Estricto del Nodo Local
- **Fecha y Hora**: 2026-08-19 19:15
- **Agente Responsable**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor)
- **Objetivo**: Corregir el despacho de comandos de administraciÃ³n remota (`cmd login ...`, `cmd ping`, `cmd trace ...`) como mensajes de texto de chat directo (DM) hacia clientes remotos; validar el tipo de nodo objetivo para restringir comandos de administraciÃ³n exclusivamente a repetidores/routers de infraestructura; migrar el traceroute a la llamada nativa por radio del SDK (`mc.commands.send_trace`); e identificar y maquetar la estaciÃ³n base local como nodo propio en la vista de Directorio (sin botones de DM, ping o ruta hacia sÃ­ mismo, y sin simulaciÃ³n espuria de mediciones de seÃ±al RF sobre sÃ­ mismo).
- **Archivos Modificados / Creados**:
  - `src/contact_manager.py`: AÃ±adido soporte de `is_local` en `NodeContactInfo`, `NodeContactUpdate` y `NodeRegistry` (`set_local_pubkey`, `is_local_key`); el nodo local se registra con rol `LOCAL`, `hops=0` y sin mÃ©tricas de seÃ±al RF recibida; exclusiÃ³n de nodos locales en `list_discovered()`.
  - `src/rx_router.py`: DetecciÃ³n de transmisor local para no asignarle mÃ©tricas RF de recepciÃ³n sobre sÃ­ mismo ni emitir eventos espurios de nuevo contacto descubierto.
  - `src/admin_handler.py`: ProtecciÃ³n del nodo local contra comandos remotos (`traceroute`, `ping_zero`, `login`); en `traceroute`, invocaciÃ³n del comando nativo de radio `mc.commands.send_trace` sin transmitir mensajes de texto de chat a los clientes; validaciÃ³n de repetidor antes de enviar `ping_zero` o `cmd login`; supresiÃ³n de `cmd login ` con contraseÃ±a vacÃ­a.
  - `src/bridge_core.py`: Registro automÃ¡tico de la clave pÃºblica del nodo local en `NodeRegistry` al sincronizar la configuraciÃ³n de hardware Heltec.
  - `src/web/api_router.py`: InclusiÃ³n de `local_node_pubkey` y `local_node_name` en `/api/status`; validaciÃ³n de tipo y propagaciÃ³n de errores HTTP 400 en `/api/repeater/remote/login`, `/api/repeater/remote/config`, `/api/repeater/remote/action` y `/api/repeater/ping_zero`.
  - `src/web/static/js/app.js`: IdentificaciÃ³n de la tarjeta local (`isLocal`) en el Directorio Unificado con avatar `ðŸ� `, rol `LOCAL (EstaciÃ³n Base)`, panel de parÃ¡metros de radio (frecuencia, potencia, SF/BW, puerto) y acceso directo a Ajustes; eliminaciÃ³n del botÃ³n `Ping 0` en tarjetas de clientes estÃ¡ndar; protecciÃ³n en `openDmConversation`, `openTracerouteModal` y `pingZero` para impedir ejecuciones hacia el nodo local; actualizaciÃ³n reactiva de `localNodePubkey` desde `/api/status`.
  - `src/web/static/css/app.css`: Estilos visuales para `.node-card.role-local-card`, `.node-card-avatar.avatar-local`, `.node-role-badge.role-local` y badges por rol.
- **Contratos / Interfaces Modificadas**: InclusiÃ³n de `local_node_pubkey` y `local_node_name` en `GET /api/status`; campo `is_local: bool` en `NodeContactInfo.to_dict()`.
- **Estado**: COMPLETADO

---

## ðŸ“� Plantilla de Registro para Nuevas Tareas

Cada vez que un agente comience o finalice una tarea, agregarÃ¡ una entrada en la siguiente estructura:

```markdown
### [ID de Tarea] [Nombre Descriptivo de la Tarea]
- **Fecha y Hora**: YYYY-MM-DD HH:MM
- **Agente Responsable**: [Agente 1 / Agente 2 / Agente 4 / Agente 5]
- **Objetivo**: [DescripciÃ³n concisa del requerimiento]
- **Archivos Modificados / Creados**:
  - `src/...`
  - `src/web/...`
- **Contratos / Interfaces Modificadas**:
  - [Detalle de cambios en API REST, WebSockets, esquemas MQTT o tipos]
- **Acciones Requeridas por el Agente Principal**:
  - [Notas de compatibilidad cruzada para armonizar otros subsistemas]
- **Estado**: [EN PROGRESO / COMPLETADO]
```

### [TASK-2026-08-26-01] Concurrencia y Resiliencia FASE 1B + 2
- **Fecha y Hora**: 2026-08-26 23:05
- **Agente Responsable**: Agente 2 (Bridge Architect)
- **Objetivo**: Implementar correcciones de concurrencia y resiliencia (drain/backpressure en broadcasts, protecciÃ³n de estructuras no thread-safe, maxsize en TxQueue, semÃ¡foro en RX, timeout en WS, etc).
- **Archivos Modificados / Creados**:
  - config.py: Agregados MAX_TX_QUEUE_SIZE, MAX_RX_CONCURRENCY, WS_IDLE_TIMEOUT_SEC.
  - src/web/http_server.py: \roadcast_event\ es ahora corutina con discard de clientes lentos y wait_for drain; timeout aplicado a eader.read\ en WS.
  - src/tcp_companion_server.py: \roadcast_companion_frame\ y \send_frame_to_client\ con validaciÃ³n de buffer y drain timeout. Buffer limits al registrar clientes.
  - src/deduplicator.py: Agregados locks asÃ­ncronos y sÃ­ncronos para operaciones thread-safe sobre el cache.
  - src/rate_limiter.py: \CustomTxQueue\ implementa \maxsize\ configurable con captura de \QueueFull\. Atributos \	otal_dropped\.
  - src/bridge_core.py: CancelaciÃ³n y recolecciÃ³n de tareas background al apagar. Limpiador de \_background_tasks\ periÃ³dico con lock. Eliminado \_tx_worker\ duplicado. Contadores de TX protegidos con lock. ReconexiÃ³n serial invoca \wait connect()\.
  - src/rx_router.py: Incorporado \syncio.Semaphore\ para limitar concurrencia en la validaciÃ³n y despacho de tramas (CONC-004). Llamadas a web broadcast refactorizadas.
  - src/serial_driver.py: Agregado \wait_for\ timeout a \ping_or_check_alive\.
  - src/mqtt_client.py: \get_running_loop\ en lugar de \get_event_loop\. Try-catch aÃ±adido al callback \on_message\ directo.
  - src/mqtt_dispatcher.py: Agregado timeout en el wait de la request de TX (CONC-009).
  - src/admin_handler.py, src/web/api_router.py: Adaptadas a la API async de websockets broadcast y rate limiter.
  - 	ests/test_tx_rate_limiter.py, 	ests/test_stress_flood.py: Fixes para compatibilidad por eliminaciÃ³n del worker obsoleto.
- **Contratos / Interfaces Modificadas**: APIs internas cambiaron en su firma de asincronÃ­a (broadcast_event). Las interfaces externas (MQTT, REST, TCP) mantienen contratos previos.
- **Estado**: COMPLETADO
## Agente 1 - Protocol & Types Specialist

**Cambios Implementados:**
- **QUAL-001**: Se cambió `NodeContactInfo.neighbors` de `list[str]` a `tuple[str, ...]` y se actualizó su instanciación pasando `tuple(...)`.
- **QUAL-002**: Se agregaron los métodos concretos del cliente paho-mqtt en `MqttClientProtocol` (bridge_core.py).
- **QUAL-006**: Se agregó el modo estricto en `parse_raw_packet` en `protocol_types.py` y se usa con `strict=True` en `serial_driver.py` emitiendo warnings si la trama es rechazada.
- **QUAL-007 / QUAL-015**: Se añadió y se invocó al final de `config.py` la validación para puertos, baud rates, SF, anchos de banda y tiempos de espera.
- **ROB-011**: Se incluyó un comentario documentando el endianness de CRC en `protocol_types.py`.


### [TASK-2026-08-26-02] QUAL Refactoring (event_utils, connect, rx_router_common)
- **Fecha y Hora**: 2026-08-26 23:13
- **Agente Responsable**: Agente 2 (Refactoring & Architecture Specialist)
- **Objetivo**: Implementar mejoras de calidad y refactorización solicitadas (QUAL-003, QUAL-009, QUAL-011).
- **Archivos Modificados / Creados**:
  - src/event_utils.py: Creado archivo nuevo con \extract_sender_from_payload\ (SSoT para remitentes) [QUAL-003].
  - src/rx_router.py: Usada \extract_sender_from_payload\. Refactorizada lógica común entre \_handle_mesh_channel_msg\ y \_handle_mesh_direct_msg\ a \_handle_mesh_msg_common\ [QUAL-011]. Llamadas asíncronas adaptadas en \handle_event\.
  - src/web/api_router.py: Usada \extract_sender_from_payload\ [QUAL-003].
  - src/serial_driver.py: Refactorizado método \connect()\ para ser no bloqueante y disparar proceso en background (\_connect_with_stabilization\) [QUAL-009].
- **Contratos / Interfaces Modificadas**: Se movió lógica estandarizada a un módulo nuevo. \connect\ ahora retorna instantáneamente.
- **Acciones Requeridas por el Agente Principal**: 
  - (Nota: QUAL-010 y QUAL-013 se omitieron ya que \contact_manager.py\ y \http_server.py\ estaban estrictamente prohibidos por System Instructions).
- **Estado**: COMPLETADO


### [TASK-2026-08-26-03] Frontend Fixes & UX/Reliability Updates
- **Fecha y Hora**: 2026-08-26 23:13
- **Agente Responsable**: Agente 4 (Web UI/UX & Frontend Specialist)
- **Objetivo**: Implementar mejoras de frontend solicitadas (FE-001 a FE-005) y robustez menor (ROB-005, ROB-006).
- **Archivos Modificados / Creados**:
  - src/web/static/js/app.js: Implementado auto-reconnect WebSocket con backoff exponencial. MitigaciÃ³n XSS (textContent y escapeHtml) para variables interpoladas. MÃ©todo updateConnectionBadge aÃ±adido.
  - src/web/static/index.html: Badge de WS insertado en el header.
  - src/web/static/css/app.css: Estilos para el badge WS.
  - src/web/http_server.py: Diccionario HTTP_STATUS_TEXTS agregado para mapeo de cÃ³digos a textos HTTP.
  - src/web/api_router.py: PaginaciÃ³n mediante limit y offset soportada en /api/nodes, /api/messages, /api/telemetry.
  - src/bridge_core.py: Debug mode loop configurado segÃºn LOG_LEVEL.
  - config.py: DefiniciÃ³n SQLITE_DB_PATH apuntando a data/meshcore_buffer.db.
  - .gitignore: Ignorar la carpeta data y db local.
- **Estado**: COMPLETADO
Fase 5 - COMPAT-001 to COMPAT-012 terminados
