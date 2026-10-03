"""Small, transport-free observations of command construction (not a test suite)."""

from __future__ import annotations

import asyncio
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from meshcore.commands.device import DeviceCommands  # noqa: E402
from src.repeater_manager import RepeaterManager  # noqa: E402


class CaptureOnly:
    """No connection, dispatcher, service, callback or radio is constructed."""

    def __init__(self) -> None:
        self.frames: list[str] = []

    async def send(self, data: bytes, *args: object, **kwargs: object) -> str:
        self.frames.append(bytes(data).hex())
        return "captured_only"


class TuningCaptureOnly:
    def __init__(self) -> None:
        self._local_config: dict[str, object] = {}
        self.writes: list[dict[str, object]] = []

    async def _write_device(self, mc: object, command: str, *args: object, **kwargs: object) -> None:
        self.writes.append({"command": command, "args": args})


def extract_tuning_method():
    """Compile only the actual method body; do not import config or construct a bridge."""
    source_path = ROOT / "src/admin/local_config_executor.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    cls = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == "LocalConfigExecutor")
    method = next(item for item in cls.body if isinstance(item, ast.AsyncFunctionDef) and item.name == "_apply_advanced_meshcore_settings")
    for argument in method.args.args:
        argument.annotation = None
    method.returns = None
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace[method.name]


async def main() -> None:
    capture = CaptureOnly()
    sdk_observations = []
    for value in (-9, -1, 0, 20):
        before = len(capture.frames)
        try:
            result = await DeviceCommands.set_tx_power(capture, value)
            sdk_observations.append({"tx_power_dbm": value, "result": result, "frame_hex": capture.frames[-1]})
        except (OverflowError, ValueError) as exc:
            sdk_observations.append({"tx_power_dbm": value, "exception": type(exc).__name__, "message": str(exc), "frames_constructed": len(capture.frames) - before})

    manager = RepeaterManager()
    tuning_method = extract_tuning_method()
    tuning_observations = []
    for value in (10, 11, 20):
        tuning = TuningCaptureOnly()
        applied: dict[str, object] = {}
        await tuning_method(tuning, {"rx_delay": value, "airtime_factor": value}, applied, object())
        tuning_observations.append({"input": value, "writes": tuning.writes, "stored": tuning._local_config, "firmware_dimensionless_values": [arg / 1000 for arg in tuning.writes[0]["args"]]})
    cases = [
        ("set_frequency", {"frequency": 868.1}),
        ("set_sf", {"sf": 7}),
        ("set_bw", {"bw": 125}),
        ("set_cr", {"cr": "4/7"}),
        ("set_hop_limit", {"hops": 4}),
        ("set_position", {"lat": 0, "lon": 10, "alt": 15, "fixed": True}),
        ("set_pos_alt", {"alt": 15}),
        ("set_admin_password", {"new_password": "REPRO_DUMMY"}),
        ("acl_add", {"public_key": "11" * 32, "permission": "admin"}),
        ("acl_remove", {"public_key": "11" * 32}),
        ("acl_list", {}),
        ("set_advert_interval", {"advert_interval": 0}),
        ("set_advert_interval", {"advert_interval": 300}),
        ("set_advert_interval", {"advert_interval": 3600}),
        ("set_owner_info", {"owner_info": "REPRO_DUMMY"}),
        ("discover.neighbors", {}),
        ("radio", {"frequency": 868.1, "bandwidth": 125, "sf": 7, "cr": 5}),
    ]
    output = {
        "scope": "construction only; no firmware execution, RF or socket use",
        "sdk_version_source": "installed meshcore 2.3.8",
        "sdk_tx_power": sdk_observations,
        "tuning": tuning_observations,
        "remote_builder": [{"action": action, "params": params, "command": manager.build_repeater_command_payload(action, params)} for action, params in cases],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
