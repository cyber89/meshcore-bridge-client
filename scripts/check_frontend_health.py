"""Health check script for MeshCore Bridge frontend using Playwright."""

from __future__ import annotations

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from isolated_frontend_station import isolated_frontend_station, login_inspection_context
from playwright.async_api import async_playwright


async def check_frontend_health() -> None:
    errors: list[str] = []
    logs: list[str] = []
    failed_requests: list[str] = []

    async with isolated_frontend_station() as (_bridge, base_url):
        async with async_playwright() as p, AsyncExitStack() as cleanup:
            browser = await p.chromium.launch(headless=True)
            cleanup.push_async_callback(browser.close)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            await login_inspection_context(context, base_url)
            page = await context.new_page()

            page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on(
                "requestfailed",
                lambda req: failed_requests.append(
                    f"{req.url} -> {req.failure or 'failed'}"
                ),
            )

            await page.goto(base_url, wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Test tabs
            tabs = [
                "tab-chat",
                "tab-contacts",
                "tab-nodes",
                "tab-map",
                "tab-analytics",
                "tab-logs",
                "tab-settings",
            ]
            for t in tabs:
                btn = page.locator(f'.nav-btn[data-tab="{t}"]')
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_timeout(400)

            print(f"=== PAGE EXCEPTIONS ({len(errors)}) ===")
            for e in errors:
                print("  EXCEPTION:", e)

            print(f"\n=== FAILED REQUESTS ({len(failed_requests)}) ===")
            for r in failed_requests:
                print("  FAILED:", r)

            warn_err_logs = [
                log_line
                for log_line in logs
                if log_line.startswith("[error]") or log_line.startswith("[warning]")
            ]
            print(f"\n=== CONSOLE WARNINGS/ERRORS ({len(warn_err_logs)}) ===")
            for log_line in warn_err_logs:
                print(" ", log_line)

            # Check chat message input presence
            chat_input = page.locator("#chatMessageInput")
            print("\n=== DOM ELEMENT CHECKS ===")
            print(f"#chatMessageInput exists: {await chat_input.count() > 0}")
            if await chat_input.count() > 0:
                print(f"#chatMessageInput is_visible: {await chat_input.is_visible()}")

            # Check theme toggle
            theme_btn = page.locator("#themeToggleBtn")
            print(f"#themeToggleBtn exists: {await theme_btn.count() > 0}")

            await browser.close()

if __name__ == "__main__":
    asyncio.run(check_frontend_health())
