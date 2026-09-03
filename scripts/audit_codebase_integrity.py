import importlib.util
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

FORBIDDEN_TERMS = [
    "src.store_forward",
    "SQLiteStoreAndForward",
    "StoredMessage",
    "src.ha_discovery",
    "HomeAssistantDiscovery",
    "meshcore_store_forward.db",
]

EXCLUDE_DIRS = {
    "deploy",
    ".git",
    "logs",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".gemini",
    ".venv",
    "venv",
    "env",
}


def scan_source_files():
    findings = []
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith(".py") and f != "audit_codebase_integrity.py":
                p = Path(root) / f
                rel_path = str(p.relative_to(ROOT_DIR)).replace("\\", "/")
                try:
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    for line_num, line in enumerate(lines, 1):
                        for term in FORBIDDEN_TERMS:
                            if term in line:
                                findings.append((rel_path, term, line_num, line.strip()))
                except Exception as e:
                    print(f"Error leyendo {rel_path}: {e}")
    return findings


def test_import_all_modules():
    successes = []
    failures = []

    src_dir = ROOT_DIR / "src"
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f.endswith(".py"):
                p = Path(root) / f
                rel_path = str(p.relative_to(ROOT_DIR)).replace("\\", "/")
                # Construir nombre de modulo python estándar (ej. src.protocol_types)
                parts = p.relative_to(ROOT_DIR).with_suffix("").parts
                mod_name = ".".join(parts)
                try:
                    importlib.import_module(mod_name)
                    successes.append(rel_path)
                except Exception as e:
                    failures.append((rel_path, str(e)))

    root_entry = ROOT_DIR / "meshcore_bridge.py"
    if root_entry.exists():
        try:
            importlib.import_module("meshcore_bridge")
            successes.append("meshcore_bridge.py")
        except Exception as e:
            failures.append(("meshcore_bridge.py", str(e)))

    return successes, failures


def main():
    print("=" * 80)
    print("AUDITORIA EXHAUSTIVA DE CONSISTENCIA Y RESILIENCIA")
    print("=" * 80)

    print("\n[PASO 1] Escaneando archivos en busca de referencias a componentes eliminados...")
    findings = scan_source_files()

    import_critical_findings = [f for f in findings if f[0].startswith("src/") or f[0] == "meshcore_bridge.py" or f[0] == "config.py"]
    non_critical_findings = [f for f in findings if f not in import_critical_findings]

    if import_critical_findings:
        print(f"ERROR: Se encontraron {len(import_critical_findings)} referencias en codigo de produccion:")
        for rel_path, term, line_num, line in import_critical_findings:
            print(f"  * {rel_path}:{line_num} -> [{term}] {line}")
    else:
        print("OK: CERO referencias a modulos eliminados en codigo de produccion (/src/, meshcore_bridge.py, config.py).")

    if non_critical_findings:
        print(f"\nReferencias en tests o skills encontradas: {len(non_critical_findings)}")
        for rel_path, term, line_num, line in non_critical_findings:
            print(f"  * {rel_path}:{line_num} -> [{term}]")

    print("\n[PASO 2] Probando importacion dinamica de cada modulo de produccion...")
    successes, failures = test_import_all_modules()

    print(f"OK: Modulos importados exitosamente: {len(successes)}")
    for s in successes:
        print(f"  OK: {s}")

    if failures:
        print(f"\nFALLOS DE IMPORTACION ({len(failures)}):")
        for rel_path, err in failures:
            print(f"  ERROR: {rel_path}: {err}")
        return 1
    else:
        print("\n100% DE MODULOS DE PRODUCCION IMPORTADOS SIN ERRORES")

    return 0 if not import_critical_findings and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
