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

from playwright.async_api import async_playwright

from scripts.isolated_frontend_station import isolated_frontend_station, login_inspection_context


def health_exit_code(
    errors: list[str], failed_requests: list[str], console_errors: list[str], missing: list[str],
) -> int:
    """Return failure for a completed inspection with broken station behavior."""
    return int(bool(errors or failed_requests or console_errors or missing))


async def check_frontend_health() -> int:
    errors: list[str] = []
    logs: list[str] = []
    failed_requests: list[str] = []
    missing: list[str] = []

    async with isolated_frontend_station() as (_bridge, base_url):
        async with async_playwright() as p, AsyncExitStack() as cleanup:
            browser = await p.chromium.launch(headless=True)
            cleanup.push_async_callback(browser.close)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            await login_inspection_context(context, base_url)
            page = await context.new_page()

            page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("response", lambda response: failed_requests.append(
                f"HTTP {response.status}: {response.url}"
            ) if response.status >= 400 else None)
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
                    if not await page.locator(f"#{t}").is_visible():
                        missing.append(f"Visible panel #{t}")
                else:
                    missing.append(f"Navigation button for #{t}")

            chat_button = page.locator('.nav-btn[data-tab="tab-chat"]')
            if await chat_button.count() > 0:
                await chat_button.click()

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
            chat_input = page.locator("#chatInputText")
            print("\n=== DOM ELEMENT CHECKS ===")
            print(f"#chatInputText exists: {await chat_input.count() > 0}")
            if await chat_input.count() > 0:
                print(f"#chatInputText is_visible: {await chat_input.is_visible()}")
                if not await chat_input.is_visible():
                    missing.append("Visible #chatInputText")
            else:
                missing.append("#chatInputText")

            # Check theme toggle
            theme_btn = page.locator("#themeToggleBtn")
            print(f"#themeToggleBtn exists: {await theme_btn.count() > 0}")
            if await theme_btn.count() == 0:
                missing.append("#themeToggleBtn")
            for issue in missing:
                print("  MISSING:", issue)

            console_errors = [line for line in logs if line.startswith("[error]")]
            return health_exit_code(errors, failed_requests, console_errors, missing)
    return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(check_frontend_health()))
