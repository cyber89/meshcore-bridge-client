"""
Script de Compilacion y Validacion de Diagramas de Arquitectura con Archify
MeshCore Bridge v3.0
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIFY_BIN_LOCAL = ROOT / ".agents" / "skills" / "archify" / "bin" / "archify.mjs"
ARCHIFY_BIN_GLOBAL = Path.home() / ".agents" / "skills" / "archify" / "bin" / "archify.mjs"

DIAGRAMS = [
    {
        "type": "architecture",
        "json": ROOT / "docs" / "diagrams" / "meshcore_architecture.json",
        "html": ROOT / "docs" / "diagrams" / "meshcore_architecture.html",
        "label": "Arquitectura General del Sistema",
    },
    {
        "type": "workflow",
        "json": ROOT / "docs" / "diagrams" / "meshcore_packet_pipeline.json",
        "html": ROOT / "docs" / "diagrams" / "meshcore_packet_pipeline.html",
        "label": "Pipeline de Tramas LoRa a IP",
    },
    {
        "type": "sequence",
        "json": ROOT / "docs" / "diagrams" / "meshcore_rx_tx_sequence.json",
        "html": ROOT / "docs" / "diagrams" / "meshcore_rx_tx_sequence.html",
        "label": "Secuencia Operativa RF y Web",
    },
]

def resolve_archify() -> Path:
    if ARCHIFY_BIN_LOCAL.exists():
        return ARCHIFY_BIN_LOCAL
    if ARCHIFY_BIN_GLOBAL.exists():
        return ARCHIFY_BIN_GLOBAL
    print("[ERROR] No se encontro archify.mjs en el proyecto ni en el entorno global.")
    sys.exit(1)

def run_step(cmd: list[str], desc: str) -> bool:
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print(f"[FAIL] {desc}")
        print(res.stderr or res.stdout)
        return False
    print(f"[OK]   {desc}")
    return True

def main():
    archify = resolve_archify()
    print("=" * 70)
    print("MeshCore Bridge - Compilador de Diagramas Interactivos con Archify")
    print(f"Motor Archify: {archify}")
    print("=" * 70)

    all_ok = True
    for item in DIAGRAMS:
        print(f"\n--- {item['label']} ---")
        if not item["json"].exists():
            print(f"[WARN] Archivo no encontrado: {item['json']}")
            continue

        val_cmd = ["node", str(archify), "validate", item["type"], str(item["json"]), "--quality", "showcase", "--json"]
        ok = run_step(val_cmd, f"Validacion Showcase ({item['type']})")
        if not ok:
            all_ok = False
            continue

        del_cmd = ["node", str(archify), "deliver", item["type"], str(item["json"]), str(item["html"]), "--quality", "showcase", "--json"]
        ok = run_step(del_cmd, f"Entrega HTML ({item['html'].name})")
        if ok and item["html"].exists():
            size_kb = item["html"].stat().st_size / 1024.0
            print(f"       -> Artefacto generado: {item['html'].name} [{size_kb:.1f} KB]")
        else:
            all_ok = False

    print("\n" + "=" * 70)
    if all_ok:
        print("[SUCCESS] Todos los diagramas de Archify fueron compilados y verificados.")
    else:
        print("[ERROR] Ocurrieron fallos durante la compilacion.")
        sys.exit(1)

if __name__ == "__main__":
    main()
