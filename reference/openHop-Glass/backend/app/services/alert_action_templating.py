from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}")


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _resolve_path_value(context: Mapping[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                raise KeyError(path)
            current = current[part]
            continue
        raise KeyError(path)
    return _json_safe_value(current)


def render_template_text(template: str | None, context: Mapping[str, Any]) -> str | None:
    if template is None:
        return None

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        value = _resolve_path_value(context, token)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return str(value)
        return str(value)

    return PLACEHOLDER_PATTERN.sub(_replace, template)


def render_template_value(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template_text(value, context)
    if isinstance(value, dict):
        return {
            str(key): render_template_value(item, context)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [render_template_value(item, context) for item in value]
    if isinstance(value, tuple):
        return [render_template_value(item, context) for item in value]
    return _json_safe_value(value)

