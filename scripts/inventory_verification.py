"""Inventory project verification files without importing or executing them."""

from __future__ import annotations

import ast
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPT_REASONS = {
    "audit_codebase_integrity.py": ("auxiliary-static-audit", "Imports src and scans repository including vendor directories; separate from canonical gate."),
    "verify_all_components.py": ("auxiliary-simulation", "Standalone assertions with current config and registry; canonical pytest covers these contracts in isolated fixtures."),
    "validate_all_node_parameters.py": ("auxiliary-simulation", "Manual node parameter matrix uses current config and registry; no pytest fixture isolation."),
    "validate_project_docs.py": ("maintained-documentation-validator", "Run by canonical quality gate; exercised by test_quality_tools.py."),
    "run_quality_checks.py": ("maintained-quality-runner", "Canonical pytest, mypy, ruff and documentation gate; exercised by test_quality_tools.py."),
    "run_all_test_categories.py": ("historical-partial-runner", "Fixed categories omit newer suites; use run_quality_checks.py for the complete maintained gate."),
    "inspect_web.py": ("manual-browser-inspection", "Targets a selected existing station; requires an authorized cookie storage state and explicit browser permission; both viewports must pass."),
    "inspect_all_views.py": ("auxiliary-isolated-browser-inspection", "Uses isolated_frontend_station: temporary state, authenticated virtual radio and ephemeral loopback; requires explicit browser authorization."),
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
    "generate_sample_mbtiles.py": ("manual-map-fixture-generator", "Writes synthetic zoom 0-2 sample only in tests/artifacts/maps and refuses overwrite; tile tests create their own temporary databases."),
    "build_diagrams.py": ("manual-documentation-generator", "Generates documentation diagrams; outside test suite and assigned QA write scope."),
    "inventory_verification.py": ("maintained-inventory-generator", "AST reads verification sources and writes inventory; does not import application or execute scenarios."),
    "audit_frontend_inspection.py": ("historical-browser-experiment", "Partial temporary state, imports operator config and fixed port 8096; use maintained isolated browser tests for acceptance."),
    "audit_layers_inventory.py": ("auxiliary-static-inventory", "Reads AST and asset hashes without importing production; writes only selected report paths."),
    "audit_fastapi_phase0.py": ("historical-wheel-audit", "Reads phase-0 wheel metadata and dependency manifests; writes a resolution report, not current runtime evidence."),
    "check_frontend_health.py": ("auxiliary-isolated-browser-inspection", "Uses isolated_frontend_station with temporary state and authenticated virtual HTTP; requires explicit browser authorization."),
    "check_layer_contracts.py": ("maintained-static-contract-check", "Reads AST and forbidden imports for declared sources and package descendants; no application imports or dynamic-import verification."),
    "check_runtime_dependencies.py": ("maintained-runtime-diagnostic", "Checks selected installed dependency profiles and runtime; not a test suite or package updater."),
    "evaluate_refactoring_metrics.py": ("auxiliary-static-metrics", "AST decision-count heuristics; not measured performance or an exact McCabe certificate."),
    "inventory_project_knowledge.py": ("maintained-inventory-generator", "Reads project files, reference Git metadata and hashes; no application or scenario execution."),
    "isolated_frontend_station.py": ("maintained-browser-fixture-helper", "Creates disposable virtual station with isolated SQLite/logs and ephemeral loopback; importing it does not start a station."),
    "prepare_browser_assets.py": ("maintained-browser-asset-preparation", "Downloads pinned Leaflet 1.9.4 JS/CSS to tests/artifacts and verifies SHA-256; network preparation, not browser execution."),
    "reset_web_password.py": ("manual-credential-recovery", "Explicit local operation changes station credentials and revokes sessions/tokens; never execute as verification."),
    "setup_auth.py": ("manual-installation-helper", "Creates restricted default owner in configured SQLite if absent; preserves existing account, never execute as verification."),
    "staged_update.py": ("manual-installation-helper", "Validates and installs staged source while preserving operator data; modifies installation, never execute as verification."),
    "audit_frontend_i18n.cjs": ("auxiliary-static-translation-audit", "Reads catalogues and source with lexical heuristics; no browser or station startup."),
    "build_frontend.cjs": ("maintained-frontend-build", "Build writes minimized/gzip artifacts and manifest; --check compares in memory without publishing."),
    "check_frontend_syntax.cjs": ("maintained-frontend-syntax-check", "Runs node --check over application JS sources; no application execution or browser."),
}


