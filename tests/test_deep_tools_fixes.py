"""Regression cases for audit tools; no station, network or browser is started."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts import (
    build_diagrams,
    check_frontend_health,
    check_layer_contracts,
    export_logs,
    inspect_web,
)


def test_failed_json_export_preserves_existing_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "diagnostics.json"
    destination.write_text("previous export", encoding="utf-8")
    monkeypatch.setattr(export_logs, "fetch_from_api", lambda *_: None)
    assert export_logs.main(["--json", "--output", str(destination)]) == 1
    assert destination.read_text(encoding="utf-8") == "previous export"


def test_json_error_is_not_a_diagnostic_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "diagnostics.json"
    monkeypatch.setattr(export_logs, "fetch_from_api", lambda *_: {"status": "error", "error": "unavailable"})
    assert export_logs.main(["--json", "--output", str(destination)]) == 1
    assert not destination.exists()


def test_package_contract_includes_unexported_descendant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for relative, source in {
        "src/__init__.py": "",
        "src/application/__init__.py": "",
        "src/application/unexported.py": "import src.web\n",
        "src/web/__init__.py": "",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[[tool.importlinter.contracts]]\nname="application"\ntype="forbidden"\n'
        'source_modules=["src.application"]\nforbidden_modules=["src.web"]\n', encoding="utf-8",
    )
    monkeypatch.setattr(check_layer_contracts, "ROOT", tmp_path)
    assert check_layer_contracts.main() == 1


def test_missing_diagram_source_fails_without_running_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_diagrams, "resolve_archify", lambda: tmp_path / "archify.mjs")
    monkeypatch.setattr(build_diagrams, "DIAGRAMS", [{
        "type": "architecture", "json": tmp_path / "absent.json",
        "html": tmp_path / "old.html", "label": "missing",
    }])
    run = MagicMock()
    monkeypatch.setattr(build_diagrams, "run_step", run)
    assert build_diagrams.main() == 1
    run.assert_not_called()


@pytest.mark.parametrize("failed_view", ["desktop", "mobile"])
async def test_inspection_requires_both_viewports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_view: str,
) -> None:
    browser = SimpleNamespace(close=AsyncMock())
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
    manager = SimpleNamespace(__aenter__=AsyncMock(return_value=playwright), __aexit__=AsyncMock(return_value=False))

    class PlaywrightContext:
        async def __aenter__(self) -> object:
            return await manager.__aenter__()

        async def __aexit__(self, *_: object) -> None:
            await manager.__aexit__()

    monkeypatch.setattr(inspect_web, "async_playwright", PlaywrightContext)
    inspector = inspect_web.WebInspector("http://127.0.0.1:1234", tmp_path)
    results = [{"status": "PASS", "components_detected": {"station": True}},
               {"status": "PASS", "components_detected": {"station": True}}]
    results[0 if failed_view == "desktop" else 1] = {"status": "FAIL", "components_detected": {}}
    monkeypatch.setattr(inspector, "_inspect_viewport", AsyncMock(side_effect=results))
    result = await inspector.inspect()
    assert result["status"] == "FAIL"
    browser.close.assert_awaited_once()


def test_inspection_does_not_accept_absent_station_components() -> None:
    assert not inspect_web.viewport_passed({
        "http_status": 200, "authenticated": True, "station_visible": True, "components_detected": {},
        "errors": {"console": [], "page_exceptions": [], "failed_network": []},
    })


def test_inspection_rejects_login_screen() -> None:
    assert not inspect_web.viewport_passed({
        "http_status": 200, "authenticated": False,
        "station_visible": True,
        "components_detected": dict.fromkeys(inspect_web.REQUIRED_COMPONENTS, True),
        "errors": {"console": [], "page_exceptions": [], "failed_network": []},
    })


def test_authorized_station_passes_only_without_errors() -> None:
    result = {
        "http_status": 200, "authenticated": True, "station_visible": True,
        "components_detected": dict.fromkeys(inspect_web.REQUIRED_COMPONENTS, True),
        "errors": {"console": [], "page_exceptions": [], "failed_network": []},
    }
    assert inspect_web.viewport_passed(result)
    result["errors"]["console"].append("JavaScript error")
    assert not inspect_web.viewport_passed(result)


@pytest.mark.parametrize("failure_kind", ["page", "http", "console", "component", "none"])
async def test_frontend_health_reports_failures_collected_during_inspection(
    failure_kind: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks: dict[str, object] = {}

    def emit_failure(*_: object, **__: object) -> None:
        event, payload = {
            "page": ("pageerror", "Synthetic JavaScript failure"),
            "http": ("response", SimpleNamespace(status=503, url="http://127.0.0.1:1234/api/status")),
            "console": ("console", SimpleNamespace(type="error", text="Synthetic console error")),
        }.get(failure_kind, ("", None))
        callback = callbacks.get(event)
        if callable(callback):
            callback(payload)

    page = SimpleNamespace(
        on=lambda event, callback: callbacks.update({event: callback}),
        goto=AsyncMock(side_effect=emit_failure), wait_for_timeout=AsyncMock(),
        locator=lambda selector: SimpleNamespace(
            count=AsyncMock(return_value=0 if selector == "#themeToggleBtn" and failure_kind == "component" else 1),
            click=AsyncMock(), is_visible=AsyncMock(return_value=True),
        ),
    )
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock())

    @asynccontextmanager
    async def fake_station() -> AsyncIterator[tuple[None, str]]:
        yield None, "http://127.0.0.1:1234"

    @asynccontextmanager
    async def fake_playwright() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))

    monkeypatch.setattr(check_frontend_health, "isolated_frontend_station", fake_station)
    monkeypatch.setattr(check_frontend_health, "async_playwright", fake_playwright)
    monkeypatch.setattr(check_frontend_health, "login_inspection_context", AsyncMock())
    assert await check_frontend_health.check_frontend_health() == (0 if failure_kind == "none" else 1)
    browser.close.assert_awaited_once()
