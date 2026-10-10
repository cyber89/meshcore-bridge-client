"""Focused regressions for honest skill-helper results and scenario selection."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_helper(skill: str, filename: str) -> ModuleType:
    path = ROOT / ".agents" / "skills" / skill / "scripts" / filename
    spec = importlib.util.spec_from_file_location(f"skill_{skill.replace('-', '_')}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def security_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    helper = load_helper("security-code-auditor", "run_security_audit.py")
    src = tmp_path / "src"
    monkeypatch.setattr(helper, "SRC_DIR", src)
    monkeypatch.setattr(helper, "STATIC_DIR", src / "web" / "static")
    return helper


def write_static_markers(helper: ModuleType) -> None:
    web = helper.SRC_DIR / "web"
    web.mkdir(parents=True)
    (web / "asgi_assets.py").write_text(
        "path.resolve()\nvalue.startswith(prefix)\n", encoding="utf-8"
    )
    utils = helper.STATIC_DIR / "js" / "core" / "utils.js"
    utils.parent.mkdir(parents=True)
    utils.write_text("export function escapeHtml(value) { return value; }\n", encoding="utf-8")


def test_json_stub_is_unverified(security_helper: ModuleType) -> None:
    status, evidence = security_helper.check_safe_json_storage()
    assert status is None
    assert evidence and "manual" in evidence[0].lower()


def test_missing_sources_are_unverified(security_helper: ModuleType) -> None:
    assert security_helper.check_path_traversal()[0] is None
    assert security_helper.check_xss_sanitization()[0] is None


def test_partial_audit_does_not_claim_complete_security(
    security_helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Even a no-op escapeHtml definition satisfies only the presence heuristic.
    write_static_markers(security_helper)
    monkeypatch.setattr(security_helper, "run_bandit_scan", lambda: (True, "Static scan passed."))
    assert security_helper.main() == 2
    output = capsys.readouterr().out
    assert "[NO VERIFICADO] Persistencia JSON" in output
    assert "[INCOMPLETO]" in output
    assert "definición escapeHtml presente" in output
    assert "CERO VULNERABILIDADES" not in output
    assert "Todos los datos dinamicos" not in output
    assert "[PASS] Persistencia JSON" not in output


def test_failed_tool_is_a_failure(
    security_helper: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(security_helper, "run_bandit_scan", lambda: (False, "dependency missing"))
    assert security_helper.main() == 1
    assert "dependency missing" in capsys.readouterr().out


def test_bandit_reports_findings_within_its_scope(
    security_helper: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = subprocess.CompletedProcess(["bandit"], 0, "", "")
    monkeypatch.setattr(security_helper.subprocess, "run", MagicMock(return_value=completed))
    status, evidence = security_helper.run_bandit_scan()
    assert status is True
    assert "media/alta" in evidence
    assert "Cero vulnerabilidades" not in evidence


@pytest.mark.parametrize("scenario", ["flood", "stress"])
def test_unimplemented_scenario_is_rejected(
    scenario: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = load_helper("lora-packet-simulator", "simulate_virtual_mesh.py")
    dispatch = MagicMock()
    monkeypatch.setattr(helper, "run_scenario_multi_hop", dispatch)
    with pytest.raises(SystemExit) as error:
        helper.main(["--scenario", scenario])
    assert error.value.code == 2
    assert "no implementado" in capsys.readouterr().err
    dispatch.assert_not_called()


def test_invalid_node_count_does_not_run_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_helper("lora-packet-simulator", "simulate_virtual_mesh.py")
    dispatch = MagicMock()
    monkeypatch.setattr(helper, "run_scenario_multi_hop", dispatch)
    with pytest.raises(SystemExit) as error:
        helper.main(["--nodes", "0"])
    assert error.value.code == 2
    dispatch.assert_not_called()


def test_multi_hop_dispatch_keeps_requested_node_count(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_helper("lora-packet-simulator", "simulate_virtual_mesh.py")
    sentinel: Any = object()
    dispatch = MagicMock(return_value=sentinel)
    runner = MagicMock()
    monkeypatch.setattr(helper, "run_scenario_multi_hop", dispatch)
    monkeypatch.setattr(helper.asyncio, "run", runner)
    helper.main(["--scenario", "multi_hop", "--nodes", "3"])
    dispatch.assert_called_once_with(3)
    runner.assert_called_once_with(sentinel)


def test_api_helper_isolates_storage_and_restores_caller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import config

    helper = load_helper("api-design-testing", "validate_api_contract.py")
    operator_path = tmp_path / "operator-channels.json"
    operator_path.write_text('{"sentinel": true}', encoding="utf-8")
    monkeypatch.setenv("CHANNELS_STORAGE_PATH", str(operator_path))
    monkeypatch.setattr(config, "CHANNELS_JSON_PATH", str(operator_path))
    monkeypatch.setattr(config, "BRIDGE_API_KEY", "operator-secret")
    dotenv_reader = MagicMock(side_effect=AssertionError("operator dotenv read"))
    monkeypatch.setattr("dotenv.load_dotenv", dotenv_reader)
    original_environment = dict(os.environ)
    original_sys_path = list(helper.sys.path)

    with helper.isolated_environment() as data_dir:
        from src.web.api_router import WebAPIRouter

        assert config.BRIDGE_API_KEY == ""
        assert Path(config.CHANNELS_JSON_PATH).parent == data_dir
        assert Path(os.environ["CHANNELS_STORAGE_PATH"]).parent == data_dir
        router = WebAPIRouter(helper.MockBridge())
        try:
            assert router.map_tile_service.base_dir == data_dir
            assert Path(router.channels_ctrl.channels_file).parent == data_dir
        finally:
            router.map_tile_service.close()
        assert data_dir.is_dir()

    assert not data_dir.exists()
    assert config.BRIDGE_API_KEY == "operator-secret"
    assert config.CHANNELS_JSON_PATH == str(operator_path)
    assert dict(os.environ) == original_environment
    assert helper.sys.path == original_sys_path
    dotenv_reader.assert_not_called()
    assert operator_path.read_text(encoding="utf-8") == '{"sentinel": true}'


def test_api_helper_uses_current_contracts_without_operator_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import builtins

    import config
    from src.web.map_tile_service import MapTileService

    helper = load_helper("api-design-testing", "validate_api_contract.py")
    operator_dir = tmp_path / "operator"
    operator_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(operator_dir))
    monkeypatch.setenv("NODE_REGISTRY_STORAGE_PATH", str(operator_dir / "nodes.json"))
    monkeypatch.setenv("CHANNELS_STORAGE_PATH", str(operator_dir / "channels.json"))
    monkeypatch.setattr(config, "DATA_DIR", str(operator_dir))
    real_open = builtins.open
    real_map_init = MapTileService.__init__
    map_roots: list[Path] = []

    def guarded_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, (str, os.PathLike)):
            path = Path(file).resolve()
            assert path.name != ".env", "operator dotenv must never be opened"
            assert not path.is_relative_to(operator_dir), "operator state must never be opened"
        return real_open(file, *args, **kwargs)

    def guarded_map_init(self: Any, data_dir: Any = None) -> None:
        assert data_dir is not None, "default map path would read operator maps"
        map_roots.append(Path(data_dir))
        real_map_init(self, data_dir=data_dir)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(MapTileService, "__init__", guarded_map_init)
    assert asyncio.run(helper.run_api_tests()) is True
    output = capsys.readouterr().out
    assert "[FAIL]" not in output
    assert "HTTP 201 (expected 201)" in output
    assert "HTTP 400 (expected 400)" in output
    assert map_roots and all(not path.exists() for path in map_roots)
    assert not list(operator_dir.iterdir())


def test_api_helper_failure_returns_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_helper("api-design-testing", "validate_api_contract.py")

    async def failed_cases() -> bool:
        return False

    monkeypatch.setattr(helper, "run_api_tests", failed_cases)
    assert helper.main() == 1
