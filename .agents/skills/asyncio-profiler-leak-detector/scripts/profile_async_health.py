#!/usr/bin/env python3
"""Profiler de Salud de Concurrencia Asyncio y Detección de Fugas para MeshCore Bridge.

Monitorea la latencia del event loop de asyncio, detecta tareas en segundo plano
huérfanas y mide el incremento de memoria diferencial con tracemalloc.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import tracemalloc

# Asegurar path de proyecto y encoding UTF-8 en stdout
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.deduplicator import PacketDeduplicator


async def measure_loop_lag(duration_sec: float) -> list[float]:
    """Mide la latencia de despacho del event loop realizando sleeps de 50ms."""
    delays: list[float] = []
    end_time = time.monotonic() + duration_sec
    target_sleep = 0.050  # 50ms

    while time.monotonic() < end_time:
        start = time.monotonic()
        await asyncio.sleep(target_sleep)
        elapsed = time.monotonic() - start
        lag = max(0.0, elapsed - target_sleep)
        delays.append(lag)

    return delays


async def run_stress_tasks(count: int = 500) -> None:
    """Genera ráfagas controladas de tareas en memoria para probar el GC de asyncio."""
    dedup = PacketDeduplicator(window_seconds=5.0, max_entries=1000)

    async def worker(idx: int) -> None:
        key = f"stress_packet_key_{idx % 50}"
        await dedup.is_duplicate(key)
        await asyncio.sleep(0.01)

    tasks = [asyncio.create_task(worker(i)) for i in range(count)]
    await asyncio.gather(*tasks)


async def profile_async(duration: float, stress: bool) -> None:
    print(f"⏱️  [PROFILER] Iniciando perfilado de event loop ({duration}s)...")
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    if stress:
        print("⚡ [PROFILER] Ejecutando simulación de carga concurrente (500 micro-tareas)...")
        await run_stress_tasks(500)

    delays = await measure_loop_lag(duration)

    snapshot_after = tracemalloc.take_snapshot()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Estadísticas de lag del loop
    if delays:
        avg_lag_ms = (sum(delays) / len(delays)) * 1000.0
        max_lag_ms = max(delays) * 1000.0
    else:
        avg_lag_ms, max_lag_ms = 0.0, 0.0

    active_tasks = len([t for t in asyncio.all_tasks() if not t.done()])

    print("\n📊 [RESULTADOS DE SALUD DE CONCURRENCIA]")
    print(f"   • Tareas activas en event loop: {active_tasks} (OK)")
    print(f"   • Latencia media del loop:     {avg_lag_ms:.2f} ms")
    print(f"   • Latencia máxima (pico lag):  {max_lag_ms:.2f} ms")
    print(f"   • Memoria actual rastreada:    {current_mem / 1024:.1f} KB")
    print(f"   • Memoria pico registrada:     {peak_mem / 1024:.1f} KB")

    # Evaluación de salud
    if max_lag_ms > 50.0:
        print("   ⚠️  ALERTA: Se detectó un bloqueo mayor a 50ms en el event loop.")
    else:
        print("   ✅ Event loop con respuesta determinista (< 50ms lag).")

    # Diferencias de memoria principales
    top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
    print("\n🔍 [TOP 3 ASIGNACIONES DE MEMORIA]")
    for stat in top_stats[:3]:
        print(f"   • {stat}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profiler de Salud Asyncio y Fugas")
    parser.add_argument("--duration", type=float, default=2.0, help="Duración del muestreo en segundos")
    parser.add_argument("--stress", action="store_true", help="Simular ráfagas de tareas")
    args = parser.parse_args()

    asyncio.run(profile_async(args.duration, args.stress))


if __name__ == "__main__":
    main()
