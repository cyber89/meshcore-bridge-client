# ADR 0025: Descomposición de God Classes en Núcleo y Serial bajo el Patrón Transparent Facade

- **Estado**: Aceptado
- **Fecha**: 2026-10-31
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase 4 del Plan de Corrección Backend (`auditoria_backend_y_plan_correccion.md`), `src/bridge_core.py`, `src/core/ack_tracker.py`, `src/core/companion_proxy.py`, `src/core/tx_coordinator.py`, `src/serial/sdk_adapter.py`, `src/serial/companion_protocol.py`, `src/serial/firmware_cli.py`, `src/serial/sdk_event_dispatcher.py`

---

## Contexto y Problema

Durante la evolución del bridge, las clases centrales `MeshCoreBridge` y `MeshcoreSDKAdapter` acumularon múltiples responsabilidades ortogonales, convirtiéndose en *God Classes* con alta sobrecarga cognitiva, acoplamiento e incremento de complejidad ciclomática:

1. **`MeshCoreBridge` (Capa de Aplicación y Orquestación)**:
   - Superaba las 2,300 líneas de código y más de 80 métodos.
   - Gestionaba simultáneamente: el ciclo de vida general del servicio, la cola TCP Companion y su framing de bajo nivel, el seguimiento y correlación de confirmaciones de entrega (ACKs) en memoria y base de datos, el enrutamiento de transmisiones salientes (TX) con validación de destinos, y la coordinación de airtime y métricas.
   - La correlación de ACKs y la lógica del servidor TCP Companion introducían dependencias cruzadas que dificultaban la verificación aislada y el testeo unitario sin instanciar la totalidad del bridge.

2. **`MeshcoreSDKAdapter` (Capa de Infraestructura y Transporte)**:
   - Superaba las 1,100 líneas de código.
   - Mezclaba el ciclo de vida del puerto serie y arranque de hardware con: el protocolo de tramas binarias Companion (`<` y `>`), la gestión de sesiones y leases CLI concurrentes vía consola, y la cola de ingestión y deduplicación de eventos SDK.
   - Las operaciones de consola CLI y configuración CAD/WiFi carecían de un aislamiento estricto por corrutina, arriesgando condiciones de carrera si dos tareas solicitaban comandos CLI simultáneamente.

A pesar de esta concentración de código, el sistema contaba con más de 2,200 pruebas unitarias y de integración que dependían de los contratos públicos, firmas, propiedades y convenciones de inicialización de ambas clases. Cualquier refactorización debía eliminar la deuda técnica sin romper la compatibilidad hacia atrás ni relajar las invariantes de dominio SSoT (§1.1 y §1.2).

## Factores de Decisión

1. **Filosofía de Deep Modules (John Ousterhout)**:
   - Dividir las responsabilidades en módulos profundos cohesivos, con interfaces públicas simples que oculten una implementación robusta.
2. **Patrón Transparent Facade**:
   - Mantener intactas las clases originales `MeshCoreBridge` y `MeshcoreSDKAdapter` como fachadas de alto nivel.
   - Conservar todas las firmas de métodos, propiedades y decoradores existentes, delegando internamente en los nuevos componentes especializados.
   - Soportar instanciaciones parciales y mocks de prueba (mediante `__new__` o `SimpleNamespace`) a través de resolutores perezosos (*lazy resolvers*) que inyectan dependencias por demanda.
3. **Respeto Estricto de Invariantes SSoT**:
   - Garantizar que los repetidores de infraestructura nunca reciban mensajería de chat (canales o DM), pero preservando íntegramente la capacidad de administración remota, ping y telemetría oficial.
   - Garantizar la prohibición de bucles hacia la propia clave pública de la estación base local.
4. **Concurrencia Determinista en AsyncIO**:
   - Colas acotadas (bounded queues) para evitar consumo desmedido de memoria RAM.
   - Contexto task-local para comandos de consola firmware (`ContextVar`), aislando los leases de sesión entre corrutinas concurrentes.

---

## Decisión

Se adopta la descomposición modular de `MeshCoreBridge` y `MeshcoreSDKAdapter` utilizando el patrón **Transparent Facade** y composición:

### 1. Descomposición de `MeshCoreBridge`

Se extraen tres módulos cohesivos en el paquete `src/core/`:

1. **`AckTracker` ([`src/core/ack_tracker.py`](../../src/core/ack_tracker.py))**:
   - Encapsula el registro, correlación, resolución y caducidad de códigos de entrega ACK L2/L4 esperados tras envíos por radio.
   - Aplica un tiempo de vida (TTL) configurable de 3,600 segundos, capacidad acotada a un máximo de 200 entradas en RAM y algoritmo de poda temporal (`prune()`).
   - Soporta sincronización bidireccional transaccional con SQLite (`StationDatabase.update_delivery`), persistiendo tiempos de ida y vuelta (*trip_time_ms*).

