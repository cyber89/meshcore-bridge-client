# ADR 0024: Registro de Capacidades, Opcionalidad en Runtime y Desacoplamiento de Servicios Opcionales

- **Estado**: Aceptado
- **Fecha**: 2026-10-22
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F4 del Plan de Evolución `nuevo.md`, `src/application/capabilities.py`, `src/capabilities.py`, `src/services_manager.py`, `src/health_reporter.py`, `src/bridge_core.py`, `src/diagnostics.py`, `src/web/controllers/services_controller.py`, `src/web/api_router.py`, `pyproject.toml`

---

## Contexto y Problema

Históricamente, MeshCore Bridge asumía un entorno monolítico donde todas las dependencias externas (FastAPI, Starlette, Uvicorn, Paho MQTT) estaban instaladas y todos los servicios de red debían operar concurrentemente:

1. **Falso Estado Degradado**: Si un operador deshabilitaba el broker MQTT local o externo (`MQTT_ENABLED=false` o `local_mqtt.enabled=false`), el reporte periódico de salud (`HealthReporter` y `DiagnosticsManager`) marcaba la estación como `"degraded"`, cuando en realidad se trataba de una configuración intencional y operativa.
2. **Fragilidad en Entornos Headless o Embebidos**: Al intentar ejecutar la estación en SBCs restringidos sin el stack web instalado, las importaciones a nivel de módulo o el arranque de FastAPI provocaban `ImportError` o fallos catastróficos, impidiendo su uso como gateway LoRa serial puro o CLI/daemon.
3. **Inestabilidad de Referencias ante Hot-Reload**: Cuando se recargaba en caliente la configuración de red (`ServicesManager.reload_services()`), el cliente MQTT se recreaba, requiriendo reescribir manualmente atributos internos (`bridge.mqtt`, `rx_router._ctx.mqtt`, `mqtt_dispatcher._ctx.mqtt`), arriesgando referencias obsoletas (*stale references*).
4. **Ausencia de un Modelo Formal de Ciclo de Vida**: No existía una taxonomía clara para distinguir si una funcionalidad estaba **instalada** (paquete Python presente en el entorno), **configurada** (habilitada en configuración), **instanciada** (objeto creado), **iniciada** (bucle o tarea activa) u **operativa** (saludable y respondiendo tráfico).

## Factores de Decisión

1. **Modelo de Ciclo de Vida en 5 Niveles**:
   - `installed`: Módulo disponible en el intérprete sin forzar su carga agresiva.
   - `configured`: Habilitado por el operador vía archivo o entorno.
   - `instantiated`: Subcomponente construido en memoria.
   - `started`: Tarea o worker en ejecución.
   - `operational`: Enlace establecido y saludable.
2. **Separación Estricta entre Liveness y Readiness**:
   - **Liveness**: El proceso Python está vivo y el event loop LoRa/Serial no está bloqueado.
   - **Readiness**: Cada subsistema opcional reporta individualmente si está listo para recibir tráfico.
3. **Core Indestructible**: El núcleo de la estación (`CORE`: Radio LoRa, SQLite, Serial Companion, Rate Limiter) es la única capacidad esencial. La falta o degradación de Web, MQTT o TCP Companion no debe interrumpir el arbitraje de la radio ni el enrutamiento de la malla.
4. **Perfiles Granulares de Dependencias (`pyproject.toml`)**: Ofrecer perfiles explícitos (`core`, `web`, `mqtt`, `all`, `dev`) para despliegues ligeros.

## Decisión

Se implementa el subsistema integral de capacidades y desacoplamiento de servicios opcionales:

### 1. `CapabilityRegistry` y `CapabilityHandle` (`src/application/capabilities.py`)
- Define los identificadores canónicos de capacidad: `core`, `web`, `companion`, `mqtt_local`, `mqtt_external`.
- Define los estados normalizados de ciclo de vida (`CapabilityState`): `not_installed`, `disabled`, `starting`, `available`, `degraded`, `failed`.
- Proporciona introspección no invasiva (`is_module_installed`, `is_web_installed`, `is_mqtt_installed`) utilizando `importlib.util.find_spec` sin ejecutar código arbitrario en módulos opcionales ausentes.
- `CapabilityHandle` ofrece mutación y consulta ergonómica (`mark_configured`, `mark_instantiated`, `mark_started`, `mark_operational`, `mark_stopped`, `mark_failed`, `is_installed`, `is_active`).

### 2. Fachada `StableMqttPort`
- Proporciona un objeto de puerto perenne (`StableMqttPort`) con resolución dinámica de cliente y tópicos (`MqttTopics`).
- Los despachadores y routers interactúan a través de `publish_safe` y propiedades dinámicas (`topic_tx_status`, `topic_admin_status`, `topic_health`, `topic_alert`), garantizando que un hot-reload en `ServicesManager` nunca deje punteros rotos, mientras que los contratos estrictos de identidad para suites existentes se preservan íntegramente.

### 3. Reporte de Salud Consciente de Opcionalidad
- `HealthReporter`, `DiagnosticsManager` y `MeshCoreBridge.get_health()` consultan el `CapabilityRegistry`: si MQTT está deshabilitado o no instalado por diseño, la estación se reporta como `"healthy"` siempre que el enlace serie esté conectado.
- El payload JSON consolidado incluye el bloque estructurado `"capabilities"` con el estado de los 5 niveles.

### 4. Modo Headless Resiliente
- `MeshCoreBridge._create_web_server()` evalúa la disponibilidad de FastAPI/Uvicorn vía `capabilities.web.is_installed`. Si las dependencias no están presentes o `WEB_ENABLED=false`, emite un aviso informativo y continúa el arranque en modo headless sin excepciones.
- Si el servidor web falla en ejecución, `_on_web_server_failure()` marca la capacidad como `FAILED` sin derribar el proceso ni reiniciar la conexión física con la radio LoRa.

### 5. Exposición en API REST y Perfiles `pyproject.toml`
- Se habilitan los endpoints `GET /api/capabilities` y `GET /api/services/capabilities` a través de `ServicesController.get_capabilities()`.
- Se integran los perfiles opcionales en `pyproject.toml`:
  - `core = []`: Radio LoRa, persistencia SQLite, framing Companion y rate limiting.
  - `web = [...]`: FastAPI, Uvicorn, Starlette, WebSockets.
  - `mqtt = [...]`: Paho-MQTT.
  - `all = [...]`: Suite completa para estaciones base integrales.

## Consecuencias

- **Positivas**:
  - Despliegue flexible: MeshCore Bridge puede ejecutarse desde microcontroladores con Linux embebido en modo headless puro (consumo mínimo de memoria) hasta estaciones completas con SPA y broker MQTT.
  - Eliminación de falsos positivos en monitorización LAN/n8n.
  - Hot-reload completamente determinista sin fugas ni referencias rotas.
- **Negativas / Compensaciones**:
  - Requiere mantener sincronizados los perfiles de dependencias y la verificación estática estricta en todos los caminos de código opcional.
