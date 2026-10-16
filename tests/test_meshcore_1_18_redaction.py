"""WiFi CLI credentials stay out of public payloads and browser history."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, Route, expect

from src.protocol_types import redact_command_str, redact_sensitive_dict


@pytest.mark.parametrize(
    "command, expected",
    [
        ("set wifi.pwd isolated-wifi-secret", "set wifi.pwd ********"),
        ("SET WIFI.PWD isolated-wifi-secret", "SET WIFI.PWD ********"),
        ("set wifi.password isolated-wifi-secret", "set wifi.password ********"),
        ("ab|set wifi.pwd isolated-wifi-secret", "ab|set wifi.pwd ********"),
        ("  set wifi.pwd isolated-wifi-secret", "set wifi.pwd ********"),
        ("set  wifi.pwd isolated-wifi-secret", "set  wifi.pwd ********"),
        ("set\twifi.pwd isolated-wifi-secret", "set\twifi.pwd ********"),
        ("AA| set wifi.pwd isolated-wifi-secret", "AA| set wifi.pwd ********"),
        ("set  pin 654321", "set  pin ********"),
    ],
)
def test_wifi_cli_credentials_are_redacted(command: str, expected: str) -> None:
    assert redact_command_str(command) == expected
    assert redact_command_str(expected) == expected


def test_wifi_credentials_in_public_envelopes_are_redacted_without_mutation() -> None:
    private: dict[str, Any] = {
        "config": {"wifi.pwd": "isolated-wifi-secret", "wifi.password": "legacy-wifi-secret"},
        "commands": ["set wifi.pwd isolated-wifi-secret", "get wifi.ssid"],
    }
    public = redact_sensitive_dict(private)
    assert public == {
        "config": {"wifi.pwd": "********", "wifi.password": "********"},
        "commands": ["set wifi.pwd ********", "get wifi.ssid"],
    }
    assert private["config"]["wifi.pwd"] == "isolated-wifi-secret"
    assert redact_sensitive_dict(public) == public


def test_spa_redactor_covers_sensitive_aliases_and_spacing() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the real SPA redactor")
    module_path = Path(__file__).resolve().parents[1] / "src/web/static/js/modules/repeater.js"
    script = """
const { RepeaterModule } = await import(process.argv[1]);
const module = new RepeaterModule({});
const commands = [
  'set wifi.pwd isolated-wifi-secret',
  'set wifi.password legacy-wifi-secret',
  'ab|set wifi.pwd isolated-wifi-secret',
  '  set wifi.pwd isolated-wifi-secret',
  'AA| set wifi.pwd isolated-wifi-secret',
  'set pin 654321',
  'set prv.key isolated-identity-secret',
  'set admin.password isolated-admin-secret',
  'set_password isolated-admin-secret',
  'set identity isolated-identity-secret',
  'get wifi.ssid',
];
const visible = commands.map(command => module._redactRemoteCommand(command));
process.stdout.write(JSON.stringify(visible));
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, module_path.as_uri()],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert json.loads(result.stdout) == [
        "set wifi.pwd ********", "set wifi.password ********", "ab|set wifi.pwd ********",
        "  set wifi.pwd ********", "AA| set wifi.pwd ********", "set pin ********",
        "set prv.key ********", "set admin.password ********", "set_password ********",
        "set identity ********", "get wifi.ssid",
    ]


async def test_real_terminal_submits_keep_credentials_out_of_dom_and_recall(browser_page: Page) -> None:
    page = browser_page
    dispatched: list[str] = []

    async def virtual_remote(route: Route) -> None:
        body = route.request.post_data_json
        assert isinstance(body, dict)
        if body.get("action", "").startswith(("set", "AA|")):
            dispatched.append(body["action"])
        await route.fulfill(json={
            "status": "ok",
            "data": {"status": "ok", "authenticated": True, "message": "QA confirmed", "telemetry": {}},
        })

    await page.route("**/api/repeater/remote/**", virtual_remote)
    await page.locator('[data-tab="tab-nodes"]').click()
    await page.locator(".btn-manage-repeater").first.click()
    await page.locator("#repeaterGatePassword").fill("virtual-only-password")
    await page.locator("#btnRepeaterGateSubmit").click()
    await expect(page.locator("#repeaterAdminModalCard")).to_have_class(re.compile(r".*\bunlocked\b.*"))
    commands = [
        ("rep-info", "repQuickCmdInput", "repQuickCmdForm", "AA| set admin.password isolated-quick-secret"),
        ("rep-console", "repeaterTerminalInput", "repeaterTerminalForm", "set pin 654321"),
        ("rep-console", "repeaterTerminalInput", "repeaterTerminalForm", "set_prv_key isolated-identity-secret"),
    ]
    for panel, input_id, form_id, command in commands:
        await page.locator(f'#repeaterAdminModal [data-subtab="{panel}"]').click()
        field = page.locator(f"#{input_id}")
        await field.fill(command)
        await page.locator(f"#{form_id}").evaluate("form => form.requestSubmit()")
        await expect(page.locator("#repeaterTerminalOutput")).not_to_contain_text(command.split()[-1])
        await field.press("ArrowUp")
        await expect(field).to_have_value("")
    assert dispatched == [command for _, _, _, command in commands]
