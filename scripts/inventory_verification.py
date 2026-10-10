"""Inventory project verification files without importing or executing them."""

from __future__ import annotations

import ast
import json
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_REASONS = {
    "audit_codebase_integrity.py": ("auxiliary-static-audit", "Imports src and scans repository including vendor directories; separate from canonical gate."),
    "verify_all_components.py": ("auxiliary-simulation", "Standalone assertions with current config and registry; canonical pytest covers these contracts in isolated fixtures."),
    "validate_all_node_parameters.py": ("auxiliary-simulation", "Manual node parameter matrix uses current config and registry; no pytest fixture isolation."),
    "validate_project_docs.py": ("maintained-documentation-validator", "Run by canonical quality gate; exercised by test_quality_tools.py."),
    "run_quality_checks.py": ("maintained-quality-runner", "Canonical pytest, mypy, ruff and documentation gate; exercised by test_quality_tools.py."),
    "run_all_test_categories.py": ("historical-partial-runner", "Hardcoded categories omit suites and repeat coverage; superseded by run_quality_checks.py."),
    "inspect_web.py": ("manual-browser-inspection", "Targets an existing localhost:8080 bridge by default; requires selected safe target and browser/CDN resources."),
    "inspect_all_views.py": ("historical-browser-experiment", "Own virtual radio but standalone server and operator config; CDN assets not isolated."),
    "audit_frontend_browser.py": ("auxiliary-browser-audit", "Own virtual radio but standalone server and operator config; CDN assets not isolated."),
    "test_search_filters.py": ("historical-browser-experiment", "Search scenario with standalone virtual server and browser/CDN; migrated suite is hermetic."),
    "test_ip_and_security_logging.py": ("auxiliary-loopback-integration", "Starts HTTP/TCP servers using operator config and logs; canonical tests isolate ports/state."),
    "simulate_tcp_mesh_network.py": ("auxiliary-loopback-simulation", "Custom virtual radio and real loopback TCP fixed port5000; standalone, outside pytest fixtures."),
    "simulate_mesh_network.py": ("auxiliary-simulation", "Mock radio/MQTT scenario with standalone config/state; no hardware required."),
    "simulate_complex_mesh_scenario.py": ("auxiliary-simulation", "Mock multi-role scenario with standalone config/state; no hardware required."),
    "simulate_full_mesh_validation.py": ("auxiliary-simulation", "Custom multi-node mocks and concurrency scenario; current config/state not fixture-isolated."),
    "simulate_concurrent_network.py": ("auxiliary-simulation", "Standalone mocked radio/MQTT load and rate limiter; current config/history not isolated."),
    "simulate_extreme_scenarios.py": ("manual-chaos-demo", "Calls full bridge.start with virtual radio; can start configured broker/server services and mutate working data."),
    "simulate_heltec_v4_mesh.py": ("manual-virtual-demo", "COM7 is mocked, but full bridge.start and fixed web8080 can start broker services and mutate working data."),
    "export_logs.py": ("manual-operator-diagnostic", "Reads current operator logs or existing bridge URL; produces export rather than test evidence."),
    "generate_sample_mbtiles.py": ("manual-map-fixture-generator", "Writes sample map database in working data; hermetic tile test creates its own temporary database."),
    "build_diagrams.py": ("manual-documentation-generator", "Generates documentation diagrams; outside test suite and assigned QA write scope."),
    "inventory_verification.py": ("maintained-inventory-generator", "AST reads verification sources and writes inventory; does not import application or execute scenarios."),
}


