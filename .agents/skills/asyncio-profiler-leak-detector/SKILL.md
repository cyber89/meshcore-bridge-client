---
name: asyncio-profiler-leak-detector
description: Medir event-loop lag y asignaciones con tracemalloc en escenarios aislados; distinguir el benchmark sintético del perfilado del servicio real.
---

# Diagnóstico asyncio

Leer [AGENTS.md](../../../AGENTS.md). El helper
[profile_async_health.py](scripts/profile_async_health.py) crea su propio escenario
de medición; no se adjunta al proceso bridge operativo ni demuestra estabilidad 24/7.

```bash
python .agents/skills/asyncio-profiler-leak-detector/scripts/profile_async_health.py --duration 5
python .agents/skills/asyncio-profiler-leak-detector/scripts/profile_async_health.py --duration 10 --stress
```

Ejecutar benchmarks/simulaciones cuando estén autorizados. Para problemas reales,
reproducir con adaptador virtual, comparar snapshots después del drenado de tareas y
separar memoria retenida intencionalmente de crecimiento sostenido. Informar duración,
carga, plataforma y mediciones; no extrapolar a CPU/RAM de un SBC diferente.
Inspeccionar las tareas del componente y sus referencias propias: all_tasks() no
identifica por sí solo tareas huérfanas o una fuga.
