# ADR 0022: Aislamiento de Consumidores y Admisión Acotada en Ingesta de Eventos

- **Estado**: Propuesto
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F2 del Plan de Evolución `nuevo.md`, `src/bridge_core.py`, `src/rx_router.py`, `src/web/asgi_ws_hub.py`

---

## Contexto y Problema

En la arquitectura actual de recepción LoRa (hallazgos H4 y H5 en `nuevo.md`):
1. **Competencia de Recursos en RX (H4)**: Tareas diagnósticas, logs detallados y retransmisiones TCP comparten la misma cola de trabajo que la recepción de paquetes de chat (`rx_router._enqueue_work`). Si la cola se satura, paquetes legítimos de chat pueden ser descartados antes de persistirse.
2. **Acoplamiento de Persistencia y Salidas Volátiles (H5)**: En `src/bridge_core.py:179–208`, tras persistir un mensaje en SQLite, el worker espera la entrega hacia los clientes WebSocket en `AsgiWsHub`. Aunque existen timeouts, clientes lentos o brokers MQTT congestionados pueden retrasar el hilo de persistencia o agotar trabajadores.

## Factores de Decisión

1. **Prioridad Absoluta de Durabilidad**: Una vez que un paquete LoRa es validado y admitido por el bridge, su persistencia en SQLite debe completarse independientemente del estado de la red IP o de la velocidad de los navegadores web conectados.
2. **Desacoplamiento de Salidas**: Un fallo de conexión con el broker MQTT o un navegador móvil congelado nunca debe provocar pérdida de datos en la estación base.
3. **Control Estricto de Memoria**: Cada consumidor debe tener un buffer acotado con política de saturación explícita (descarte de frames viejos para clientes lentos, descarte de telemetría repetible, preservación estricta de chat).

## Decisión Propuesta

1. **Admisión Acotada en Ingesta**:
   - Reservar capacidad con contadores atómicos seguros entre hilos antes de programar llamadas `call_soon_threadsafe`.
   - Separar el flujo de ingesta de chat/ACK del flujo de logs y telemetría no crítica.
2. **Persistencia Previa al Fanout**:
   - El ciclo de vida de un mensaje de chat admitido asegura el commit en SQLite antes de notificar a los publicadores de eventos.
   - Si la publicación WebSocket o MQTT falla, el mensaje ya se encuentra seguro en base de datos.
3. **Buffers y Workers Desacoplados por Consumidor**:
   - Cada adaptador de salida (WebSocket Hub, MQTT Publisher, Logger) posee su propia cola limitada.
   - Si un cliente WebSocket se retrasa, su cola individual se desconecta o descarta según su política, sin bloquear el event loop principal ni el pipeline de recepción serie.

## Consecuencias

- **Positivas**:
  - Resiliencia máxima: la radio LoRa y la persistencia local continúan operando a velocidad nominal aún bajo tormentas de tráfico IP o desconexión de brokers.
  - Trazabilidad y contadores claros de descarte por causa y consumidor.
- **Negativas / Compensaciones**:
  - Mayor consumo de buffers en memoria al mantener colas independientes por adaptador.
