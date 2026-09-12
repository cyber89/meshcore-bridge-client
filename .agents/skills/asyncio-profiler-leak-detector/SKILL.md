---
name: asyncio-profiler-leak-detector
description: >-
  Profiler de concurrencia asyncio, diagnóstico de latencia en event loop, detección de corutinas
  huérfanas y fugas de memoria con tracemalloc para garantizar estabilidad 24/7 en SBCs embebidos.
---

# Asyncio Profiler & Memory Leak Detector Skill

Esta skill proporciona herramientas de diagnóstico no invasivas para supervisar el rendimiento en tiempo de ejecución, la salud de las tareas asíncronas y el consumo de memoria en **MeshCore Bridge**.

---

## 1. Capacidades de Diagnóstico

1. **Detección de Bloqueos en el Event Loop**:
   - Monitorea el retardo (*lag*) del bucle de eventos `asyncio`.
   - Alerta si alguna llamada de I/O síncrona o procesamiento denso supera el umbral crítico (> 20ms).
2. **Auditoría de Tareas en Segundo Plano (`Task Leak Detection`)**:
   - Inspecciona `asyncio.all_tasks()`.
   - Detecta corutinas huérfanas creadas con `asyncio.create_task()` que no retienen referencia o carecen de manejador de excepciones (*unhandled exceptions*).
3. **Perfilado de Memoria Diferencial (`tracemalloc`)**:
   - Captura snapshots de asignación de memoria RAM antes y después de ciclos de procesamiento.
   - Identifica líneas de código exactas donde se acumulan buffers o referencias no liberadas.

---

## 2. Ejecución del Diagnóstico

Para ejecutar un análisis de salud de concurrencia:

```bash
# Diagnóstico rápido de event loop y memoria
python .agents/skills/asyncio-profiler-leak-detector/scripts/profile_async_health.py --duration 5

# Análisis con simulación de carga concurrente
python .agents/skills/asyncio-profiler-leak-detector/scripts/profile_async_health.py --duration 10 --stress
```
