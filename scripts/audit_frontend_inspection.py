"""
Comprehensive Frontend QA, Layout, Alignment and Console Debugger for MeshCore Bridge.
Runs the station in an isolated virtual environment and inspects every view, tab,
subtab, modal, theme, and viewport with Playwright Chromium.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.async_api import ConsoleMessage, Response, async_playwright

from src.bridge_core import MeshCoreBridge
from src.virtual_mesh_adapter import VirtualMeshAdapter
from src.web.auth_store import AuthStore


async def run_frontend_inspection() -> dict[str, Any]:
    temp_dir = tempfile.mkdtemp(prefix="meshcore_audit_")
    db_path = os.path.join(temp_dir, "station.sqlite3")
    artifacts_dir = PROJECT_ROOT / "tests" / "artifacts" / "frontend_audit"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Set up auth store in temp db with active admin user
    auth_store = AuthStore(db_path)
    auth_store.initialize()
    auth_store.bootstrap("admin", "correctpassword123", must_change_credentials=False)
    session = auth_store.login("admin", "correctpassword123", remember=True, peer="127.0.0.1")
    assert session is not None, "Failed to create audit session"

    # Configure environment for bridge
    import config
    os.environ["DATA_DIR"] = temp_dir
    os.environ["DATABASE_PATH"] = db_path
    config.DATA_DIR = temp_dir
    config.DATABASE_PATH = db_path
    config.NODE_REGISTRY_STORAGE_PATH = os.path.join(temp_dir, "node_registry.json")
    config.AIRTIME_HISTORY_FILE = os.path.join(temp_dir, "airtime_history.json")

    port = 8096
    bridge = MeshCoreBridge()
    if bridge.web_server:
        bridge.web_server.port = port

    v_adapter = VirtualMeshAdapter(event_callback=bridge.on_mesh_event)
    bridge.serial_adapter = v_adapter
    await v_adapter.connect()
    await bridge.web_server.start()
    await asyncio.sleep(1.0)

    # Seed mock data into bridge if needed
    base_url = f"http://localhost:{port}"

    console_records: list[dict[str, Any]] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    overflow_issues: list[dict[str, Any]] = []
    visual_audit_findings: list[dict[str, Any]] = []

    def on_console(msg: ConsoleMessage) -> None:
        console_records.append({
            "type": msg.type,
            "text": msg.text,
            "location": f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', 0)}" if msg.location else ""
        })

    def on_page_error(exc: Any) -> None:
        page_errors.append(str(exc))

    def on_response(resp: Response) -> None:
        if resp.status >= 400:
            failed_requests.append({
                "url": resp.url,
                "status": resp.status,
                "status_text": resp.status_text
            })

    report: dict[str, Any] = {
        "summary": {},
        "console_errors": [],
        "console_warnings": [],
        "page_errors": [],
        "failed_requests": [],
        "overflow_issues": [],
        "visual_audit_findings": [],
        "screenshots": [],
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            # ==========================================
            # 1. AUDIT AUTH GATE (DESKTOP & MOBILE)
            # ==========================================
            print("\n🔍 [1/5] Auditando Auth Gate (Pantalla de inicio de sesión)...")
            auth_context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            auth_page = await auth_context.new_page()
            auth_page.on("console", on_console)
            auth_page.on("pageerror", on_page_error)
            auth_page.on("response", on_response)

            await auth_page.goto(base_url, wait_until="networkidle")
            await auth_page.wait_for_timeout(600)

            shot_auth_dark = artifacts_dir / "00_auth_gate_dark_desktop.png"
            await auth_page.screenshot(path=str(shot_auth_dark), full_page=True)
            report["screenshots"].append(str(shot_auth_dark.name))

            # Test Auth Gate Theme Toggle
            await auth_page.locator("#authThemeButton").click()
            await auth_page.wait_for_timeout(300)
            shot_auth_light = artifacts_dir / "00_auth_gate_light_desktop.png"
            await auth_page.screenshot(path=str(shot_auth_light), full_page=True)
            report["screenshots"].append(str(shot_auth_light.name))

            # Switch back to dark
            await auth_page.locator("#authThemeButton").click()
            await auth_page.wait_for_timeout(200)

            # Auth Gate Mobile
            mobile_auth_page = await auth_context.new_page()
            await mobile_auth_page.set_viewport_size({"width": 390, "height": 844})
            await mobile_auth_page.goto(base_url, wait_until="networkidle")
            await mobile_auth_page.wait_for_timeout(400)
            shot_auth_mobile = artifacts_dir / "00_auth_gate_mobile.png"
            await mobile_auth_page.screenshot(path=str(shot_auth_mobile), full_page=True)
            report["screenshots"].append(str(shot_auth_mobile.name))
            await mobile_auth_page.close()
            await auth_context.close()

            # ==========================================
            # 2. AUDIT AUTHENTICATED STATION - DESKTOP (1920x1080)
            # ==========================================
            print("\n🔍 [2/5] Auditando Estación Autenticada Desktop (1920x1080)...")
            desktop_context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            page = await desktop_context.new_page()
            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("response", on_response)

            await page.goto(base_url, wait_until="networkidle")
            await page.wait_for_timeout(500)

            # Log in through UI form
            print("  🔑 Iniciando sesión mediante el formulario UI...")
            await page.fill("#loginUsername", "admin")
            await page.fill("#loginPassword", "correctpassword123")
            await page.click('.auth-submit')
            await page.wait_for_selector("body:not(.auth-pending)", timeout=8000)
            await page.wait_for_timeout(1000)
            print("  ✓ Sesión iniciada con éxito. auth-pending removido.")

            # Helper to check horizontal overflows
            async def check_overflow(view_name: str) -> None:
                issues = await page.evaluate("""
                    () => {
                        const results = [];
                        const docWidth = document.documentElement.clientWidth;
                        const isClipped = (el) => {
                            let p = el.parentElement;
                            while (p && p !== document.body && p !== document.documentElement) {
                                const style = window.getComputedStyle(p);
                                const ox = style.overflowX;
                                const o = style.overflow;
                                if (ox === 'auto' || ox === 'hidden' || ox === 'scroll' || ox === 'clip' ||
                                    o === 'hidden' || o === 'clip') {
                                    return true;
                                }
                                p = p.parentElement;
                            }
                            return false;
                        };
                        document.querySelectorAll('*').forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.right > docWidth + 1 && el.offsetParent !== null && !['HTML', 'BODY'].includes(el.tagName) && !isClipped(el)) {
                                results.push({
                                    tag: el.tagName,
                                    id: el.id || '',
                                    className: (el.className || '').toString().slice(0, 80),
                                    right: Math.round(rect.right),
                                    docWidth: docWidth,
                                    overflow: Math.round(rect.right - docWidth)
                                });
                            }
                        });
                        return results.slice(0, 5);
                    }
                """)
                for issue in issues:
                    overflow_issues.append({"view": view_name, **issue})

            # Check view tabs
            tabs = [
                ("01_chat", "tab-chat"),
                ("02_contacts", "tab-contacts"),
                ("03_nodes", "tab-nodes"),
                ("04_map", "tab-map"),
                ("05_analytics", "tab-analytics"),
                ("06_logs", "tab-logs"),
                ("07_settings", "tab-settings"),
            ]

            for prefix, tab_id in tabs:
                btn = page.locator(f'.nav-btn[data-tab="{tab_id}"]')
                if await btn.count() > 0:
                    await btn.click()
                    await page.wait_for_timeout(600)
                    await check_overflow(f"desktop_{tab_id}")
                    shot_path = artifacts_dir / f"{prefix}_{tab_id}_desktop.png"
                    await page.screenshot(path=str(shot_path), full_page=True)
                    report["screenshots"].append(str(shot_path.name))
                    print(f"  ✓ Vista Desktop capturada: {tab_id}")

            # Subpestaña Sniffer
            await page.locator('.nav-btn[data-tab="tab-logs"]').click()
            await page.wait_for_timeout(300)
            btn_sniffer = page.locator("#btnSubtabSniffer")
            if await btn_sniffer.count() > 0:
                await btn_sniffer.click()
                await page.wait_for_timeout(500)
                await check_overflow("desktop_sniffer")
                shot_sniffer = artifacts_dir / "06_sub_sniffer_desktop.png"
                await page.screenshot(path=str(shot_sniffer), full_page=True)
                report["screenshots"].append(str(shot_sniffer.name))
                print("  ✓ Subpestaña Sniffer capturada")

            # Subpestañas de Ajustes
            await page.locator('.nav-btn[data-tab="tab-settings"]').click()
            await page.wait_for_timeout(300)
            settings_subtabs = [
                "local-telemetry",
                "local-radio",
                "local-owner-pos",
                "local-console",
                "local-storage-maps",
                "local-security",
                "local-services",
            ]
            for sub in settings_subtabs:
                s_btn = page.locator(f'.local-subtab-btn[data-subtab="{sub}"]')
                if await s_btn.count() > 0:
                    await s_btn.click()
                    await page.wait_for_timeout(400)
                    await check_overflow(f"desktop_settings_{sub}")
                    s_path = artifacts_dir / f"07_sub_{sub}_desktop.png"
                    await page.screenshot(path=str(s_path), full_page=True)
                    report["screenshots"].append(str(s_path.name))
                    print(f"  ✓ Subpestaña Ajustes capturada: {sub}")

            # ==========================================
            # 3. AUDIT MODALS & DIALOGS
            # ==========================================
            print("\n🔍 [3/5] Auditando Diálogos Modales...")
            # Command palette
            btn_cmd = page.locator("#btnCommandPalette")
            if await btn_cmd.count() > 0:
                await btn_cmd.click()
                await page.wait_for_timeout(400)
                shot_cmd = artifacts_dir / "modal_command_palette.png"
                await page.screenshot(path=str(shot_cmd))
                report["screenshots"].append(str(shot_cmd.name))
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)

            # Account Dialog
            account_btn = page.locator('[data-open-account]')
            if await account_btn.count() > 0:
                await account_btn.first.click()
                await page.wait_for_timeout(400)
                shot_acc = artifacts_dir / "modal_account_dialog.png"
                await page.screenshot(path=str(shot_acc))
                report["screenshots"].append(str(shot_acc.name))
                btn_close_acc = page.locator("#accountCloseButton")
                if await btn_close_acc.count() > 0:
                    await btn_close_acc.click()
                    await page.wait_for_timeout(200)

            # Add Channel Modal
            await page.locator('.nav-btn[data-tab="tab-chat"]').click()
            await page.wait_for_timeout(200)
            btn_add_ch = page.locator("#btnAddChannel")
            if await btn_add_ch.count() > 0:
                await btn_add_ch.click()
                await page.wait_for_timeout(300)
                shot_ch = artifacts_dir / "modal_add_channel.png"
                await page.screenshot(path=str(shot_ch))
                report["screenshots"].append(str(shot_ch.name))
                btn_cancel_ch = page.locator("#btnCancelCreateChannel")
                if await btn_cancel_ch.count() > 0:
                    await btn_cancel_ch.click()
                    await page.wait_for_timeout(200)

            # Add Contact Modal
            await page.locator('.nav-btn[data-tab="tab-contacts"]').click()
            await page.wait_for_timeout(200)
            btn_add_ct = page.locator("#btnHeaderAddContact")
            if await btn_add_ct.count() > 0:
                await btn_add_ct.click()
                await page.wait_for_timeout(300)
                shot_ct = artifacts_dir / "modal_add_contact.png"
                await page.screenshot(path=str(shot_ct))
                report["screenshots"].append(str(shot_ct.name))
                btn_cancel_ct = page.locator("#btnCloseCreateContactModal")
                if await btn_cancel_ct.count() > 0:
                    await btn_cancel_ct.click()
                    await page.wait_for_timeout(200)

            # ==========================================
            # 4. AUDIT LIGHT THEME UNIFORMITY
            # ==========================================
            print("\n🔍 [4/5] Auditando Tema Claro (Zephyr)...")
            theme_btn = page.locator("#themeToggleBtn")
            if await theme_btn.count() > 0:
                await theme_btn.click()
                await page.wait_for_timeout(600)
                # Capture Chat and Nodes in Light theme
                await page.locator('.nav-btn[data-tab="tab-chat"]').click()
                await page.wait_for_timeout(400)
                shot_light_chat = artifacts_dir / "01_chat_light_desktop.png"
                await page.screenshot(path=str(shot_light_chat), full_page=True)
                report["screenshots"].append(str(shot_light_chat.name))

                await page.locator('.nav-btn[data-tab="tab-nodes"]').click()
                await page.wait_for_timeout(400)
                shot_light_nodes = artifacts_dir / "03_nodes_light_desktop.png"
                await page.screenshot(path=str(shot_light_nodes), full_page=True)
                report["screenshots"].append(str(shot_light_nodes.name))

                # Switch back to dark theme
                await theme_btn.click()
                await page.wait_for_timeout(400)

            # ==========================================
            # 5. AUDIT MOBILE RESPONSIVENESS (390x844)
            # ==========================================
            print("\n🔍 [5/5] Auditando Vistas Móviles (390x844 iPhone / Smartphone)...")
            mobile_context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
            )
            await mobile_context.add_cookies(await desktop_context.cookies())
            m_page = await mobile_context.new_page()
            m_page.on("console", on_console)
            m_page.on("pageerror", on_page_error)
            m_page.on("response", on_response)

            await m_page.goto(base_url, wait_until="networkidle")
            await m_page.wait_for_timeout(1000)

            for prefix, tab_id in tabs:
                await m_page.evaluate(f"""
                    () => {{
                        const btn = document.querySelector('.nav-btn[data-tab="{tab_id}"]');
                        if (btn) btn.click();
                        const offcanvas = document.getElementById("appSidebar");
                        if (offcanvas && typeof bootstrap !== "undefined" && bootstrap.Offcanvas) {{
                            const inst = bootstrap.Offcanvas.getInstance(offcanvas);
                            if (inst) inst.hide();
                        }}
                    }}
                """)
                await m_page.wait_for_timeout(600)

                # Check horizontal overflow on mobile
                m_issues = await m_page.evaluate("""
                    () => {
                        const results = [];
                        const docWidth = document.documentElement.clientWidth;
                        const isClipped = (el) => {
                            let p = el.parentElement;
                            while (p && p !== document.body && p !== document.documentElement) {
                                const style = window.getComputedStyle(p);
                                const ox = style.overflowX;
                                const o = style.overflow;
                                if (ox === 'auto' || ox === 'hidden' || ox === 'scroll' || ox === 'clip' ||
                                    o === 'hidden' || o === 'clip') {
                                    return true;
                                }
                                p = p.parentElement;
                            }
                            return false;
                        };
                        document.querySelectorAll('*').forEach(el => {
                            const rect = el.getBoundingClientRect();
                            if (rect.right > docWidth + 1 && el.offsetParent !== null && !['HTML', 'BODY'].includes(el.tagName) && !isClipped(el)) {
                                results.push({
                                    tag: el.tagName,
                                    id: el.id || '',
                                    className: (el.className || '').toString().slice(0, 80),
                                    right: Math.round(rect.right),
                                    docWidth: docWidth,
                                    overflow: Math.round(rect.right - docWidth)
                                });
                            }
                        });
                        return results.slice(0, 5);
                    }
                """)
                for issue in m_issues:
                    overflow_issues.append({"view": f"mobile_{tab_id}", **issue})

                shot_mobile = artifacts_dir / f"{prefix}_{tab_id}_mobile.png"
                await m_page.screenshot(path=str(shot_mobile), full_page=True)
                report["screenshots"].append(str(shot_mobile.name))
                print(f"  ✓ Vista Móvil capturada: {tab_id}")

            # Check Strict Rule Invariants (SSoT)
            contacts_role_check = await page.evaluate("""
                () => {
                    const repeaterInContacts = document.querySelector('#tab-contacts .role-repeater, #tab-contacts [data-role="REPEATER"], #tab-contacts [data-role="ROUTER"]');
                    const localInContacts = document.querySelector('#tab-contacts .role-local, #tab-contacts [data-role="LOCAL"]');
                    return {
                        repeaterFound: Boolean(repeaterInContacts),
                        localFound: Boolean(localInContacts)
                    };
                }
            """)
            if contacts_role_check.get("repeaterFound"):
                visual_audit_findings.append({
                    "severity": "CRITICAL",
                    "type": "SSOT_VIOLATION",
                    "description": "Se detectó un nodo REPEATER en la libreta de contactos (violación de AGENTS.md 1.1)."
                })
            if contacts_role_check.get("localFound"):
                visual_audit_findings.append({
                    "severity": "CRITICAL",
                    "type": "SSOT_VIOLATION",
                    "description": "Se detectó el nodo LOCAL en la libreta de contactos (violación de AGENTS.md 1.1)."
                })

            await m_page.close()
            await mobile_context.close()
            await page.close()
            await desktop_context.close()
            await browser.close()

    finally:
        await v_adapter.disconnect()
        await bridge.web_server.stop()
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    # Compile report
    errors = [c for c in console_records if c["type"] == "error"]
    warnings = [c for c in console_records if c["type"] == "warning"]

    report["console_errors"] = errors
    report["console_warnings"] = warnings
    report["page_errors"] = page_errors
    report["failed_requests"] = failed_requests
    report["overflow_issues"] = overflow_issues
    report["visual_audit_findings"] = visual_audit_findings
    report["summary"] = {
        "total_console_logs": len(console_records),
        "console_errors_count": len(errors),
        "console_warnings_count": len(warnings),
        "page_errors_count": len(page_errors),
        "failed_requests_count": len(failed_requests),
        "overflow_issues_count": len(overflow_issues),
        "visual_findings_count": len(visual_audit_findings),
        "screenshots_count": len(report["screenshots"]),
    }

    report_path = artifacts_dir / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📊 Reporte completo guardado en: {report_path}")
    return report


if __name__ == "__main__":
    rep = asyncio.run(run_frontend_inspection())
    print("\n" + "=" * 60)
    print("RESUMEN DE INSPECCIÓN:")
    print(json.dumps(rep["summary"], indent=2))
    print("=" * 60)
    if rep["console_errors"]:
        print("\n❌ ERRORES DE CONSOLA:")
        for e in rep["console_errors"]:
            print(f"  • [{e['location']}] {e['text']}")
    if rep["page_errors"]:
        print("\n❌ EXCEPCIONES JS:")
        for pe in rep["page_errors"]:
            print(f"  • {pe}")
    if rep["overflow_issues"]:
        print("\n⚠️ ELEMENTOS CON OVERFLOW DETECTADOS:")
        for oi in rep["overflow_issues"]:
            print(f"  • Vista {oi['view']}: <{oi['tag']}> id={oi['id']} cls={oi['className']} overflow={oi['overflow']}px")
