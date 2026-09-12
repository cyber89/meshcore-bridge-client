#!/usr/bin/env python3
"""Verificador Estático de Paridad de API REST y WebSockets para MeshCore Bridge.

Compara las rutas expuestas en el backend (api_router.py y controladores) con las llamadas
fetch('/api/...') realizadas en el cliente web SPA (src/web/static/js/).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Asegurar encoding UTF-8 en stdout
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[4]
BACKEND_ROUTER = ROOT_DIR / "src" / "web" / "api_router.py"
FRONTEND_DIR = ROOT_DIR / "src" / "web" / "static" / "js"


def extract_backend_routes() -> set[str]:
    """Extrae las rutas /api/... definidas en api_router.py."""
    routes: set[str] = set()
    if not BACKEND_ROUTER.exists():
        print(f"⚠️  No se encontró {BACKEND_ROUTER}")
        return routes

    content = BACKEND_ROUTER.read_text(encoding="utf-8")
    # Buscar patrones de rutas /api/...
    matches = re.findall(r'"(/api/[a-zA-Z0-9_\-\./]+)"', content)
    for m in matches:
        clean = m.rstrip("/")
        # Omitir rutas de ejemplo o tests
        if not clean.endswith(".py"):
            routes.add(clean)

    return routes


def extract_frontend_api_calls() -> dict[str, list[str]]:
    """Extrae todas las llamadas a endpoints /api/... en archivos JS del frontend."""
    calls_by_file: dict[str, list[str]] = {}
    if not FRONTEND_DIR.exists():
        return calls_by_file

    api_pattern = re.compile(r"""(?:fetch|url)\s*[(:=]\s*[`'"](/api/[a-zA-Z0-9_\-\./$${}]+)[`'"]""")

    for js_file in sorted(FRONTEND_DIR.rglob("*.js")):
        content = js_file.read_text(encoding="utf-8")
        matches = api_pattern.findall(content)
        if matches:
            rel_path = str(js_file.relative_to(FRONTEND_DIR))
            calls_by_file[rel_path] = []
            for m in matches:
                # Normalizar interpolaciones como ${id} o ${key} a comodines
                norm = re.sub(r"\$\{[^}]+\}", "*", m).rstrip("/")
                calls_by_file[rel_path].append(norm)

    return calls_by_file


def is_route_covered(fe_call: str, be_routes: set[str]) -> bool:
    """Comprueba si una llamada del frontend coincide o encaja con un prefijo del backend."""
    if fe_call in be_routes:
        return True

    # Comprobación de comodín /api/nodes/* -> /api/nodes o similar
    base_prefix = fe_call.split("?")[0]
    if base_prefix in be_routes:
        return True

    # Comprobar si coincide con rutas dinámicas conocidas
    prefix_parts = [p for p in base_prefix.split("/") if p and p != "*"]
    prefix_check = "/" + "/".join(prefix_parts)
    if prefix_check in be_routes:
        return True

    # Comprobar coincidencia con rutas de prefijo (ej: /api/channels, /api/contacts)
    for r in be_routes:
        if base_prefix.startswith(r) or r.startswith(base_prefix):
            return True

    return False


def main() -> None:
    print("🔍 [API PARITY] Verificando paridad entre API Backend y Frontend SPA...\n")
    be_routes = extract_backend_routes()
    fe_calls = extract_frontend_api_calls()

    print(f"📦 Rutas detectadas en Backend: {len(be_routes)}")
    total_fe_calls = sum(len(c) for c in fe_calls.values())
    print(f"🌐 Llamadas API detectadas en Frontend: {total_fe_calls} en {len(fe_calls)} archivos JS\n")

    missing_in_backend: list[tuple[str, str]] = []
    matched_calls = 0

    for js_file, calls in fe_calls.items():
        for call in calls:
            if is_route_covered(call, be_routes):
                matched_calls += 1
            else:
                missing_in_backend.append((js_file, call))

    print("=" * 60)
    if missing_in_backend:
        print(f"❌ [DESALINEACIÓN DETECTADA] {len(missing_in_backend)} llamadas no coinciden:")
        for f, c in missing_in_backend:
            print(f"   • {f}: {c}")
    else:
        print("✅ [PARIDAD 100% OK] Todas las llamadas del frontend corresponden a rutas válidas.")

    print(f"   • Llamadas verificadas con éxito: {matched_calls}/{total_fe_calls}")
    print("=" * 60)


if __name__ == "__main__":
    main()
