"""The reference inspector must locate real source lines without requiring a tree."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def inspector_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py"
    )
    spec = importlib.util.spec_from_file_location("meshcore_inspector_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_inspects_one_header_and_reports_the_define_line(inspector_module, tmp_path):
    header = tmp_path / "advert.h"
    header.write_text("// header\n\n   #define ADV_TYPE_CHAT 1\n", encoding="utf-8")
    result = inspector_module.CSourceInspector([header]).scan_all()
    assert [(item.name, item.value, item.line_number) for item in result.defines] == [
        ("ADV_TYPE_CHAT", "1", 3)
    ]


def test_inspects_one_sdk_python_file(inspector_module, tmp_path):
    source = tmp_path / "events.py"
    source.write_text("class EventType:\n    pass\n", encoding="utf-8")
    result = inspector_module.CSourceInspector([source]).scan_all()
    assert result.python_classes == [
        {"name": "EventType", "bases": "", "file_path": str(source), "line_number": 1}
    ]


def test_directory_define_does_not_count_the_preceding_blank_line(inspector_module, tmp_path):
    (tmp_path / "advert.h").write_text("\n\n#define ADV_TYPE_CHAT 1\n", encoding="utf-8")
    result = inspector_module.CSourceInspector([tmp_path]).scan_all()
    assert result.defines[0].line_number == 3
