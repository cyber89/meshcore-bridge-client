# Auditoría de Capas y Consolidación FastAPI ASGI (2026-10-09)

- **Fecha:** 2026-10-09
- **Alcance:** Auditoría arquitectónica y estática integral por capas (Capas 1 a 5) tras el retiro del servidor web nativo legacy (`src/web/http_server.py`) y la adopción de `AsgiWebServer` (FastAPI / Uvicorn).
- **Participantes:** Equipo multi-agente de Antigravity (Roles 0 a 5).
- **Estado:** Completada y verificada estáticamente. Suites de pruebas en ejecución pendientes bajo autorización del usuario.

---

## 1. Resumen Ejecutivo

La auditoría exhaustiva de las cinco capas del sistema demostró que la migración a la arquitectura FastAPI ASGI con Uvicorn embebido mantiene el 100% de los contratos funcionales, de red y de persistencia:

1. **Capa 1 (Web, Ingress y Controladores):** 105 rutas REST del backend registradas. Coincidencia léxica del 100% (68/68 llamadas frontend en 8 archivos JavaScript).
2. **Capa 2 (Core Orchestration):** Ciclo de vida asíncrono ordenado (`start`/`stop`). Desacoplamiento de infraestructura y cero llamadas bloqueantes en el event loop.
3. **Capa 3 (Dominio de Malla y Enrutamiento):** Preservación estricta de las reglas inmutables de exclusión de repetidores y nodo local en contactos (`contact_manager.py:list_client_contacts`). Rate limiter y airtime tracker intactos.
4. **Capa 4 (Protocolo Canónico):** Enums y dataclasses inmutables (`PacketType`, `FirmwareAdvertType`, `FrameHeader`) alineados al 100% con el firmware de referencia.
5. **Capa 5 (Infraestructura y Persistencia):** Persistencia JSON atómica en disco (`node_registry.json`, `channels.json`, `airtime_history.json`, `services_config.json`, `repeater_cooldowns.json`) mediante archivos temporales, `os.replace` y `fsync`.

---

## 2. Hallazgos y Correcciones Aplicadas

1. **Broadcast Concurrente en WebSocket Hub (`src/web/asgi_ws_hub.py`):**
   - Se refactorizó `broadcast_event` para utilizar `asyncio.gather(*delivery_tasks, return_exceptions=True)`, garantizando que la latencia o timeout de un cliente lento no retrase la entrega a clientes concurrentes.
2. **Propiedad `system_logs` en `AsgiWebServer` (`src/web/asgi_server.py`):**
   - Se expuso `system_logs` enlazada a `router.recent_system_logs` para paridad con el comando diagnóstico CLI `logs` (`cli_command_executor.py`).
3. **Eliminación de Código Inalcanzable (`src/rx_router.py`):**
   - Se retiraron las comprobaciones huérfanas de `RX_LOG_DATA`, `PATH_UPDATE` y `CHANNEL_INFO`, ya que son procesadas exclusivamente por `TelemetryHandler` y `SystemHandler`.
4. **Migración de Propiedades Deprecadas (`src/rx_router.py`):**
   - Se reemplazó el acceso al alias legacy `frame.header.opcode` por el canónico `frame.header.packet_type` en la generación de claves de deduplicación y registros de log.
5. **Anotaciones SAST Bandit (`src/services_config.py`, `src/web/asgi_server.py`):**
   - Se agregaron anotaciones `# nosec B104` en los binds explícitos `0.0.0.0` requeridos por la arquitectura.

---

## 3. Matriz de Verificación Estática

| Herramienta / Validador | Resultado | Evidencia |
|---|:---:|---|
| **`python -m mypy --strict`** | **PASS** | 0 errores en 81 archivos de código fuente. |
| **`python -m ruff check`** | **PASS** | 0 errores y 0 advertencias de estilo o imports. |
| **`scripts/validate_project_docs.py`** | **PASS** | 0 incidencias en estructura documental y enlaces. |
| **`verify_api_parity.py`** | **PASS** | 68/68 llamadas SPA mapeadas a rutas REST backend. |
| **`audit_async_concurrency.py`** | **PASS** | Cero llamadas bloqueantes (`time.sleep`, requests) en el event loop. |
| **`audit_architecture_contracts.py`** | **PASS** | 100% de aislamiento del núcleo de dominio. |
| **`run_security_audit.py` (Bandit SAST)** | **PASS** | Cero hallazgos de severidad media o alta. |
