"""Local preferences stay optional when browser storage is unavailable."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_optional_local_preferences_handle_denied_storage() -> None:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend JavaScript checks"
    module = (Path(__file__).parents[1] / "src/web/static/js/core/utils.js").as_uri()
    script = """
        const {readLocalPreference, writeLocalPreference} = await import(process.argv[1]);
        Object.defineProperty(globalThis, 'localStorage', {configurable: true,
            get() {throw new DOMException('Blocked', 'SecurityError');}});
        const denied = [readLocalPreference('key'), readLocalPreference('key', 'fallback'),
            writeLocalPreference('key', true)];
        const values = new Map();
        Object.defineProperty(globalThis, 'localStorage', {configurable: true, value: {
            getItem: key => values.get(key) ?? null,
            setItem: (key, value) => values.set(key, value),
        }});
        const available = [readLocalPreference('key', 'missing'),
            writeLocalPreference('key', true), readLocalPreference('key')];
        console.log(JSON.stringify({denied, available}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, module], capture_output=True,
        text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "denied": [None, "fallback", False], "available": ["missing", True, "true"],
    }


def test_fragment_counter_matches_utf8_packets_and_total_airtime() -> None:
    node = shutil.which("node")
    assert node is not None
    root = Path(__file__).parents[1] / "src/web/static/js"
    script = """
        globalThis.localStorage = {getItem: () => null};
        globalThis.window = {};
        globalThis.I18n = {t: (key, params) => JSON.stringify({key, params})};
        const {ChatModule} = await import(process.argv[1]);
        const {splitUtf8Message, getUtf8ByteLength, estimateLoraAirtimeMs} = await import(process.argv[2]);
        const text = '界'.repeat(106) + 'ab';
        const parts = splitUtf8Message(text, 160);
        const chat = new ChatModule({});
        chat.dom = {chatInputText: {value: text},
            chatCharCounter: {textContent: '', title: '', classList: {remove() {}}}};
        chat.updateCharCounter();
        console.log(JSON.stringify({sizes: parts.map(getUtf8ByteLength), rejoined: parts.join('') === text,
            label: chat.dom.chatCharCounter.textContent, tooltip: JSON.parse(chat.dom.chatCharCounter.title),
            expectedAirtime: parts.reduce((sum, part) => sum + estimateLoraAirtimeMs(getUtf8ByteLength(part), 11, 250, 5), 0)}));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, (root / "modules/chat.js").as_uri(),
         (root / "core/utils.js").as_uri()], capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stderr
    measured = json.loads(result.stdout)
    assert measured["sizes"] == [159, 160, 1] and measured["rejoined"]
    assert measured["label"] == "320 B (3 pkts)"
    assert measured["tooltip"]["key"] == "chat.fragmented_payload_title"
    assert measured["tooltip"]["params"]["airtime"] == measured["expectedAirtime"]
    assert measured["tooltip"]["params"]["max"] == 160
