---
name: software-architecture-patterns
description: >-
  Estándares y directrices para Arquitectura Hexagonal (Ports & Adapters), Arquitectura Dirigida
  por Eventos (EDA), Domain-Driven Design (DDD), State Machines y Patrones de Resiliencia
  (Circuit Breaker, Exponential Backoff, Bulkhead, Fallback).
---

# Software Architecture Patterns Skill

Esta skill define los lineamientos arquitectónicos de nivel enterprise para sistemas asíncronos y distribuidos como MeshCore Bridge.

---

## 1. Arquitectura Hexagonal (Ports & Adapters)

```
+-------------------------------------------------------------------+
|                        Adaptadores Primarios                      |
|  [REST API / FastAPI]  [WebSockets]  [TCP Companion]  [CLI/Admin] |
+---------------------------------+---------------------------------+
                                  |
                                  v
+---------------------------------+---------------------------------+
|                       Puertos de Entrada                          |
|    - IBridgeController (start, stop, enqueue_tx, get_status)      |
|    - ICompanionProtocol (handle_frame, send_response)             |
+---------------------------------+---------------------------------+
                                  |
                                  v
+---------------------------------+---------------------------------+
|                         Núcleo de Dominio                         |
|   - MeshCoreBridge (Orquestación del ciclo de vida)              |
|   - RxEventRouter (Enrutamiento de eventos por opcode)            |
|   - ContactManager (Identidades y claves públicas)                |
|   - AdminCommandHandler (Comandos de configuración RF)            |
+---------------------------------+---------------------------------+
                                  |
                                  v
+---------------------------------+---------------------------------+
|                       Puertos de Salida                           |
|    - ISerialAdapter (send_raw_packet, read_stream, set_callbacks) |
|    - IStoreForward (save_packet, get_pending, mark_delivered)     |
|    - IMqttPublisher (publish_event, publish_telemetry)            |
+---------------------------------+---------------------------------+
                                  |
                                  v
+---------------------------------+---------------------------------+
|                       Adaptadores Secundarios                     |
|  [pyserial-asyncio]  [VirtualMeshAdapter]  [SQLite WAL]  [MQTT]   |
+-------------------------------------------------------------------+
```

### Reglas de Dependencia:
1. Las capas internas (Núcleo) **NUNCA** deben importar de capas externas (Adaptadores de UI, red o BD).
2. La comunicación entre el Núcleo y el exterior se realiza exclusivamente a través de interfaces (`typing.Protocol` o `abc.ABC`).
3. El dominio es 100% testeable sin requerir hardware físico, red ni base de datos real (usando adaptadores virtuales y mocks).

---

## 2. Arquitectura Dirigida por Eventos (EDA) & Pub/Sub

1. **Desacoplamiento Temporal**: El emisor de un evento no conoce ni espera la finalización de los consumidores.
2. **Eventos Inmutables**: Todos los eventos del dominio se modelan como `@dataclass(frozen=True, slots=True)`.
3. **Múltiples Suscriptores Asíncronos**:
   * Evento `RxPacketReceived` $\to$ Consumido simultáneamente por:
     * `StoreForward` (persistencia en SQLite).
     * `MqttBridge` (publicación hacia Home Assistant / n8n).
     * `WebSocketHub` (actualización reactiva de la SPA).
     * `TCPCompanionServer` (reenvío a apps móviles conectadas).

---

## 3. Patrones de Resiliencia y Tolerancia a Fallos

1. **Circuit Breaker (Cortocircuito)**:
   * Estados: `CLOSED` (normal), `OPEN` (fallando, no enviar peticiones), `HALF-OPEN` (prueba de recuperación).
   * Aplica a: Conexiones serie USB, brokers MQTT remotos y APIs REST externas.
2. **Exponential Backoff con Jitter**:
   * Tiempo de espera ante reintentos: $T = \min(T_{max}, T_{base} \times 2^{retry}) \pm \text{uniform}(0, \text{jitter})$.
   * Evita el efecto «thundering herd» sobre transceptores o brokers.
3. **Bulkhead (Aislamiento de Recursos)**:
   * Aislar colas de procesamiento para que la congestión de un canal (ej. broadcast masivo) no bloquee los mensajes directos prioritarios ni las respuestas administrativas.
4. **Graceful Degradation / Store & Forward**:
   * Si la radio LoRa o la red se desconecta, los mensajes se encolan de forma persistente en SQLite WAL y se reintentan automáticamente al restaurar el enlace.

---

## 4. Script de Auditoría Arquitectónica

```bash
python .agents/skills/software-architecture-patterns/scripts/audit_architecture.py
```