def build_inventory(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for directory in ("tests", "scripts", "scratch"):
        for path in sorted((root / directory).rglob("*")):
            if not path.is_file() or path.suffix not in ({".py", ".cjs"} if directory == "scripts" else {".py"}):
                continue
            if "__pycache__" in path.parts or "artifacts" in path.parts or (directory == "scratch" and "maintenance" in path.parts):
                continue
            source = path.read_text(encoding="utf-8-sig")
            # CommonJS is inventoried as text; parsing it requires the separate Node check.
            tree = ast.parse(source, filename=str(path)) if path.suffix == ".py" else ast.Module(body=[], type_ignores=[])
            functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if directory == "tests":
                category, reason = ("maintained-pytest-suite", "Collected by full pytest gate with isolated configuration/state.") if path.name.startswith("test_") else ("maintained-pytest-fixtures", "Shared isolation and virtual loopback/browser fixtures.")
                execution = "full-pytest-gate"
            elif directory == "scripts":
                category, reason = SCRIPT_REASONS.get(path.name, ("unclassified", "Requires manual review before execution."))
                execution = "Source inventoried; not executed by this generator."
            elif path.name == "fix2.py":
                category, reason = "historical-source-mutation-tool", "Rewrites production JS; not a verification scenario, never execute as QA."
                execution = "AST-reviewed; not executed"
            else:
                category, reason = "historical-browser-experiment", "Standalone virtual server on fixed port8094/8095/8098 with operator state and remote map assets; not pytest collected."
                execution = "AST-reviewed; not executed; isolated maintained browser and tile tests cover supported contracts"
            files.append({"path": path.relative_to(root).as_posix(), "category": category, "reason": reason, "execution": execution, "test_functions": [name for name in functions if name.startswith("test_")], "docstring": ast.get_docstring(tree), "lines": len(source.splitlines()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    counts = {directory: sum(str(item["path"]).startswith(directory + "/") for item in files) for directory in ("tests", "scripts", "scratch")}
    evidence: dict[str, object] = {}
    for label, relative in (("historical_baseline", "tests/artifacts/qa-baseline.xml"), ("historical_pytest_final", "tests/artifacts/pytest-final.xml"), ("ci_junit_if_present", "tests/artifacts/junit.xml")):
        report = root / relative
        if report.exists():
            suites = ET.parse(report).getroot().findall(".//testsuite")
            metrics = {name: sum(int(suite.get(name, "0")) for suite in suites) for name in ("tests", "failures", "errors", "skipped")}
            metrics["passed"] = metrics["tests"] - metrics["failures"] - metrics["errors"] - metrics["skipped"]
            evidence[label] = {"report": relative, "counts": metrics, "sha256": hashlib.sha256(report.read_bytes()).hexdigest(), "limitation": "Existing local artifact; not run by this inventory and not attributed to the current source revision."}
    coverage = root / "tests/artifacts/coverage.json"
    if coverage.exists():
        evidence["historical_coverage"] = {"report": coverage.relative_to(root).as_posix(), "totals": json.loads(coverage.read_text(encoding="utf-8"))["totals"], "limitation": "Existing artifact; does not establish current checkout coverage."}
    return {"scope": "Python sources under tests/ and scratch/, Python/CommonJS under scripts/; excludes reference/, vendored .agents/, artifacts and scratch/maintenance", "counts": counts, "evidence": evidence, "execution": "Inventory only: no suite, application import, browser, physical radio or production broker was executed.", "files": files}


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
        "Generado mediante `python scripts/inventory_verification.py`: lectura AST de Python e inventario textual de CommonJS, sin importar módulos ni ejecutar escenarios. Los hashes de fuentes están en `tests/artifacts/inventory.json` (artefacto local ignorado en Git).",
        "",
        f"El alcance incluye {len(inventory['files'])} archivos: {counts['tests']} Python en `tests/` ({suite_count} módulos `test_*.py` y {counts['tests'] - suite_count} helpers/fixtures), {counts['scripts']} scripts Python/CommonJS y {counts['scratch']} archivos históricos de `scratch/`. Se excluyen referencias, vendors, artefactos y `scratch/maintenance/`.",
        "",
        "La suite mantenida se selecciona con `python -m pytest tests` o `python scripts/run_quality_checks.py` y requiere petición explícita del usuario. El segundo también ejecuta mypy, Ruff y documentación. Los scripts auxiliares no entran automáticamente en pytest. Consultar [TESTING.md](TESTING.md) para comandos y límites.",
        "",
        "Este inventario no ejecuta pytest, navegador, imports de producción, Bandit ni auditorías dinámicas. Si encuentra XML/cobertura locales, el JSON los registra como artefactos existentes sin atribuirlos al checkout actual. No acredita aprobación de pruebas, seguridad, rendimiento ni interoperabilidad.",
        "",
        "El contrato de las pruebas mantenidas exige configuración, SQLite, mapas y logs temporales; mocks o radio virtual y loopback. No debe acceder a una estación operativa. Las etiquetas hardware/flapping se refieren a fallos simulados y el inventario de fuentes no demuestra cumplimiento de cada fixture.",
        "",
        "Las fixtures mantenidas de navegador usan un origin efímero, activos locales y teselas remotas conocidas sustituidas por imágenes neutras; bloquean tráfico externo inesperado. CI prepara Leaflet fijado por SHA-256. Estas pruebas no acreditan disponibilidad de proveedores externos ni exactitud geográfica de sus teselas. Los scripts históricos conservan limitaciones específicas indicadas en la tabla.",
        "",
        "La cobertura mide líneas Python ejecutadas; no equivale a cobertura del JavaScript ni garantiza todos los contratos. Administración CLI, SDK físico y flujos de configuración requieren evidencia específica. Los archivos mutation/resilience contienen casos adversarios dirigidos, no una campaña automatizada de mutación.",
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
            if path.endswith("inventory_verification.py"):
                reason = "Herramienta de inventario ejecutada: lectura AST y generación de JSON/Markdown; no ejecuta los módulos revisados."
            elif str(item["category"]).startswith("maintained"):
                reason = "Herramienta mantenida; inventariada sin ejecutarla. " + reason
            else:
                reason = "Fuente inventariada; sin ejecución independiente. " + reason
        lines.append(f"| [{path}](../{path}) | {item['category']} | {reason.replace('|', '/')} |")
    (root / "docs/TEST_INVENTORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inventoried {len(inventory['files'])} verification files: {destination}")


if __name__ == "__main__":
    main()
