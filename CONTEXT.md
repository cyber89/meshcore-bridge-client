# MeshCore Bridge - CONTEXT.md (Lenguaje Ubicuo y Modelo de Dominio)

Este documento define el **Lenguaje Ubicuo (Ubiquitous Language)** y el **Modelo de Dominio** de **MeshCore Bridge**. Todos los agentes de IA, desarrolladores y módulos de software deben utilizar estos términos con precisión matemática y sin ambigüedades.

---

## 1. Propósito y Arquitectura General del Sistema

- **MeshCore Bridge**: Aplicación asíncrona en Python 3.10+ que actúa como pasarela bidireccional determinista entre una red de malla LoRa (basada en el protocolo y firmware oficial de MeshCore) y redes IP (WebSockets, REST API y MQTT para automatización con n8n/Node-RED).
- **Base Station (Estación Base / Nodo Local)**: Dispositivo transceptor de radio LoRa conectado físicamente por puerto serie (USB/UART) al host que ejecuta el bridge.
- **Event Bus (Bus Asíncrono de Eventos)**: Cola interna basada en `asyncio.Queue` para distribuir tramas recibidas, eventos de telemetría y cambios de estado sin bloquear el event loop.

---

## 2. Clasificación y Roles Canónicos de Nodos (SSoT MeshCore)

La clasificación de cualquier dispositivo en la red se determina **exclusivamente** mediante el opcode binario `FirmwareAdvertType` del firmware MeshCore (`reference/meshcore/AdvertDataHelpers.h`, `src/protocol_types.py`):

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
   - **Prohibición de Chat**: Está terminantemente prohibido despachar mensajes de chat (canales o DM) hacia un repetidor. Su canal de control es estrictamente administrativo (`CMD_ADMIN`, `CMD_PING_NODE`, `CMD_TRACEROUTE`).
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
- **Hop Limit**: Contador de saltos de un paquete dentro de la malla para evitar bucles infinitos (valor estándar: 3–4, máximo: 7). Cada salto decrementa el contador.
- **Duty Cycle**: Límite regulatorio regional (ej. sub-bandas de 868 MHz al 1% o 10%) que restringe el tiempo acumulado de transmisión por hora.
- **Byte Stuffing**: Técnica de delimitación de tramas serie (UART) utilizando bytes especiales de inicio (`SOF` / `0xAA 0x55`) y fin (`EOF`), con secuencias de escape para evitar colisiones con datos binarios arbitrarios.
- **LQI (Link Quality Indicator)**: Métrica compuesta calculada a partir de RSSI, SNR y tasa de pérdida de paquetes para estimar la calidad de enlace entre dos nodos.
- **Deduplication Window**: Búfer temporal (LRU con caducidad en segundos) que descarta tramas idénticas retransmitidas por repetidores vecinos.

---

## 5. Módulos Clave del Sistema y Principios de Diseño

El sistema sigue la filosofía de **Deep Modules** (John Ousterhout, *A Philosophy of Software Design*): módulos con una interfaz diminuta y simple que encapsulan gran cantidad de lógica determinista.

- **`BaseSerialAdapter` (Seam)**: Costura o interfaz abstracta que desacopla la lógica del bridge del driver de hardware serie o SDK.
- **`MeshcoreSDKAdapter`**: Adaptador concreto que envuelve el SDK oficial de MeshCore para comunicación con el chip LoRa.
- **`MeshCoreBridge`**: Módulo profundo que orquesta el ciclo de vida del servicio, backpressure de colas y apagado ordenado (*graceful shutdown*).
- **`PacketParser`**: Deserializador y decodificador binario de tramas MeshCore con validación estricta de CRC y longitud.
- **`NodeRegistry`**: Módulo profundo para indexación rápida por clave pública y alias, persistencia y filtrado de contactos vs nodos de infraestructura.
- **`RepeaterManager`**: Gestor de comandos administrativos remotos con control de cooldowns y deduplicación de respuestas.
- **`RateLimiter`**: Limitador de tasa con algoritmo Token Bucket para proteger el canal de radio contra ráfagas no autorizadas.
- **`MessageDeduplicator`**: Filtro de idempotencia para eventos entrantes y salientes.
- **`MqttSubsystem`**: Conector asíncrono MQTT con soporte LWT (*Last Will and Testament*) y reconexión automática.
- **`HttpServer / WebSocketServer`**: Servidor ASGI nativo ligero en Vanilla Python con autenticación de sesión y difusión de eventos en tiempo real.

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
