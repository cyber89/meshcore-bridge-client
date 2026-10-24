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
Nivel 5: Registros de Decisiones de Arquitectura Vigentes (consultar índice docs/README.md; hasta ADR 0024)
   ↓
Nivel 6: Planes de Modernización (docs/plans/)
   ↓
Nivel 7: Historial de Auditorías y Decisiones Sustituidas (docs/audits/, docs/fastapi/)
```

Esta jerarquía organiza autoridad documental: el código determina las capacidades
implementadas y las fuentes oficiales determinan el protocolo. Una propuesta o
una regla normativa no acredita su implementación. Revisión de navegación y
persistencia: 2026-10-24, mediante lectura estática.

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
8. **`MUST NOT` Activar Repetición en Servidores ROOM**:
   El bridge bloquea `set repeat on` para todo rol `ROOM` (`FirmwareAdvertType.ROOM = 3`), también con versiones anteriores o desconocidas. El firmware 1.18 también lo rechaza.
9. **`MUST NOT` Ejecutar Suites de Pruebas Automáticamente**:  
   Está terminantemente prohibido ejecutar `pytest`, Playwright o herramientas de fuzzing salvo que el usuario lo solicite explícitamente en su mensaje.

---

## 3. Matriz Canónica de Clasificación de Dispositivos

Basada estrictamente en la especificación binaria de MeshCore (`AdvertDataHelpers.h`, `FirmwareAdvertType`):

| `FirmwareAdvertType` | Código | Rol Canónico | Capacidades Permitidas | Prohibiciones |
|:---:|:---:|:---:|---|---|
| `NONE` / `CHAT` | `0` / `1` | `CLIENT` | Mensajería de texto (Canal / DM), telemetría, ping | Acceso a comandos admin de repetidor |
| `REPEATER` | `2` | `REPEATER` | Comandos remotos admin, telemetría, traceroute, ping hop 0 | **Chat de texto (DM o broadcast)** |
| `ROOM` | `3` | `ROOM` | BBS, telemetría, administración de sala | **`set repeat on` (bloqueado por el bridge para cualquier versión)** |
| `SENSOR` | `4` | `SENSOR` | Telemetría periódica Cayenne LPP / Custom, suscripciones `0x08`/`0x09` | Mensajería interactiva |
| — | — | `LOCAL` | Estación base host conectada por UART/TCP | **Automensajería (bucle local)** |

---

## 4. Índice de Módulos y Símbolos de Producción

| Dominio / Subsistema | Archivo Principal | Clase / Función Clave | Responsabilidad |
|---|---|---|---|
| **Punto de Entrada** | `meshcore_bridge.py` | `main` | Validación de runtime y arranque |
| **Núcleo Asíncrono** | `src/bridge_core.py` | `MeshCoreBridge` | Composición, inicialización de colas, suscripción a eventos y shutdown |
| **Fachada de Radio** | `src/serial_driver.py` | `BaseSerialAdapter`, `SerialWatchdog` | Reexporta las implementaciones de `src/serial/` |
| **Adaptador SDK** | `src/serial/sdk_adapter.py` | `MeshcoreSDKAdapter` | Enlace con SDK oficial Companion (`meshcore_py`) |
| **Enrutador de Entrada** | `src/rx_router.py` | `RxEventRouter` | Normalización, clasificación por opcode y entrega a handlers |
| **Deduplicador** | `src/deduplicator.py` | `PacketDeduplicator` | Filtrado de duplicados RF mediante ventana deslizante en RAM |
| **Control de Airtime** | `src/rate_limiter.py` | `TxRateLimiter`, `AirtimeTracker` | Estimación de duty cycle frente al límite configurado, espaciado y prioridades TX |
| **Resolución de Destinos** | `src/target_resolver.py` | `TargetResolver` | Mapeo de prefijos, apodos y claves públicas de 64 caracteres |
| **Registro de Nodos** | `src/contact_manager.py` | `NodeRegistry` | Registro de vecinos LoRa, telemetría y libreta de contactos |
| **Calidad de Enlace** | `src/lqi_engine.py` | `LinkQualityEngine` | Estimación de calidad mediante SNR, RSSI y saltos |
| **Gestión de Infraestructura** | `src/repeater_manager.py` | `RepeaterManager` | Envío de comandos remotos y persistencia de cooldowns |
| **Manejador de Sensores** | `src/sensor_decoder.py` | `CayenneLPPDecoder`, `extract_telemetry_fields` | Decodificación CayenneLPP y normalización de telemetría |
| **Cliente MQTT Local** | `src/mqtt_client.py` | `AsyncBridgeMQTTClient` | Conexión Paho MQTT hacia automatizaciones n8n |
| **MQTT Externo** | `src/external_mqtt_client.py` | `ExternalBridgeMQTTClient` | Puente hacia brokers externos con TLS configurable |
| **Persistencia Autorizada** | `src/station_database.py` | `StationDatabase` | SQLite en modo WAL: chat, sesiones, canales y airtime |
| **Servidor Web ASGI** | `src/web/asgi_server.py` | `create_asgi_app` | Servidor FastAPI + Uvicorn embebido en el event loop |
| **Despachador REST** | `src/web/api_router.py` | `WebAPIRouter` | Mapeo modular de rutas hacia controladores de negocio |
| **WebSocket Hub** | `src/web/asgi_ws_hub.py` | `WebSocketHub` | Emisión bidireccional reactiva y gestión de conexiones |
| **Autenticación HTTP** | `src/web/authentication.py` | `AuthenticationService` | Cookies HttpOnly, protección CSRF y autorización HTTP/WebSocket |
| **Credenciales** | `src/web/auth_store.py` | `AuthStore` | Hash scrypt, sesiones/tokens y recuperación local transaccional |
| **Casos de uso** | `src/application/` | `ChannelService`, `MessageService`, `ContactService` | Canales, chat/historial y sincronización de contactos sin depender del adaptador web |
| **Ledger MQTT** | `src/application/command_policy.py` | `CommandLedgerPolicy` | Reserva y resultado en SQLite; aplicación parcial según la ruta del dispatcher |
| **Capacidades** | `src/application/capabilities.py` | `CapabilityRegistry`, `StableMqttPort` | Estado de servicios opcionales y fachada MQTT estable |

---

## 5. Persistencia SQLite implementada (`meshcore.sqlite3`)

El DDL ejecutable reside en `StationDatabase.initialize()`
(`src/station_database.py`, esquema `user_version=2`) y `AuthStore.initialize()`
(`src/web/auth_store.py`). Ambos comparten el archivo de estación; las operaciones
síncronas deben invocarse desde workers cuando el llamador use asyncio.
La estación configura WAL y `synchronous=FULL`.

| Tabla real | Contenido / claves principales |
| --- | --- |
| `metadata` | Pares `key`/`value`; incluye el UUID `station_id`. |
| `documents` | `name`, `payload` JSON, `updated_at`; nombres permitidos: `nodes`, `channels`, `services`, `airtime`, `repeater_cooldowns`. |
| `legacy_imports` | Fuente, digest y fecha de cada dominio JSON importado una vez. |
| `messages` | `seq INTEGER PRIMARY KEY AUTOINCREMENT`, `msg_id UNIQUE`, `feed_key`, `timestamp TEXT`, `direction`, `status`, `expected_ack`, `payload` JSON. |
| `delivery_events` | `event_key` único y payload del evento de entrega. |
| `pending_acks` | `ack_code`, `req_id`, `target`, `timestamp REAL`. |
| `sensor_subscriptions` | Clave pública, `push_tag` único, timeout, deltas LPP, vencimiento y estado de suscripción. |
| `command_ledger` | Reserva por `(station_id, integration_scope, command_id)`, huella, estado y resultado; poda al insertar a 10 000 filas. |
| `auth_owner` | Cuenta única, sal/hash scrypt, cambio obligatorio y generación. |
| `auth_sessions` | Digest, CSRF, vencimiento, recordar sesión y generación. |
| `auth_api_tokens` | Digest del token de integración. |
| `auth_login_attempts` | Contadores persistidos de intentos por peer y globales. |

Las conversaciones se calculan a partir de mensajes; no hay tablas
`conversations`, `station_documents` o `station_auth`. El UUID se guarda en
`metadata`, no en una columna `station_id` de cada fila de `messages`.
Los estados admitidos son `received`, `queued`, `sent`, `failed`, `delivered`;
`sent` no acredita entrega RF. El ledger conserva hasta 10 000 entradas y no
es una cola durable de reintentos. TX (`mqtt`) y ambas rutas de administración
(`mqtt_admin`) detienen toda reserva no admitida, también las que siguen en curso
sin resultado. El ledger usa workers propios; sólo las órdenes sin ID admiten
modo legado. Con ID, ausencia/error de BD o fallo al marcar despacho impide RF. Reserva,
RF y registro de resultado son pasos separados: no hay transacción conjunta ni
garantía global de ejecución exactamente una vez. Véase [STORAGE.md](STORAGE.md).

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