def build_inventory(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for directory in ("tests", "scripts", "scratch"):
        for path in sorted((root / directory).rglob("*.py")):
            if "__pycache__" in path.parts or "artifacts" in path.parts or (directory == "scratch" and "maintenance" in path.parts):
                continue
            source = path.read_text(encoding="utf-8-sig")
            try:
                tree = ast.parse(source, filename=str(path))
            except SyntaxError:
                continue
            functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if directory == "tests":
                category, reason = ("maintained-pytest-suite", "Collected by full pytest gate with isolated configuration/state.") if path.name.startswith("test_") else ("maintained-pytest-fixtures", "Shared isolation and virtual loopback/browser fixtures.")
                execution = "full-pytest-gate"
            elif directory == "scripts":
                category, reason = SCRIPT_REASONS.get(path.name, ("unclassified", "Requires manual review before execution."))
                execution = "AST-reviewed; canonical helpers tested by pytest" if category.startswith("maintained") else "AST-reviewed; not independently executed: " + reason
                if path.name == "audit_codebase_integrity.py":
                    execution = "Executed by main QA:59 application imports passed; scans source references."
                elif path.name == "inventory_verification.py":
                    execution = "Executed:AST source inventory and report generation; no imports or scenario execution."
            elif path.name == "fix2.py":
                category, reason = "historical-source-mutation-tool", "Rewrites production JS; not a verification scenario, never execute as QA."
                execution = "AST-reviewed; not executed"
            else:
                category, reason = "historical-browser-experiment", "Standalone virtual server on fixed port8094/8095/8098 with operator state and remote map assets; not pytest collected."
                execution = "AST-reviewed; not executed; isolated maintained browser and tile tests cover supported contracts"
            files.append({"path": path.relative_to(root).as_posix(), "category": category, "reason": reason, "execution": execution, "test_functions": [name for name in functions if name.startswith("test_")], "docstring": ast.get_docstring(tree), "lines": len(source.splitlines())})
    counts = {directory: sum(str(item["path"]).startswith(directory + "/") for item in files) for directory in ("tests", "scripts", "scratch")}
    evidence: dict[str, object] = {}
    for label, relative in (("baseline", "tests/artifacts/qa-baseline.xml"), ("latest_full_pytest", "tests/artifacts/pytest-final.xml")):
        report = root / relative
        if report.exists():
            suites = ET.parse(report).getroot().findall(".//testsuite")
            metrics = {name: sum(int(suite.get(name, "0")) for suite in suites) for name in ("tests", "failures", "errors", "skipped")}
            metrics["passed"] = metrics["tests"] - metrics["failures"] - metrics["errors"] - metrics["skipped"]
            evidence[label] = {"report": relative, "counts": metrics}
    coverage = root / "tests/artifacts/coverage.json"
    if coverage.exists():
        evidence["latest_coverage"] = {"report": coverage.relative_to(root).as_posix(), "totals": json.loads(coverage.read_text(encoding="utf-8"))["totals"]}
    evidence["baseline_limitations"] = "Baseline excluded both original browser suites requiring live localhost8080/CDN; original non-browser gate had277cases. Current full gate includes migrated hermetic Chromium suites and new regressions."
    return {"scope": "All project verification Python files under tests/, scripts/ and scratch/; excludes reference/, vendored .agents/ and current-task temporary scratch/maintenance migration/staging tools", "counts": counts, "evidence": evidence, "hardware": "No physical radio or production broker exercised. Hardware-labelled suite tests use mocks.", "browser_limitations": "Real Chromium SPA and WebSocket tests allow only ephemeral loopback origin; optional remote font/Leaflet tags omitted, geographic map rendering/CDN not validated.", "files": files}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    inventory = build_inventory(root)
    destination = root / "tests/artifacts/inventory.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = inventory["counts"]
    suite_count = sum(str(item["path"]).startswith("tests/test_") for item in inventory["files"])
    lines = [
        "# Inventario de verificación",
        "",
        "Generado mediante `python scripts/inventory_verification.py`, leyendo y analizando los archivos con AST sin importar sus módulos ni ejecutar escenarios.",
        "",
        f"El alcance incluye {len(inventory['files'])} archivos: {counts['tests']} Python en `tests/` ({suite_count} suites y fixtures), {counts['scripts']} en `scripts/` y {counts['scratch']} archivos históricos de `scratch/`. Se excluyen referencias, vendors y las herramientas temporales de migración de esta revisión en `scratch/maintenance/`.",
        "",
        "La suite mantenida se ejecuta completa mediante `python scripts/run_quality_checks.py`; pytest descubre todas las suites de `tests/`. Los scripts auxiliares no se ejecutan como parte de pytest: su revisión AST no confirma que sus escenarios pasen. La evidencia y los conteos de la última ejecución completa están en `tests/artifacts/inventory.json` y `tests/artifacts/pytest-final.xml`. El runner puede producir `tests/artifacts/quality.json`. Consultar [TESTING.md](TESTING.md) para comandos y resultados finales.",
        "",
        "Verificación auxiliar ejecutada por el agente principal: `audit_codebase_integrity.py` importó 59 módulos de aplicación correctamente; el auditor estático de asyncio pasó y Bandit con `-ll -ii` no señaló hallazgos de severidad y confianza media/alta. Esto no constituye una prueba de ausencia de vulnerabilidades. Los helpers API de skills se validan aparte; sus resultados definitivos están en TESTING.md.",
        "",
        "Las pruebas mantenidas aíslan configuración `.env`, archivos JSON, mapas y logs. Usan mocks o radio virtual y servidores de loopback; no verifican radio física, un broker de producción, despliegue en SBC ni integración n8n externa. Las etiquetas hardware/flapping se refieren a fallos simulados.",
        "",
        "Chromium ejecuta la SPA, sus controles DOM, REST y WebSocket reales contra un origin de loopback efímero. La fixture concede acceso de red local únicamente a ese origin y bloquea solicitudes externas. Omite las etiquetas opcionales de fuentes remotas y Leaflet: navegación del mapa y servicio de tiles local están cubiertos, pero el renderizado geográfico con Leaflet/CDN no. Revisa errores JavaScript, consola, HTTP y peticiones fallidas. Capturas: `tests/artifacts/qa_spa_1920x1080.png` y `tests/artifacts/qa_spa_390x844.png`.",
        "",
        "La cobertura es de líneas Python ejecutadas; no equivale a cobertura del JavaScript ni a garantía de todos los contratos. Administración CLI, SDK físico y flujos de configuración siguen teniendo ramas sin ejecutar. Los archivos mutation/resilience contienen casos adversarios dirigidos, no una campaña automatizada de mutación.",
        "",
        "| Archivo | Clasificación | Estado y alcance |",
        "| --- | --- | --- |",
    ]
    for item in inventory["files"]:
        path = str(item["path"])
        reason = str(item["reason"])
        if path.startswith("tests/"):
            description = str(item["docstring"] or "").split("\n", 1)[0]
            reason = "Suite del gate completo. " + description if path.split("/")[-1].startswith("test_") else reason
        else:
            if path.endswith("audit_codebase_integrity.py"):
                reason = str(item["execution"])
            elif path.endswith("inventory_verification.py"):
                reason = "Herramienta de inventario ejecutada: lectura AST y generación de JSON/Markdown; no ejecuta los módulos revisados."
            elif str(item["category"]).startswith("maintained"):
                reason = "Helper ejecutado en el gate o generación del inventario; contratos cubiertos por pruebas de tooling. " + reason
            else:
                reason = "Revisado con AST; sin ejecución independiente. " + reason
        lines.append(f"| [{path}](../{path}) | {item['category']} | {reason.replace('|', '/')} |")
    (root / "docs/TEST_INVENTORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inventoried {len(inventory['files'])} verification files: {destination}")


if __name__ == "__main__":
    main()
