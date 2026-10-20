# Referencia de Navegación e Inferencia para Modelos de IA

> **Documento Oficial para Agentes Autónomos y Modelos de Inteligencia Artificial**  
> **Propósito**: Guía de alta densidad de información, determinista y libre de ambigüedades para razonamiento automático, generación de código y navegación en el repositorio **MeshCore Bridge**.

---

## 1. Jerarquía de Verdad Única (SSoT Precedence Order)

Cuando dos documentos o fuentes parezcan divergir, el modelo de IA **DEBE** resolver el conflicto aplicando estrictamente este orden de precedencia decreciente:

```text
Nivel 0: AGENTS.md (Reglas operativas del usuario y prohibiciones de ejecución)
   ↓
Nivel 1: CONTEXT.md (Modelo de dominio canónico, clasificación de nodos e invariantes de red)
   ↓
Nivel 2: Firmware C++ y SDK Oficial en /reference/ + PROTOCOL_SPEC.md (Contratos binarios oficiales)
   ↓
Nivel 3: docs/ARCHITECTURE.md (Arquitectura del sistema en 5 capas y concurrency model)
   ↓
Nivel 4: Manuales Vivos de Subsistema (docs/STORAGE.md, DEPLOYMENT_GUIDE.md, FRONTEND_DELIVERY.md, etc.)
   ↓
Nivel 5: Registros de Decisiones de Arquitectura Vigentes (docs/adr/0001 al 0018)
   ↓
Nivel 6: Planes de Modernización (docs/plans/)
   ↓
Nivel 7: Historial de Auditorías y Decisiones Sustituidas (docs/audits/, docs/fastapi/)
```

---

## 2. Invariantes Críticas del Dominio (Reglas RFC 2119)

1. **`MUST NOT` Agregar Repetidores a Contactos**:  
   Cualquier nodo con rol `REPEATER` (`FirmwareAdvertType.REPEATER = 2`) **NUNCA** debe ser incluido en la libreta de contactos (`NodeRegistry.list_client_contacts()`) ni ser destinatario de mensajes de chat (broadcast ni DM). Su interacción es exclusivamente administrativa (`repeater_manager.py`).
2. **`MUST NOT` Generar Bucles hacia el Nodo Local**:  
   El transceptor anfitrión (`LOCAL`) **NUNCA** debe enviarse mensajes dirigidos a su propia clave pública.
3. **`MUST` Pasar Todo Tráfico RF por el Limitador de Tasa**:  
   Ningún componente puede transmitir por radio LoRa sin pasar por `TxRateLimiter` (`src/rate_limiter.py`) y registrar airtime en `AirtimeTracker`.
4. **`MUST NOT` Bloquear el Event Loop de AsyncIO**:  
   Está estrictamente prohibido invocar operaciones de I/O bloqueantes (I/O de disco síncrono, `time.sleep`, sockets síncronos) en el event loop principal.
5. **`MUST` Ejecutar Persistencia SQLite en Hilos de Trabajo**:  
   Las operaciones con la base de datos `StationDatabase` (`src/station_database.py`) deben ser ejecutadas fuera del bucle de eventos mediante `asyncio.to_thread()` o un executor.
6. **`MUST` Persistir Timers y Cooldowns**:  
   Los timestamps de enfriamiento y límites de tasa deben persistirse en disco (`repeater_cooldowns.json` o SQLite). Nunca deben residir exclusivamente en variables de instancia volátiles.
7. **`MUST` Diferenciar Tipos de Framing**:  
   El framing Companion oficial (`<`/`>`, longitud LE `uint16` y payload) es gestionado por el SDK. El framing raw propio (`0xAA/0x55` + CRC16 de `MeshcoreFrame`) es un parser en memoria, no transporte físico UART.
8. **`MUST NOT` Activar Repetición en Servidores ROOM en MeshCore 1.18+**:  
   El comando `set repeat on` está explícitamente bloqueado para dispositivos con rol `ROOM` (`FirmwareAdvertType.ROOM = 3`).