2. **`CompanionProxy` ([`src/core/companion_proxy.py`](../../src/core/companion_proxy.py))**:
   - Encapsula el procesamiento de tramas binarias de la pasarela oficial TCP Companion (puerto 4403).
   - Administra el reenvío bidireccional estricto FIFO de tramas entre los clientes de red y el transceptor físico.
   - Aplica las guardas SSoT §1.1 y §1.2: bloquea activamente cualquier intento de enviar texto o chat hacia repetidores o la clave pública local, pero permite sin restricciones opcodes administrativos y de diagnóstico (`SEND_LOGIN`, `SEND_STATUS_REQ`, `SEND_TELEMETRY_REQ`, `SEND_PATH_DISCOVERY_REQ`, `SEND_ANON_REQ`, comandos CLI con `txt_type == 1`).

3. **`TxCoordinator` ([`src/core/tx_coordinator.py`](../../src/core/tx_coordinator.py))**:
   - Coordina la ejecución y el ciclo de vida de transmisiones salientes hacia la malla LoRa.
   - Normaliza y valida identidades de destino (resolviendo nombres de contacto, canales o difusión pública).
   - Valida la admisibilidad antes de invocar la radio, formatea eventos de chat salientes con metadatos requeridos por la persistencia (`dm_target`, `is_direct`, `recipient_name`), registra paquetes en `PacketBuffer` y actualiza métricas (`tx_count`, `tx_error_count`) de forma atómica y determinista.

4. **Fachada `MeshCoreBridge` ([`src/bridge_core.py`](../../src/bridge_core.py))**:
   - Conserva su interfaz original delegando en `_ack_tracker`, `_companion_proxy` y `_tx_coordinator`.
   - Utiliza métodos de resolución de clase (`_get_ack_tracker`, `_get_companion_proxy`, `_get_tx_coordinator`) para construir o reutilizar componentes bajo demanda, garantizando funcionamiento transparente tanto en ejecución normal como en fixtures de pruebas que instancian atributos vía mock.

---

### 2. Descomposición de `MeshcoreSDKAdapter`

Se modulariza el paquete `src/serial/` dividiendo el adaptador en tres submódulos especializados:

1. **`CompanionProtocol` ([`src/serial/companion_protocol.py`](../../src/serial/companion_protocol.py))**:
   - Centraliza las tablas de comandos oficiales del protocolo Companion (`_COMPANION_RF_COMMANDS`, `_COMPANION_MIN_LENGTHS`, `_RAW_REPLY_TYPES`).
   - Implementa el discriminador `companion_command_kind`, funciones de truncado seguro UTF-8 para nombres y textos, y validación estricta de permisos de chat raw (`is_raw_chat_permitted`).

2. **`FirmwareCliHandler` ([`src/serial/firmware_cli.py`](../../src/serial/firmware_cli.py))**:
   - Gestiona el lease task-local de la consola CLI del firmware mediante `ContextVar[str | None]`, garantizando que ninguna corrutina interfiera con la sesión de terminal de otra.
   - Genera prefijos aleatorios de sesión de comando, filtra respuestas no deseadas y administra la lectura y escritura de preferencias avanzadas de firmware (CAD, WiFi).

3. **`SdkEventDispatcher` ([`src/serial/sdk_event_dispatcher.py`](../../src/serial/sdk_event_dispatcher.py))**:
   - Implementa una cola asíncrona acotada a 256 eventos para el desacoplamiento entre el hilo de recepción del SDK oficial y el event loop principal de asyncio.
   - Deduplica anuncios de paquetes repetidos y provee un despachador thread-safe con parada limpia y segura.

4. **Fachada `MeshcoreSDKAdapter` ([`src/serial/sdk_adapter.py`](../../src/serial/sdk_adapter.py))**:
   - Mantiene la firma completa de la clase base `BaseSerialAdapter`.
   - Delega la interpretación de tramas en `CompanionProtocol`, los comandos CLI en `FirmwareCliHandler` y la entrega de eventos en `SdkEventDispatcher`.

---

## Consecuencias y Beneficios

1. **Alta Cohesión y Bajo Acoplamiento**: Cada componente encapsula un único aspecto del sistema, con responsabilidades claramente delimitadas.
2. **Reducción de Complejidad**: Desaparecen los métodos sobredimensionados de más de 100 líneas dentro del orquestador central y del driver serie.
3. **Compatibilidad Hacia Atrás del 100%**: Ninguna ruta de la API REST, WebSocket Hub, cliente MQTT ni suite de pruebas requirió cambios en sus llamadas hacia `MeshCoreBridge` o `MeshcoreSDKAdapter`.
4. **Testabilidad Aislada**: Es posible testear la lógica de reintentos ACK o el framing Companion de forma puramente unitaria en memoria, sin depender del puerto serie ni del loop de red.
5. **Robustez de Concurrencia**: Se eliminan condiciones de carrera en la consola firmware gracias al aislamiento task-local por `ContextVar`.
