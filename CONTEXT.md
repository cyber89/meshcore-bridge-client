# MeshCore Bridge - CONTEXT.md (Lenguaje Ubicuo y Modelo de Dominio)

Este documento define el **Lenguaje Ubicuo (Ubiquitous Language)** y el **Modelo de Dominio** de **MeshCore Bridge**. Todos los agentes de IA, desarrolladores y módulos de software deben utilizar estos términos con precisión matemática y sin ambigüedades.

---

## 1. Propósito y Arquitectura General del Sistema

- **MeshCore Bridge**: Aplicación asíncrona en Python 3.10+ que actúa como pasarela bidireccional determinista entre una red de malla LoRa (basada en el protocolo y firmware oficial de MeshCore) y redes IP (WebSockets, REST API y MQTT para automatización con n8n/Node-RED).
- **Base Station (Estación Base / Nodo Local)**: Transceptor MeshCore Companion conectado al host por USB/UART o mediante TCP al Companion remoto. Su identidad es la clave pública local.
- **Enrutamiento de Eventos**: `RxEventRouter` distribuye eventos SDK o tramas raw propias entre handlers; MQTT/WebSocket reciben eventos normalizados. El frontend tiene su propio `EventBus` JavaScript. La cola TX usa `asyncio.PriorityQueue`.

---

## 2. Clasificación y Roles Canónicos de Nodos (SSoT MeshCore)

La clasificación canónica de dispositivos se determina mediante el campo de tipo de advert `FirmwareAdvertType` del firmware MeshCore (`reference/meshcore/src/helpers/AdvertDataHelpers.h`, `src/protocol_types.py`). Un nombre o alias no demuestra el rol.

| Rol | Opcode `FirmwareAdvertType` | Descripción y Capacidades |
|---|---|---|
| **`CLIENT`** | `NONE (0)` o `CHAT (1)` | Dispositivo de usuario final. Posee interfaz de chat, envía y recibe mensajería broadcast por canales públicos/privados y mensajes directos (DM). Aparece en la libreta de **Contactos** (`#tab-contacts`). |
| **`REPEATER`** | `REPEATER (2)` | Nodo de infraestructura de red (router/repetidor LoRa en torre o sitio elevado). Reenvía paquetes en la malla. **No posee interfaz de usuario ni procesa texto**. Gestionado exclusivamente por `RepeaterManager` (`🎛️ Administrar`, pings, telemetría, traceroutes). |
| **`ROOM`** | `ROOM (3)` | Servidor comunitario / BBS (Bulletin Board System) que almacena y reenvía mensajes o temas grupales. |
| **`SENSOR`** | `SENSOR (4)` | Nodo de telemetría autónomo (temperatura, batería, ambiental). Emite lecturas periódicas unidireccionales. |
| **`LOCAL`** | *N/A (Identidad del Host)* | La propia estación base conectada por puerto serie. Posee su propio par de claves criptográficas y no debe duplicarse como vecino. |

---

## 3. Restricciones Inmutables de Dominio (Reglas SSoT)

1. **Aislamiento Estricto de Repetidores (`REPEATER`)**:
   - **Prohibición de Contacto**: Un repetidor **NUNCA** debe registrarse en la lista de Contactos (`NodeRegistry.list_client_contacts()`). Pertenece única y exclusivamente a la vista unificada de **Nodos** (`#unifiedNodesGridUi`) y a la **Analítica**.
   - **Prohibición de Chat**: Está terminantemente prohibido despachar mensajes de chat (canales o DM) hacia un repetidor. Su canal de control es estrictamente administrativo (administración, ping y traceroute mediante los ejecutores del bridge y comandos SDK; no son opcodes `CMD_ADMIN`, `CMD_PING_NODE` o `CMD_TRACEROUTE` oficiales).
2. **Aislamiento del Nodo Local (`LOCAL`)**:
   - La estación base no debe añadirse a la libreta de contactos.
   - Prohibido el bucle local: nunca enviar mensajes dirigidos a la clave pública de la propia estación base.
3. **Protección de Airtime LoRa (Checklist Obligatorio)**:
   - LoRa es un medio **half-duplex, compartido y de bajo ancho de banda**.
   - Toda funcionalidad que emita tramas por radio debe responder: ¿Cuánto airtime consume? ¿Puede generar spam o bucles de feedback? ¿Un guardado de configuración rearma un timer en memoria?
   - Preferir siempre la **escucha pasiva** sobre la consulta activa.

---

## 4. Terminología de Radiofrecuencia y Framing Binario

