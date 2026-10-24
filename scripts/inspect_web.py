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
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

# Configurar salida UTF-8 en terminal de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


REQUIRED_COMPONENTS = {
    "header_bar": "header.app-header",
    "tab_navigation_buttons": ".nav-btn[role='tab']",
    "chat_panel": "#tab-chat",
    "chat_message_feed": "#chatMessageFeed",
    "chat_input": "#chatInputText",
    "map_container": "#tab-map",
    "nodes_panel": "#tab-nodes",
    "logs_panel": "#tab-logs",
    "settings_panel": "#tab-settings",
}


def viewport_passed(result: dict[str, Any]) -> bool:
    """Require an authorized station and all checks, not merely an HTTP 200."""
    components = result.get("components_detected", {})
    errors = result.get("errors", {})
    status = result.get("http_status", 0)
    return bool(
        isinstance(status, int) and 200 <= status < 300
        and result.get("authenticated") is True
        and result.get("station_visible") is True
        and all(components.get(name) for name in REQUIRED_COMPONENTS)
        and not any(errors.get(name) for name in ("console", "page_exceptions", "failed_network", "inspection"))
    )


class WebInspector:
    """Inspect both viewports using an existing, explicitly supplied session."""

    def __init__(
        self, target_url: str, output_dir: str | Path = "tests/artifacts", *,
        storage_state: str | Path | None = None,
    ) -> None:
        parsed = urlsplit(target_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Inspection requires an HTTP(S) URL without embedded credentials")
        self.target_url = target_url
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.storage_state = str(Path(storage_state).resolve()) if storage_state else None
        if self.storage_state and not Path(self.storage_state).is_file():
            raise ValueError("Browser storage state must be an existing authorized session file")
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.failed_requests: list[dict[str, Any]] = []

    async def _inspect_viewport(
        self, browser: Any, name: str, viewport: dict[str, int], mobile: bool,
    ) -> dict[str, Any]:
        errors: dict[str, list[Any]] = {key: [] for key in ("console", "page_exceptions", "failed_network", "inspection")}
        result: dict[str, Any] = {
            "status": "FAIL", "authenticated": False, "station_visible": False,
            "components_detected": {}, "errors": errors, "http_status": 0,
        }
        options: dict[str, Any] = {"viewport": viewport, "is_mobile": mobile, "has_touch": mobile}
        if self.storage_state:
            options["storage_state"] = self.storage_state
        context = await browser.new_context(**options)
        try:
            page = await context.new_page()
            page.on("console", lambda message: errors["console"].append(f"[{message.type}] {message.text}")
                    if message.type in ("error", "warning") else None)
            page.on("pageerror", lambda error: errors["page_exceptions"].append(str(error)))
            page.on("response", lambda response: errors["failed_network"].append({
                "url": response.url, "status": response.status,
            }) if response.status >= 400 else None)
            page.on("requestfailed", lambda request: errors["failed_network"].append({
                "url": request.url, "status": 0, "failure": request.failure or "failed",
            }))
            session_response = await context.request.get(self.origin + "/api/auth/session")
            session = await session_response.json() if session_response.status == 200 else {}
            result["authenticated"] = bool(isinstance(session, dict) and session.get("authenticated")
                                            and not session.get("must_change_credentials"))
            if not result["authenticated"]:
                errors["inspection"].append("An authorized browser session is required; provide --storage-state. A Bearer token does not sign in the SPA.")
            response = await page.goto(self.target_url, wait_until="domcontentloaded", timeout=15000)
            result["http_status"] = response.status if response is not None else 0
            if result["authenticated"]:
                await page.locator("body:not(.auth-pending) header.app-header").wait_for(state="visible", timeout=15000)
            await page.wait_for_timeout(1500)
            result["page_title"] = await page.title()
            result["components_detected"] = {key: await page.locator(selector).count() > 0
                                                for key, selector in REQUIRED_COMPONENTS.items()}
            result["station_visible"] = bool(await page.locator("header.app-header").is_visible()
                                              and await page.locator("body.auth-pending").count() == 0)
            await page.screenshot(path=str(self.output_dir / f"{name}.png"), full_page=True)
            if name == "desktop":
                # Authenticated DOM may contain station data; artifacts stay local.
                (self.output_dir / "dom_dump.html").write_text(await page.content(), encoding="utf-8")
        except Exception as error:
            errors["inspection"].append(f"Inspection failed: {type(error).__name__}")
        finally:
            await context.close()
        result["status"] = "PASS" if viewport_passed(result) else "FAIL"
        return result

    async def inspect(self) -> dict[str, Any]:
        """Keep per-viewport evidence and fail if either inspection fails."""
        results: dict[str, Any] = {
            "target_url": self.target_url, "status": "ERROR", "viewports": {},
            "screenshots": {name: str(self.output_dir / f"{name}.png") for name in ("desktop", "mobile")},
            "dom_dump": str(self.output_dir / "dom_dump.html"),
        }
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                for name, viewport, mobile in (
                    ("desktop", {"width": 1920, "height": 1080}, False),
                    ("mobile", {"width": 390, "height": 844}, True),
                ):
                    try:
                        results["viewports"][name] = await self._inspect_viewport(browser, name, viewport, mobile)
                    except Exception as error:
                        results["viewports"][name] = {"status": "ERROR", "errors": {"inspection": [type(error).__name__]}}
            finally:
                await browser.close()
        views = results["viewports"]
        desktop = views.get("desktop", {})
        results.update(page_title=desktop.get("page_title", ""), http_status=desktop.get("http_status", 0),
                       components_detected=desktop.get("components_detected", {}))
        self.console_errors = [error for view in views.values() for error in view.get("errors", {}).get("console", [])]
        self.page_errors = [error for view in views.values() for error in view.get("errors", {}).get("page_exceptions", [])]
        self.failed_requests = [error for view in views.values() for error in view.get("errors", {}).get("failed_network", [])]
        results.update(console_errors_count=len(self.console_errors), page_errors_count=len(self.page_errors),
                       failed_requests_count=len(self.failed_requests), errors={
                           "console": self.console_errors, "page_exceptions": self.page_errors,
                           "failed_network": self.failed_requests,
                       })
        results["status"] = "PASS" if len(views) == 2 and all(view.get("status") == "PASS" for view in views.values()) else "FAIL"
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
    for name, view in results.get("viewports", {}).items():
        print(f" • {name}: {view.get('status', 'ERROR')}")
        for issue in view.get("errors", {}).get("inspection", []):
            print(f"   {issue}")
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

    parser.add_argument("--storage-state", help="Existing Playwright storage state for an authorized browser session")
    args = parser.parse_args()
    try:
        inspector = WebInspector(target_url=args.url, output_dir=args.output,
                                 storage_state=args.storage_state)
    except ValueError as error:
        parser.error(str(error))
    results = await inspector.inspect()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    return 0 if results.get("status") == "PASS" else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
