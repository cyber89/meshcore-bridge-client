"""Keep public admin payloads secret-free without mutating internal snapshots."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from src.protocol_types import redact_sensitive_dict, redact_sensitive_mapping


@pytest.mark.parametrize("redactor", [redact_sensitive_dict, redact_sensitive_mapping])
def test_admin_snapshot_redaction_preserves_input_and_nonsecret_data(redactor: Any) -> None:
    snapshot = {
        "status": "partial", "pin": 123456, "password": "private-admin-secret",
        "nested": [{"guest_password": "private-guest-secret", "temperature": 22.5}],
        "dispatched_commands": ["login private-admin-secret", "set admin.password private-new-secret", "set radio 915,125,7,5"],
    }
    original = deepcopy(snapshot)
    assert redactor(snapshot) == {
        "status": "partial", "pin": 0, "has_pin": True, "password": "********",
        "nested": [{"guest_password": "********", "temperature": 22.5}],
        "dispatched_commands": ["login ********", "set admin.password ********", "set radio 915,125,7,5"],
    }
    assert snapshot == original


@pytest.mark.parametrize("value", [None, 42, b"opaque-nonsecret-data"])
def test_general_redactor_keeps_opaque_values_in_nested_lists(value: Any) -> None:
    assert redact_sensitive_dict([value, "login private-secret"]) == [value, "login ********"]