- **Airtime**: Tiempo en milisegundos durante el cual la portadora de radio está ocupada transmitiendo un paquete LoRa (depende de Spreading Factor, Bandwidth y longitud del payload).
- **Hop Count / Path Length**: Métrica de recorrido obtenida del evento SDK o del formato de ruta del firmware. No implica un TTL universal ni un máximo fijo de siete saltos; interpretar su representación según el protocolo oficial.
- **Duty Cycle**: Proporción de tiempo de transmisión acumulado en una ventana. `AirtimeTracker` calcula una estimación y la compara con el límite configurado; ese valor no certifica cumplimiento regulatorio.
- **Framing Companion**: Transporte oficial con marcador `<` para comandos, `>` para respuestas, longitud `uint16` little-endian y payload.
- **Byte Stuffing Raw Propio**: Formato interno del bridge con inicio `0xAA`, fin `0x55`, escape `0x1B` y XOR `0x20`, definido por `MeshcoreFrame`. Su CRC-16 no debe atribuirse al transporte Companion oficial ni a todos los paquetes RF.
- **LQI (Link Quality Indicator)**: Métrica del bridge calculada a partir de RSSI, SNR y saltos, con suavizado EMA y decaimiento temporal (`src/lqi_engine.py`). No calcula tasa de pérdida ni acredita calidad bidireccional.
- **Deduplication Window**: Búfer temporal (LRU con caducidad en segundos) que descarta tramas idénticas retransmitidas por repetidores vecinos.

---

## 5. Módulos Clave del Sistema y Principios de Diseño

El sistema sigue la filosofía de **Deep Modules** (John Ousterhout, *A Philosophy of Software Design*): módulos con una interfaz diminuta y simple que encapsulan gran cantidad de lógica determinista.

- **`BaseSerialAdapter` (Seam)**: Costura o interfaz abstracta que desacopla la lógica del bridge del driver de hardware serie o SDK.
- **`MeshcoreSDKAdapter`**: Adaptador concreto que envuelve el SDK oficial de MeshCore para comunicación con el chip LoRa.
- **`MeshCoreBridge`**: Módulo profundo que orquesta el ciclo de vida del servicio, backpressure de colas y apagado ordenado (*graceful shutdown*).
- **`RawSerialFramingAdapter`**: Parser en memoria del framing propio del bridge con validación de CRC y longitud; actualmente no abre un puerto físico ni transmite por UART.
- **`NodeRegistry`**: Módulo profundo para indexación rápida por clave pública y alias, persistencia y filtrado de contactos vs nodos de infraestructura.
- **`RepeaterManager`**: Gestor de comandos administrativos remotos con control de cooldowns y deduplicación de respuestas.
- **`TxRateLimiter`**: Cola de prioridades y worker con espaciado y estimador de airtime. Puede descartar elementos `LOW` cuando el duty cycle estimado es crítico; no es Token Bucket ni bloqueo absoluto de todo TX.
- **`PacketDeduplicator`**: Filtro de idempotencia para eventos entrantes y salientes.
- **`AsyncBridgeMQTTClient`**: Conector asíncrono MQTT con soporte LWT (*Last Will and Testament*) y reconexión automática.
- **`MeshCoreWebServer`**: Servidor HTTP 1.1 y WebSocket con `asyncio.start_server`, API key opcional y difusión de eventos; no es una aplicación ASGI.

---

## 6. Principios de Vocabulario de Código (Deep Modules Vocabulary)

Al diseñar o refactorizar cualquier módulo del bridge, utilizar estos conceptos:

1. **Módulo (Module)**: Clase, función o paquete con una interfaz pública y una implementación interna.
2. **Interfaz (Interface)**: Todo lo que el llamador necesita saber: tipos, invariantes, excepciones y precondiciones. Debe mantenerse lo más pequeña posible.
3. **Implementación (Implementation)**: El código interno protegido dentro del módulo.
4. **Profundidad (Depth)**: Grado de apalancamiento: mucha funcionalidad resuelta tras una interfaz mínima. (Opuesto: *Shallow Module*, módulos delgados donde la interfaz es casi tan compleja como lo que hacen).
5. **Costura (Seam)**: Lugar donde se puede cambiar o interceptar el comportamiento sin editar el código del llamador (ej. inyección de adaptadores serie o mocks de radio).
6. **Apalancamiento (Leverage)**: Retorno de inversión para los llamadores: aprender 2 métodos públicos para obtener un subsistema completo y robusto.
7. **Localidad (Locality)**: Garantía de que los cambios, bugs y estado residen en un solo archivo en vez de dispersarse por el sistema.

## 7. Persistencia y autoridad documental

Registro de nodos, canales e historial de airtime usan JSON. Los contactos también se sincronizan con la radio. `PacketBuffer` y deduplicación viven en RAM; el historial del navegador usa IndexedDB. No hay backend SQLite para estos datos ni cola MQTT durable en disco; el servicio cartográfico puede leer SQLite MBTiles.

Las reglas anteriores expresan invariantes de dominio, no una certificación de toda la implementación. El [índice documental](docs/README.md) distingue guías vigentes, contratos, ADRs e informes históricos.
