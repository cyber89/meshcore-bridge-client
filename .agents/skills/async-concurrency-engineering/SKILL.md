---
name: async-concurrency-engineering
description: >-
  Estándares avanzados de concurrencia en Python (asyncio nativo, multihilo seguro,
  TaskGroups, backpressure queues, gestión de locks y apagado ordenado graceful shutdown).
---

# Async Concurrency Engineering Skill

Esta skill establece las directrices de ingeniería para garantizar código asíncrono determinista, no bloqueante y libre de condiciones de carrera o bloqueos mutuos (*deadlocks*).

---

## 1. Reglas de Oro en `asyncio`

1. **Cero Llamadas Bloqueantes en el Event Loop**:
   * **Prohibido**: `time.sleep()`, `requests.get()`, operaciones sincrónicas de sockets o I/O de disco bloqueante en corrutinas.
   * **Solución**: Usar `asyncio.sleep()`, `httpx` / `aiohttp`, `aiofiles` o delegar a un hilo mediante `asyncio.to_thread(sync_fn)`.
2. **Puente Seguro entre Hilos y Asyncio**:
   * Si un hilo del SO (ej. callback de pyserial o daemon de fondo) necesita notificar a una corrutina en el event loop, **NUNCA** llamar directamente a corrutinas con `asyncio.run()`.
   * **Solución**: Usar `loop.call_soon_threadsafe(callback, *args)` o encolar en una `asyncio.Queue` protegida.
3. **Persistencia SQLite Concurrente**:
   * Las conexiones SQLite compartidas entre hilos deben protegerse mediante `threading.Lock` o transacciones atómicas con modo WAL activado (`PRAGMA journal_mode=WAL`).

---

## 2. Gestión del Ciclo de Vida y Apagado Ordenado (*Graceful Shutdown*)

```python
async def shutdown(signal_name: str, loop: asyncio.AbstractEventLoop) -> None:
    """Secuencia determinista de apagado seguro."""
    logger.info(f"Iniciando apagado por señal {signal_name}...")
    
    # 1. Detener aceptación de nuevas conexiones (TCP / WebSockets)
    # 2. Drenar colas pendientes de transmisión (Flush TX queues)
    # 3. Cancelar tareas de fondo pendientes
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    
    # 4. Esperar finalización de tareas con timeout
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # 5. Cerrar adaptadores serie, conexiones de base de datos y clientes MQTT
    # 6. Detener el event loop de forma limpia
```

---

## 3. Manejo de Excepciones en Tareas en Segundo Plano

* Cada tarea creada con `asyncio.create_task()` debe contar con manejo de excepciones local (`try/except`) o registrar un callback de finalización con `task.add_done_callback(handle_task_result)` para evitar advertencias de *Task exception was never retrieved*.

---

## 4. Herramientas de Verificación

```bash
python .agents/skills/async-concurrency-engineering/scripts/audit_async_concurrency.py
```