9. **`MUST NOT` Ejecutar Suites de Pruebas Automáticamente**:  
   Está terminantemente prohibido ejecutar `pytest`, Playwright o herramientas de fuzzing salvo que el usuario lo solicite explícitamente en su mensaje.

---

## 3. Matriz Canónica de Clasificación de Dispositivos

Basada estrictamente en la especificación binaria de MeshCore (`AdvertDataHelpers.h`, `FirmwareAdvertType`):

| `FirmwareAdvertType` | Código | Rol Canónico | Capacidades Permitidas | Prohibiciones |
|:---:|:---:|:---:|---|---|
| `NONE` / `CHAT` | `0` / `1` | `CLIENT` | Mensajería de texto (Canal / DM), telemetría, ping | Acceso a comandos admin de repetidor |
| `REPEATER` | `2` | `REPEATER` | Comandos remotos admin, telemetría, traceroute, ping hop 0 | **Chat de texto (DM o broadcast)** |
| `ROOM` | `3` | `ROOM` | BBS, telemetría, administración de sala | **`set repeat on` (rechazado en v1.18+)** |
| `SENSOR` | `4` | `SENSOR` | Telemetría periódica Cayenne LPP / Custom, suscripciones `0x08`/`0x09` | Mensajería interactiva |
| — | — | `LOCAL` | Estación base host conectada por UART/TCP | **Automensajería (bucle local)** |

---

## 4. Índice de Módulos y Símbolos de Producción

| Dominio / Subsistema | Archivo Principal | Clase / Función Clave | Responsabilidad |
|---|---|---|---|
| **Punto de Entrada** | `meshcore_bridge.py` | `MeshCoreBridge` | Arranque, composición de dependencias y orquestación |
| **Núcleo Asíncrono** | `src/bridge_core.py` | `BridgeCore` | Inicialización de colas, suscripción a eventos y shutdown |
| **Driver de Radio** | `src/serial_driver.py` | `SerialDriver` | Ciclo de vida UART, reconexión con backoff exponencial |
| **Adaptador SDK** | `src/serial/sdk_adapter.py` | `MeshcoreSDKAdapter` | Enlace con SDK oficial Companion (`meshcore_py`) |
| **Enrutador de Entrada** | `src/rx_router.py` | `RxRouter` | Deserialización, clasificación por opcode y entrega a bus |
| **Deduplicador** | `src/deduplicator.py` | `PacketDeduplicator` | Filtrado de duplicados RF mediante ventana deslizante en RAM |
| **Control de Airtime** | `src/rate_limiter.py` | `TxRateLimiter`, `AirtimeTracker` | Medición de duty cycle (1%), espaciado y límite de transmisión |
| **Resolución de Destinos** | `src/target_resolver.py` | `TargetResolver` | Mapeo de prefijos, apodos y claves públicas de 64 caracteres |
| **Registro de Nodos** | `src/contact_manager.py` | `NodeRegistry` | Registro de vecinos LoRa, telemetría y libreta de contactos |
| **Calidad de Enlace** | `src/lqi_engine.py` | `LQIEngine` | Cálculo de Link Quality Index mediante SNR, RSSI y saltos |
| **Gestión de Infraestructura** | `src/repeater_manager.py` | `RepeaterManager` | Envío de comandos remotos y persistencia de cooldowns |
| **Manejador de Sensores** | `src/sensor_decoder.py` | `decode_sensor_packet` | Decodificación binaria de tramas Cayenne LPP y custom |
| **Broker MQTT** | `src/mqtt_client.py` | `AsyncMQTTClient` | Conexión Paho MQTT asíncrona hacia automatizaciones n8n |
| **MQTT Externo** | `src/external_mqtt.py` | `ExternalMQTTBridge` | Puente hacia brokers MQTT públicos/externos con TLS |
| **Persistencia Autorizada** | `src/station_database.py` | `StationDatabase` | SQLite en modo WAL: chat, sesiones, canales y airtime |
| **Servidor Web ASGI** | `src/web/asgi_server.py` | `create_asgi_app` | Servidor FastAPI + Uvicorn embebido en el event loop |
| **Despachador REST** | `src/web/api_router.py` | `WebAPIRouter` | Mapeo modular de rutas hacia controladores de negocio |
| **WebSocket Hub** | `src/web/asgi_ws_hub.py` | `WebSocketHub` | Emisión bidireccional reactiva y gestión de conexiones |
| **Autenticación** | `src/web/authentication.py` | `AuthService` | Hasheo PBKDF2, cookies HttpOnly y protección CSRF |

