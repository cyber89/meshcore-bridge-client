# ADR 0022: Aislamiento de Consumidores y Admisión Acotada en Ingesta de Eventos

- **Estado**: Aceptado
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Fase F2 del Plan de Evolución `nuevo.md`, `src/bridge_core.py`, `src/rx_router.py`, `src/web/asgi_ws_hub.py`, `src/mqtt_client.py`, `src/external_mqtt_client.py`

---

## Contexto y Problema

En la arquitectura previa de recepción LoRa (hallazgos H4 y H5 en `nuevo.md`):
1. **Competencia de Recursos en RX (H4)**: Tareas diagnósticas, logs detallados y retransmisiones TCP compartían la misma cola de trabajo que la recepción de paquetes de chat (`rx_router._enqueue_work`). Si la cola se saturaba (capacidad 256), paquetes legítimos de radio LoRa eran descartados antes de persistirse.
2. **Acoplamiento de Persistencia y Salidas Volátiles (H5)**: En `src/bridge_core.py`, tras persistir un mensaje en SQLite, el worker esperaba síncronamente la entrega hacia los clientes WebSocket en `AsgiWsHub`. Clientes lentos o timeouts de entrega (hasta 2.0s por peer) retrasaban la ruta de persistencia y bloqueaban trabajadores RX/TX.
3. **Falta de Control de Admisión Inter-Hilos**: En los clientes MQTT (local y externo), las llamadas `call_soon_threadsafe` desde los hilos de red de Paho se ejecutaban sin contadores de reserva atómicos, exponiendo el event loop a desbordamientos no acotados bajo ráfagas masivas.

## Factores de Decisión

1. **Prioridad Absoluta de Durabilidad**: Una vez que un paquete LoRa es validado y admitido por el bridge, su persistencia en SQLite debe completarse independientemente del estado de la red IP o de la velocidad de los navegadores web conectados.
2. **Desacoplamiento Total de Salidas**: Un fallo de conexión con el broker MQTT o un navegador móvil congelado nunca debe provocar pérdida de paquetes LoRa ni retrasos en el transceptor.
3. **Control Estricto de Memoria y Concurrencia**: Cada consumidor posee un buffer acotado con política de descarte explícita (descarte de broadcasts volátiles antiguos ante saturación, preservación estricta de tramas RF). La persistencia en SQLite se serializa mediante semáforo para respetar el modelo monohilo escritor de SQLite WAL.

## Decisión Adoptada (Fase F2)

1. **Separación Estricta de Colas de Recepción (F2.1 - Fix H4)**:
   - `rx_router._pending_rx` queda reservada **exclusivamente** para el procesamiento de tramas RF legítimas (`MeshcoreFrame` y eventos decodificados de la radio).
   - Tareas auxiliares de broadcast (`_broadcast_system_log`, tramas crudas TCP Companion, alertas de ciclo de trabajo y corte de airtime) se despachan a través de una cola de background auxiliar desacoplada (`_bg_queue`, capacidad 256) con trabajadores propios (`_bg_workers`) en `bridge_core.py`.
   - `_spawn_broadcast_task` en `rx_router.py` enruta notificaciones de UI hacia la cola auxiliar del bridge en lugar de reinyectarlas en `_enqueue_work`.

2. **Persistencia No Bloqueante del Fanout (F2.2 - Fix H5)**:
   - En `bridge_core.py:publish_chat_event`, la persistencia en base de datos SQLite se ejecuta primero mediante `_persist`.
   - Una vez confirmado el commit en SQLite, la notificación WebSocket se programa como emisión en segundo plano no bloqueante (`self._schedule_background(lambda: web.broadcast_event(payload))`). La función retorna inmediatamente el payload persistido con su ID y secuencia asignados.
   - En `bridge_core.py:_persist`, se introduce `_persist_semaphore = asyncio.Semaphore(1)` para serializar las escrituras a disco fuera del loop con `to_thread`, evitando saturación del thread pool y bloqueos de contención en WAL.

3. **Admisión Acotada y Thread-Safe antes de `call_soon_threadsafe` (F2.3)**:
   - Se implementan contadores atómicos protegidos por cerrojo (`threading.Lock`) en `AsyncBridgeMQTTClient` y `ExternalBridgeMQTTClient` con un límite estricto de 256 callbacks pendientes.
   - Si el búfer entre hilos se satura, el mensaje entrante se rechaza y se registra como desbordamiento medido (`[MQTT-INGRESS-OVERFLOW]`), liberando el contador en el bloque `finally` al ejecutarse o cancelarse.

4. **Ciclo de Apagado Ordenado con Deadline Global Monotónico (F2.4)**:
   - El método `MeshCoreBridge.stop(timeout=5.0)` calcula un deadline monotónico absoluto y asigna a cada fase una porción de presupuesto acotada (`remaining_budget`):
     1. Cerrar admisión externa (MQTT dispatcher y Watchdog serial).
     2. Detener nuevas notificaciones y vaciar colas de difusión auxiliar (`_bg_queue`).
     3. Detener admisión TX en `rate_limiter` y cancelar solicitudes no transmitidas.
     4. Drenar trabajos aceptados en `rx_router` y completar escrituras SQLite pendientes protegidas con `asyncio.shield`.
     5. Detener servicios de red (`services_manager`, `tcp_server`, `web_server`, `serial_adapter`) y liberar recursos.

## Consecuencias

- **Positivas**:
  - Resiliencia máxima: la radio LoRa y la persistencia local operan a velocidad nominal aún bajo tormentas de tráfico WebSockets o caídas de red IP.
  - La cola RF de `rx_router` queda protegida contra saturación por ráfagas de logs o sniffer.
  - El apagado del bridge es determinista y no deja hilos escritores o tareas huérfanas bloqueadas.
- **Negativas / Compensaciones**:
  - Tareas volátiles de log o sniffer pueden descartarse si los clientes WebSockets no consumen al ritmo de generación, preservando la estabilidad del sistema.
