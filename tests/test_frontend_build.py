"""Frontend receipts must describe the bytes preserved by Git checkouts."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_frontend.cjs"
BOOTSTRAP = """
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {createRequire} = require('node:module');
const filename = process.argv[1];
vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {
  require: createRequire(filename),
  __dirname: path.join(process.argv[2], 'scripts'),
  Buffer, console, process,
}, {filename});
"""


@pytest.fixture
def frontend_checkout(tmp_path: Path) -> Path:
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    if not (PROJECT_ROOT / "tools/frontend/node_modules/esbuild").is_dir():
        pytest.skip("Install locked frontend tools with npm ci --prefix tools/frontend")
    static = tmp_path / "src/web/static"
    (static / "js/core").mkdir(parents=True)
    (static / "index.html").write_bytes(b"<!doctype html>\n<p>isolated build</p>\n")
    (static / "js/core/theme.js").write_bytes(b"export const theme = 'dark';\n")
    return tmp_path


def run_build(checkout: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "-e", BOOTSTRAP, str(BUILD_SCRIPT), str(checkout), *arguments],
        capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
    )


@pytest.mark.parametrize("arguments", [(), ("--check",)])
def test_crlf_source_cannot_publish_checkout_dependent_receipts(
    frontend_checkout: Path, arguments: tuple[str, ...]
) -> None:
    assert run_build(frontend_checkout).returncode == 0
    source = frontend_checkout / "src/web/static/js/core/theme.js"
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    result = run_build(frontend_checkout, *arguments)
    assert result.returncode == 1
    assert "CRLF source: js/core/theme.js" in result.stderr


def test_lf_receipts_verify_and_stale_sources_still_fail(frontend_checkout: Path) -> None:
    assert run_build(frontend_checkout).returncode == 0
    static = frontend_checkout / "src/web/static"
    manifest = json.loads((static / "asset-manifest.json").read_text(encoding="utf-8"))
    for source, receipt in manifest["assets"].items():
        assert receipt["source_sha256"] == hashlib.sha256((static / source).read_bytes()).hexdigest()
        assert gzip.decompress((static / (receipt["file"] + ".gz")).read_bytes()) == (
            static / receipt["file"]
        ).read_bytes()
    assert run_build(frontend_checkout, "--check").returncode == 0
    (static / "js/core/theme.js").write_bytes(b"export const theme = 'light';\n")
    result = run_build(frontend_checkout, "--check")
    assert result.returncode == 1
    assert "Stale or missing artifacts" in result.stderr
