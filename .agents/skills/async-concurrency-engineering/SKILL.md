---
name: async-concurrency-engineering
description: Revisar tareas, locks, backpressure y apagado de MeshCore Bridge sin bloquear asyncio; mantener compatibilidad Python 3.10.
---

# Concurrencia del bridge

Leer [AGENTS.md](../../../AGENTS.md) y el ciclo de vida en
[bridge_core.py](../../../src/bridge_core.py), [sdk_adapter.py](../../../src/serial/sdk_adapter.py)
y [watchdog.py](../../../src/serial/watchdog.py).

- Delegar I/O bloqueante con asyncio.to_thread; escribir JSON temporal y reemplazar
  atómicamente. Atomicidad no equivale a ausencia de bloqueo ni garantiza durabilidad
  ante cualquier corte de energía: verificar flush/fsync donde se requiera.
- Paho usa un hilo de red: entrar al loop mediante call_soon_threadsafe; asyncio.Queue
  no es thread-safe. Evitar asyncio.run dentro de callbacks del servicio.
- Retener tareas propias en colecciones; consumir excepciones, cancelar y esperar
  sólo esas tareas durante stop(). No cancelar globalmente asyncio.all_tasks().
- Definir propietario único de reconexión y comprobar desconexión durante TX,
  fallos de ping y excepción de reconexión con mocks del SDK.
- Acotar colas, manejar QueueFull y resolver futures pendientes en apagado/fallo.
- Python 3.10: usar wait_for/gather y manejo explícito de cancelación. TaskGroup y
  asyncio.timeout requieren 3.11; no introducirlos sin cambiar el mínimo acordado.
- Aplicar el checklist de radio antes de nuevos timers, reintentos o transmisiones.
  No elegir unilateralmente intervalos/capacidades RF.

```bash
python .agents/skills/async-concurrency-engineering/scripts/audit_async_concurrency.py
```

El auditor AST señala patrones; no prueba ausencia de carreras. Ejecutar regresiones
concurrentes sólo bajo la autorización de pruebas establecida en AGENTS.md.
