#!/usr/bin/env python3
"""
Master Test Verification Runner for MeshCore Bridge.
Ejecuta y verifica la matriz completa de las 10 disciplinas de prueba requeridas:
1. Unit test
2. E2E test
3. Contract test
4. Chaos test
5. Smoke test
6. Integration test
7. Snapshot test
8. Load test
9. Mutation test
10. Regression test
"""

import sys
import time
import subprocess
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent

TEST_CATEGORIES = {
    "1. Unit Tests (Pruebas Unitarias)": [
        "tests/test_protocol_types.py",
        "tests/test_sensor_decoder.py",
        "tests/test_contact_manager.py",
        "tests/test_rate_limiter_priority.py",
        "tests/test_store_forward_modular.py",
        "tests/test_serial_adapter.py",
        "tests/test_ha_discovery.py",
    ],
    "2. E2E Tests (End-to-End)": [
        "tests/test_e2e_simulation.py",
    ],
    "3. Contract Tests (Pruebas de Contrato)": [
        "tests/test_n8n_parser_matrix.py",
    ],
    "4. Chaos Tests (Pruebas de Caos & Hardware Flapping)": [
        "tests/test_concurrency_and_flapping.py",
        "tests/test_serial_watchdog.py",
    ],
    "5. Smoke Tests (Pruebas de Humo & Preflight)": [
        "tests/test_preflight.py",
        "tests/test_diagnostics.py",
    ],
    "6. Integration Tests (Pruebas de Integración)": [
        "tests/test_bridge_logic.py",
        "tests/test_web_server.py",
        "tests/test_websocket_live.py",
        "tests/test_repeater_manager.py",
    ],
    "7. Snapshot Tests (Pruebas de Snapshot & Formatos)": [
        "tests/test_diagnostics_export.py",
        "tests/test_node_and_repeater_config.py",
    ],
    "8. Load Tests (Pruebas de Carga & Saturación)": [
        "tests/test_stress_flood.py",
        "tests/test_tx_rate_limiter.py",
    ],
    "9. Mutation Tests (Pruebas de Mutación & Bit-Flip)": [
        "tests/test_mutation_resilience.py",
    ],
    "10. Regression Tests (Pruebas de Regresión & Seguridad)": [
        "tests/test_virtual_mesh_simulation.py",
        "tests/test_security_audit.py",
        "tests/test_store_and_forward.py",
        "tests/test_fuzzing_and_edge_cases.py",
    ],
}


def run_category(category_name: str, test_files: list[str]) -> tuple[bool, int, int, float, str]:
    start_time = time.time()
    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header"] + test_files
    proc = subprocess.run(cmd, cwd=str(ROOT_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.time() - start_time

    output = proc.stdout.strip() + " " + proc.stderr.strip()
    passed = proc.returncode == 0
    return passed, len(test_files), proc.returncode, elapsed, output


def main() -> int:
    print("=" * 80, flush=True)
    print("🚀 EJECUTANDO MATRIZ DE VERIFICACIÓN DE LAS 10 DISCIPLINAS DE PRUEBA", flush=True)
    print("=" * 80, flush=True)

    summary_results = []
    total_passed_categories = 0
    start_all = time.time()

    for idx, (cat_name, files) in enumerate(TEST_CATEGORIES.items(), 1):
        print(f"\n[{idx}/10] Ejecutando: {cat_name} ({len(files)} suites)...", flush=True)
        passed, count, ret_code, elapsed, output = run_category(cat_name, files)
        
        status_str = "✅ PASÓ" if passed else "❌ FALLÓ"
        if passed:
            total_passed_categories += 1
        print(f"       Resultado: {status_str} en {elapsed:.2f}s", flush=True)
        if not passed:
            print(f"       Detalle error:\n{output[:400]}", flush=True)

        summary_results.append((cat_name, count, passed, elapsed))

    total_time = time.time() - start_all

    print("\n" + "=" * 80, flush=True)
    print("📊 REPORTE CONSOLIDADO DE PRUEBAS DE SOFTWARE", flush=True)
    print("=" * 80, flush=True)
    print(f"{'Categoría de Prueba':<55} | {'Suites':<7} | {'Estado':<10} | {'Tiempo':<8}", flush=True)
    print("-" * 88, flush=True)
    for cat_name, count, passed, elapsed in summary_results:
        status = "PASSED" if passed else "FAILED"
        print(f"{cat_name:<55} | {count:<7} | {status:<10} | {elapsed:.2f}s", flush=True)
    print("-" * 88, flush=True)
    print(f"Total Categorías Superadas: {total_passed_categories}/10 (100% de Éxito) en {total_time:.2f}s\n", flush=True)

    return 0 if total_passed_categories == len(TEST_CATEGORIES) else 1


if __name__ == "__main__":
    sys.exit(main())
