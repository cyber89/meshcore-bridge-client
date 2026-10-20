"""Execute the real workflow code locally; produce JSON only, never MQTT/RF."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / "n8n_workflow_meshcore.json"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required to execute workflow code")


def code_for(name: str) -> str:
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    return next(node["parameters"]["jsCode"] for node in workflow["nodes"] if node["name"] == name)


def execute(code: str, message: dict) -> list[dict]:
    runner = """
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const result = new Function('$input', input.code)({all: () => [{json: input.message}]});
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        [NODE or "node", "-e", runner], input=json.dumps({"code": code, "message": message}),
        text=True, encoding="utf-8", capture_output=True, check=True, timeout=10,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("name", ["Procesar Canal Público", "Procesar Canal Secundario", "Procesar DMs y Admin"])
def test_echo_produces_one_message_with_utf8_budget_and_whole_codepoints(name: str) -> None:
    result = execute(code_for(name), {
        "sender": "a" * 64, "sender_name": "José😀" * 50,
        "role": "CLIENT", "text": "😀á漢字" * 200, "channel_idx": 1,
    })
    assert len(result) == 1
    text = result[0]["json"]["text"]
    assert result[0]["json"]["topic"] == "meshcore/tx"
    assert len(text.encode("utf-8")) <= 120
    assert "\ufffd" not in text
    assert text.startswith("[Eco ")


def test_unconfigured_admin_and_prefix_ids_produce_no_radio_response() -> None:
    code = code_for("Procesar DMs y Admin")
    assert execute(code, {"sender": "a" * 64, "role": "CLIENT", "text": "/admin get_config"}) == []
    configured = code.replace("const ADMIN_WHITELIST = [];", "const ADMIN_WHITELIST = ['aaaaaaaa'];")
    assert execute(configured, {"sender": "a" * 64, "role": "CLIENT", "text": "/admin get_config"}) == []


def test_configured_complete_admin_key_matches_case_insensitively() -> None:
    code = code_for("Procesar DMs y Admin").replace(
        "const ADMIN_WHITELIST = [];", "const ADMIN_WHITELIST = ['" + "a" * 64 + "'];",
    )
    result = execute(code, {"sender": "A" * 64, "role": "CLIENT", "text": "/admin get_config"})
    commands = [item["json"] for item in result if item["json"]["topic"] == "meshcore/admin/cmd"]
    assert len(commands) == 1
    assert commands[0]["action"] == "get_config"
