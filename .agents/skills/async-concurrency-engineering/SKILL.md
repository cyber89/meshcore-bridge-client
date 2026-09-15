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
3. **Persistencia Atómica y Segura**:
   * Las operaciones de escritura en disco (archivos JSON de canales/configuración) deben realizarse de forma atómica (escritura en temporal + renombre atómico) o mediante corrutinas sin bloquear el event loop.

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

## 3. Manejo de Excepciones y Retención de Referencias de Tareas

1. **Retención de Referencias contra Garbage Collection**:
   - `asyncio.create_task()` crea referencias débiles internamente en el loop. Si la tarea no se referencia en una colección del contexto (`self._background_tasks.add(task)`), el Garbage Collector de Python puede destruirla prematuramente.
   - **Patrón Obligatorio**:
     ```python
     task = loop.create_task(coro)
     self._background_tasks.add(task)
     task.add_done_callback(self._background_tasks.discard)
     ```

2. **Concurrencia Estructurada (Python 3.11+ TaskGroup)**:
   - Para operaciones concurrentes con ciclo de vida acotado, preferir `asyncio.TaskGroup()` sobre `asyncio.gather()`. Si una sub-corrutina falla, las demás se cancelan automáticamente y se agrupan en un `ExceptionGroup`.
   ```python
   async with asyncio.TaskGroup() as tg:
       t1 = tg.create_task(query_node(node_a))
       t2 = tg.create_task(query_node(node_b))
   ```

3. **Timeouts Canónicos con `asyncio.timeout`**:
   - Usar el context manager nativo `async with asyncio.timeout(seconds):` en lugar de `asyncio.wait_for()`, permitiendo una cancelación más limpia y evitando pérdidas de contexto.

4. **Contrapresión (Backpressure) con Colas Acotadas**:
   - **Prohibido**: `asyncio.Queue()` sin límite máximo de capacidad (`maxsize=0`) en productores no controlados (como tráfico RF o mensajes MQTT).
   - **Solución**: Fijar siempre un `maxsize` prudente (ej. 200 a 1000 items) y manejar `asyncio.QueueFull` con descarte controlado de tramas de baja prioridad o señalización de contrapresión.

---

## 4. Herramientas de Verificación

```bash
python .agents/skills/async-concurrency-engineering/scripts/audit_async_concurrency.py
python .agents/skills/asyncio-profiler-leak-detector/scripts/profile_async_health.py
```

