#!/usr/bin/env python3
"""
MeshCore Universal Bridge - CLI Log and Diagnostics Exporter
Script de utilidad para exportar, visualizar y compartir diagnósticos y logs del bridge.

Uso:
  python scripts/export_logs.py --markdown           # Imprime informe Markdown para copiar y pegar a la IA
  python scripts/export_logs.py --tail 50            # Muestra las últimas 50 líneas de log en vivo
  python scripts/export_logs.py --json               # Imprime el snapshot diagnóstico completo en JSON
  python scripts/export_logs.py --output reporte.md  # Guarda el informe en un archivo específico
  python scripts/export_logs.py --live-url http://127.0.0.1:8080  # Consulta un bridge en ejecución
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

# Asegurar que el directorio raíz esté en sys.path para importar src
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Configurar stdout UTF-8 seguro para Windows y Linux
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class _NoDiagnosticRedirects(urllib.request.HTTPRedirectHandler):
    """Do not forward a diagnostic Bearer token to a redirected origin."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def fetch_from_api(url: str, endpoint: str) -> dict[str, object] | str | None:
    """Intenta consultar el endpoint REST del bridge en vivo."""
    full_url = f"{url.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        headers = {"User-Agent": "MeshCore-CLI-Exporter/3.0"}
        token = os.environ.get("MESHCORE_API_TOKEN") or os.environ.get("BRIDGE_API_KEY", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(full_url, headers=headers)
        opener = urllib.request.build_opener(_NoDiagnosticRedirects())
        with opener.open(req, timeout=3.0) as resp:
            data = resp.read().decode("utf-8")
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    return parsed
                return data
            except Exception:
                return data
    except Exception:
        return None


def generate_local_report() -> str:
    """Read existing logs without constructing a bridge or opening its database."""
    import config
    log_file = getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log")
    p = Path(log_file)
    content = p.read_text(encoding="utf-8", errors="ignore") if p.exists() else "Archivo de logs no encontrado."
    return f"# Reporte de Emergencia MeshCore Bridge\n\n```log\n{content[-2000:]}\n```"


def show_tail(lines: int = 50) -> bool:
    """Imprime las últimas N líneas del archivo de logs."""
    import config
    log_file = getattr(config, "LOG_FILE_PATH", "logs/meshcore-bridge.log")
    p = Path(log_file)
    if not p.exists():
        print(f"❌ Archivo de logs no encontrado en: {p}")
        return False

    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            tail = "".join(all_lines[-lines:])
            print(f"--- Últimas {lines} líneas de {p} ---")
            print(tail)
        return True
    except Exception as e:
        print(f"❌ Error leyendo archivo de logs: {e}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MeshCore Bridge - Diagnósticos y Exportador de Logs para IA / Soporte")
    parser.add_argument("--markdown", "-m", action="store_true", help="Genera reporte estructurado en Markdown")
    parser.add_argument("--json", "-j", action="store_true", help="Genera reporte completo en JSON")
    parser.add_argument("--tail", "-t", type=int, default=0, help="Muestra las últimas N líneas del archivo de logs")
    parser.add_argument("--output", "-o", type=str, help="Guarda el reporte generado en el archivo indicado")
    parser.add_argument("--live-url", type=str, default="http://127.0.0.1:8080", help="URL base del servidor web del bridge")

    args = parser.parse_args(argv)

    # 1. Caso Tail
    if args.tail > 0:
        return 0 if show_tail(args.tail) else 1

    # 2. Caso JSON
    if args.json:
        # Intentar API REST primero
        api_data = fetch_from_api(args.live_url, "/api/diagnostics/export")
        if (not isinstance(api_data, dict) or not api_data or "error" in api_data
                or api_data.get("status") in ("error", "failed")):
            print(json.dumps({"error": "Live diagnostics unavailable; set MESHCORE_API_TOKEN for authenticated access."}), file=sys.stderr)
            return 1
        out = json.dumps(api_data, indent=2)

        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            print(f"✓ Reporte JSON guardado en: {args.output}")
        else:
            print(out)
        return 0

    # 3. Caso Markdown (por defecto)
    api_md = fetch_from_api(args.live_url, "/api/diagnostics/report.md")
    if api_md and isinstance(api_md, dict) and "markdown" in api_md:
        report_text = str(api_md["markdown"])
    elif isinstance(api_md, str) and api_md:
        report_text = api_md
    else:
        report_text = generate_local_report()

    if args.output:
        Path(args.output).write_text(report_text, encoding="utf-8")
        print(f"✓ Reporte Markdown para IA guardado en: {args.output}")
    else:
        print(report_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
