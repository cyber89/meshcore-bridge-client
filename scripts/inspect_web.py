#!/usr/bin/env python3
"""
Playwright Web Browser Inspection & Visual QA Automation Script.
Inspecciona una URL local en modo headless, captura errores de consola/red,
toma capturas de pantalla en vistas Desktop y Mobile, y valida el estado del DOM.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import ConsoleMessage, Response, async_playwright

# Configurar salida UTF-8 en terminal de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class WebInspector:
    """Inspector visual y funcional automatizado con Playwright."""

    def __init__(self, target_url: str, output_dir: str | Path = "tests/artifacts") -> None:
        self.target_url = target_url
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.failed_requests: list[dict[str, Any]] = []

    def _handle_console_message(self, msg: ConsoleMessage) -> None:
        if msg.type in ("error", "warning"):
            self.console_errors.append(f"[{msg.type.upper()}] {msg.text}")

    def _handle_page_error(self, exc: Any) -> None:
        self.page_errors.append(str(exc))

    def _handle_response(self, response: Response) -> None:
        if response.status >= 400:
            self.failed_requests.append({
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
            })

    async def inspect(self) -> dict[str, Any]:
        """Ejecuta la inspección completa en Desktop y Mobile."""
        desktop_png = self.output_dir / "desktop.png"
        mobile_png = self.output_dir / "mobile.png"
        dom_dump_file = self.output_dir / "dom_dump.html"

        results: dict[str, Any] = {
            "target_url": self.target_url,
            "status": "UNKNOWN",
            "page_title": "",
            "components_detected": {},
            "console_errors_count": 0,
            "page_errors_count": 0,
            "failed_requests_count": 0,
            "screenshots": {
                "desktop": str(desktop_png),
                "mobile": str(mobile_png),
            },
            "dom_dump": str(dom_dump_file),
            "errors": {
                "console": [],
                "page_exceptions": [],
                "failed_network": [],
            },
        }

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                # -------------------------------------------------------------
                # 1. Inspección en Vista Desktop (1920 x 1080)
                # -------------------------------------------------------------
                desktop_ctx = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )
                page = await desktop_ctx.new_page()

                page.on("console", self._handle_console_message)
                page.on("pageerror", self._handle_page_error)
                page.on("response", self._handle_response)

                try:
                    resp = await page.goto(self.target_url, wait_until="networkidle", timeout=15000)
                    http_status = resp.status if resp else 200
                except Exception:
                    # Fallback si WebSocket mantiene networkidle activo
                    resp = await page.goto(self.target_url, wait_until="domcontentloaded", timeout=15000)
                    http_status = resp.status if resp else 200

                # Esperar 1.5 segundos para renderizado dinámico y WebSocket handshake
                await page.wait_for_timeout(1500)

                results["page_title"] = await page.title()
                results["http_status"] = http_status

                # Captura Desktop
                await page.screenshot(path=str(desktop_png), full_page=True)

                # Volcado del DOM
                dom_html = await page.content()
                with open(dom_dump_file, "w", encoding="utf-8") as f:
                    f.write(dom_html)

                # Detección y validación de componentes clave en el DOM
                results["components_detected"] = {
                    "header_bar": await page.locator("header.app-header").count() > 0,
                    "h1_title": await page.locator("h1, .logo-title").count() > 0,
                    "tab_navigation_buttons": await page.locator(".nav-btn[role='tab']").count(),
                    "chat_panel (#tab-chat)": await page.locator("#tab-chat").count() > 0,
                    "chat_message_feed": await page.locator("#chatMessageFeed").count() > 0,
                    "map_container (#tab-map)": await page.locator("#tab-map, #liveGpsMap").count() > 0,
                    "nodes_panel (#tab-nodes)": await page.locator("#tab-nodes").count() > 0,
                    "sniffer_panel (#tab-sniffer)": await page.locator("#tab-sniffer").count() > 0,
                    "analytics_panel (#tab-analytics)": await page.locator("#tab-analytics").count() > 0,
                    "telemetry_panel (#tab-telemetry)": await page.locator("#tab-telemetry").count() > 0,
                    "logs_panel (#tab-logs)": await page.locator("#tab-logs").count() > 0,
                }

                await desktop_ctx.close()

                # -------------------------------------------------------------
                # 2. Inspección en Vista Móvil (390 x 844 - iPhone 14/15)
                # -------------------------------------------------------------
                mobile_ctx = await browser.new_context(
                    viewport={"width": 390, "height": 844},
                    is_mobile=True,
                    has_touch=True,
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                )
                mobile_page = await mobile_ctx.new_page()

                try:
                    await mobile_page.goto(self.target_url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass

                await mobile_page.wait_for_timeout(1000)
                await mobile_page.screenshot(path=str(mobile_png), full_page=True)
                await mobile_ctx.close()

                # Consolidar resultados
                results["console_errors_count"] = len(self.console_errors)
                results["page_errors_count"] = len(self.page_errors)
                results["failed_requests_count"] = len(self.failed_requests)
                results["errors"]["console"] = self.console_errors
                results["errors"]["page_exceptions"] = self.page_errors
                results["errors"]["failed_network"] = self.failed_requests

                if len(self.page_errors) == 0 and len(self.failed_requests) == 0:
                    results["status"] = "PASS"
                else:
                    results["status"] = "FAIL"

            except Exception as e:
                results["status"] = "ERROR"
                results["error_message"] = str(e)
            finally:
                await browser.close()

        return results


def print_report(results: dict[str, Any]) -> None:
    """Imprime un informe en consola con formato visual estructurado."""
    status = results.get("status", "UNKNOWN")
    status_tag = "✅ [PASS]" if status == "PASS" else "❌ [FAIL]"

    print("\n" + "=" * 74)
    print(f" 🌐 PLAYWRIGHT VISUAL & FUNCTIONAL INSPECTION REPORT: {status_tag}")
    print("=" * 74)
    print(f" • URL Inspeccionada:   {results.get('target_url')}")
    print(f" • Título de Página:    {results.get('page_title')}")
    print(f" • Estado HTTP:         {results.get('http_status', 'N/A')}")
    print("-" * 74)
    print(" 📸 CAPTURAS DE PANTALLA GENERADAS:")
    print(f"   🖥️ Desktop (1920x1080): {results.get('screenshots', {}).get('desktop')}")
    print(f"   📱 Mobile (390x844):    {results.get('screenshots', {}).get('mobile')}")
    print(f"   📄 DOM Dump HTML:       {results.get('dom_dump')}")
    print("-" * 74)
    print(" 🧩 COMPONENTES DETECTADOS EN EL DOM:")
    for comp, detected in results.get("components_detected", {}).items():
        val_str = f"✅ ({detected})" if (isinstance(detected, int) and detected > 0) or detected is True else f"⚠️ ({detected})"
        print(f"   - {comp:<22}: {val_str}")
    print("-" * 74)
    print(" 🔍 RESUMEN DE SALUD Y ERRORES:")
    print(f"   • Excepciones JS no capturadas: {results.get('page_errors_count', 0)}")
    print(f"   • Peticiones de red fallidas:   {results.get('failed_requests_count', 0)}")
    print(f"   • Mensajes de consola (Error):  {results.get('console_errors_count', 0)}")

    if results.get("errors", {}).get("page_exceptions"):
        print("\n   [!] Excepciones JS:")
        for err in results["errors"]["page_exceptions"]:
            print(f"       ❌ {err}")

    if results.get("errors", {}).get("failed_network"):
        print("\n   [!] Peticiones HTTP Fallidas (4xx / 5xx):")
        for req in results["errors"]["failed_network"]:
            print(f"       ❌ HTTP {req.get('status')} -> {req.get('url')}")

    print("=" * 74 + "\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright Visual and Functional Web Inspector")
    parser.add_argument("--url", default="http://localhost:8080", help="URL to inspect (default: http://localhost:8080)")
    parser.add_argument("--output", default="tests/artifacts", help="Output directory for screenshots and DOM dump")
    parser.add_argument("--json", action="store_true", help="Output results strictly in JSON format")

    args = parser.parse_args()

    inspector = WebInspector(target_url=args.url, output_dir=args.output)
    results = await inspector.inspect()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    return 0 if results.get("status") == "PASS" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
