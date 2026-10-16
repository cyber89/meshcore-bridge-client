"""Passive CLI parsing must preserve LR1121 and existing sub-GHz radio replies."""

import pytest

from src.repeater_manager import RepeaterManager


@pytest.mark.parametrize(
    ("reply", "frequency", "bandwidth", "spreading_factor", "coding_rate"),
    [
        ("> 2400.000,250.000,7,5", 2400.0, 250.0, 7, "4/5"),
        ("2450.000,125.000,8,8", 2450.0, 125.0, 8, "4/8"),
        ("  > 2400, 250, 7, 5  ", 2400.0, 250.0, 7, "4/5"),
        ("> 868.100,250.000,10,5", 868.1, 250.0, 10, "4/5"),
        ("915,125,7,8", 915.0, 125.0, 7, "4/8"),
    ],
)
@pytest.mark.parametrize("command_context", [False, True], ids=["passive", "get-radio"])
def test_radio_reply_preserves_four_digit_frequency_and_modem_fields(
    reply: str,
    frequency: float,
    bandwidth: float,
    spreading_factor: int,
    coding_rate: str,
    command_context: bool,
) -> None:
    manager = RepeaterManager()

    if command_context:
        result = manager.parse_command_response("get radio", reply)
    else:
        result = manager.parse_repeater_telemetry_or_response(reply)

    assert result == {
        "frequency": frequency,
        "bandwidth": bandwidth,
        "spreading_factor": spreading_factor,
        "coding_rate": coding_rate,
    }


def test_radio_error_reply_does_not_update_radio_configuration() -> None:
    assert RepeaterManager().parse_command_response("get radio", "ERR - unavailable") == {}