---

## 5. Esquema Canónico de Base de Datos SQLite (`meshcore.sqlite3`)

El backend de persistencia (`src/station_database.py`, [ADR 0017](adr/0017-sqlite-station-browser-cache.md)) opera en modo WAL (`synchronous=FULL`):

```sql
-- Historial completo de mensajería (Canales y DMs)
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT UNIQUE NOT NULL,
    seq INTEGER NOT NULL,
    station_id TEXT NOT NULL,
    feed_key TEXT NOT NULL,           -- 'ch_0', 'dm_<pubkey_64>'
    direction TEXT NOT NULL,          -- 'incoming', 'outgoing'
    sender_pubkey TEXT NOT NULL,
    recipient_pubkey TEXT,
    text TEXT NOT NULL,
    timestamp INTEGER NOT NULL,       -- Epoch en segundos
    delivery_state TEXT NOT NULL,     -- 'pending', 'sent', 'delivered', 'failed'
    ack_timestamp INTEGER,
    source TEXT NOT NULL              -- 'radio', 'web', 'mqtt', 'browser_import'
);

-- Estado de conversaciones
CREATE TABLE conversations (
    feed_key TEXT PRIMARY KEY,
    last_msg_id TEXT NOT NULL,
    unread_count INTEGER DEFAULT 0,
    updated_at INTEGER NOT NULL
);

-- Documentos de configuración y estado sincronizado
CREATE TABLE station_documents (
    domain TEXT PRIMARY KEY,          -- 'node_registry', 'channels', 'airtime_history', 'services_config'
    document_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

-- Autenticación y credenciales de estación
CREATE TABLE station_auth (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    requires_initial_setup INTEGER DEFAULT 1,
    updated_at INTEGER NOT NULL
);
```

---

## 6. Antipatrones Prohibidos para Modelos de IA

1. **`ERROR` Asignar chat a un repetidor**:  
   Generar interfaz de mensajería, botones de envío o DMs hacia un nodo con rol `REPEATER`.
2. **`ERROR` Operaciones de base de datos síncronas en corrutinas**:  
   Invocar directamente `self.db.execute()` dentro de una función `async def` sin delegar en `asyncio.to_thread()`.
3. **`ERROR` Confundir estado `sent` con `delivered`**:  
   `sent` confirma únicamente la transmisión local del paquete por la radio. `delivered` requiere confirmación de ACK correlacionada por radio.
4. **`ERROR` Modificar archivos en `/reference/`**:  
   El directorio `/reference/` contiene clones de sólo lectura de los repositorios oficiales. **NUNCA** editar ni escribir en `/reference/`.
5. **`ERROR` Guardar timers exclusivamente en variables de clase**:  
   Si una tarea programada maneja un cooldown o intervalo de seguridad, debe guardar el último timestamp en disco o base de datos.
6. **`ERROR` Introducir frameworks JS pesados en frontend**:  
   El frontend es estrictamente **Vanilla JavaScript (ESM)**, **Bootstrap 5.3** y **Vanilla CSS**. No usar React, Vue, Svelte ni Tailwind.
7. **`ERROR` Almacenar contraseñas o tokens en LocalStorage**:  
   La autenticación web se basa exclusivamente en cookies HttpOnly y tokens CSRF en memoria.
8. **`ERROR` Volcar archivos de propuestas en la raíz**:  
   Todo documento de análisis pertenece a `docs/audits/` (con prefijo de fecha) o `docs/plans/`. La raíz se reserva para el SSoT y puntos de entrada.
