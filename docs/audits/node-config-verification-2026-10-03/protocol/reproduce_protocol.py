"""Transport-free observation of current real builders and SDK serialization.

Only this evidence directory is written. No bridge, dotenv, hardware, socket,
broker, transport, or firmware is initialized. AST extraction isolates one real
production method; it does not claim integration or firmware execution.
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import importlib.metadata
import io
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

# src/__init__.py eagerly imports bridge_core/config. Install a namespace-only
# package so importing the real builder cannot execute that initializer.
isolated_src = types.ModuleType("src")
isolated_src.__path__ = [str(ROOT / "src")]
sys.modules["src"] = isolated_src
blocked_dotenv_reads = []


def guarded_open(original):
    def open_without_operational_env(file, *args, **kwargs):
        if isinstance(file, (str, bytes, Path)) and Path(file).name == ".env":
            blocked_dotenv_reads.append("blocked .env")
            raise PermissionError("Operational .env access prohibited by this harness")
        return original(file, *args, **kwargs)
    return open_without_operational_env


builtins.open = guarded_open(builtins.open)
io.open = guarded_open(io.open)

from meshcore.commands.device import DeviceCommands
from src.repeater_manager import RepeaterManager


class CaptureOnly:
    def __init__(self):
        self.frames = []

    async def send(self, data, *args, **kwargs):
        self.frames.append(bytes(data).hex())
        return "captured_only"


class TuningOnly:
    def __init__(self):
        self._local_config = {}
        self.writes = []

    async def _write_device(self, mc, command, *args, **kwargs):
        self.writes.append({"command": command, "args": args})


def isolated_method():
    path = ROOT / "src/admin/local_config_executor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "LocalConfigExecutor")
    method = next(x for x in cls.body if isinstance(x, ast.AsyncFunctionDef) and x.name == "_apply_advanced_meshcore_settings")
    for arg in method.args.args:
        arg.annotation = None
    method.returns = None
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[method.name]


async def main():
    capture = CaptureOnly()
    sdk = []
    for value in (-9, -1, 0, 20):
        before = len(capture.frames)
        try:
            result = await DeviceCommands.set_tx_power(capture, value)
            sdk.append({"input_dbm": value, "result": result, "frame": capture.frames[-1]})
        except Exception as error:
            sdk.append({"input_dbm": value, "exception": type(error).__name__, "message": str(error), "frames": len(capture.frames) - before})
    tuning = []
    for value in (10, 11, 20):
        instance = TuningOnly()
        applied = {}
        await isolated_method()(instance, {"rx_delay": value, "airtime_factor": value}, applied, object())
        tuning.append({"input": value, "writes": instance.writes, "firmware_decoded": [x / 1000 for x in instance.writes[0]["args"]]})
    cases = [
        ("set_frequency", {"frequency": 868.1}), ("set_sf", {"sf": 7}),
        ("set_bw", {"bw": 125}), ("set_cr", {"cr": "4/7"}),
        ("set_position", {"lat": 0, "lon": 10, "alt": 15, "fixed": True}),
        ("set_hop_limit", {"hops": 4}), ("set_pos_alt", {"alt": 15}),
        ("set_radio", {"frequency": 868.1, "bandwidth": 125, "sf": 7, "cr": 7}),
        ("set_radio", {"frequency": 868.1, "bandwidth": 125, "sf": 7, "cr": "INVALID"}),
        ("set_radio", {"frequency": 868.1, "bandwidth": 125, "sf": 7, "cr": "99/7"}),
        ("radio", {"frequency": 868.1, "bandwidth": 125, "sf": 7, "cr": 7}),
        ("set_lat", {"lat": 0}), ("set_lon", {"lon": 0}),
        ("set_lat", {"lat": 100}), ("set_lon", {"lon": "nan"}),
        ("lat", {"lat": 41}), ("lon", {"lon": -73}),
        ("set_owner_info", {"owner_info": "REPRO_DUMMY"}),
        ("set_admin_password", {"new_password": "REPRO_DUMMY"}),
        ("acl_add", {"public_key": "11" * 32, "permission": "admin"}),
        ("acl_add", {"public_key": "11" * 32, "permission": "guest"}),
        ("acl_add", {"public_key": "11" * 32, "permission": "read"}),
        ("acl_remove", {"public_key": "11" * 32}),
        ("setperm", {"public_key": "11" * 32, "permission": 3}),
        ("setperm", {"public_key": "xx", "permission": 999}),
        ("acl_list", {}), ("get_acl", {}), ("status", {}),
        ("battery", {}), ("discover.neighbors", {}), ("uptime", {}),
        ("help", {}), ("set_repeat_enabled", {"repeat_enabled": False}),
        ("set_guest_password", {"guest_password": "REPRO_DUMMY"}),
        ("set_latitude", {"latitude": 41}), ("set_longitude", {"longitude": -73}),
        ("set_region", {"region": "TEST"}),
    ]
    for value in (0, 30, 60, 61, 120, 239, 240, 241, 300, 600, 1200, 3600, 14400, -1, "INVALID"):
        cases.append(("set_advert_interval", {"advert_interval": value}))
    for value in (0, 1, 2, 3, 168, 169, -1, "INVALID"):
        cases.append(("set_flood_advert_interval", {"flood_advert_interval": value}))
    manager = RepeaterManager()
    output = {
        "scope": "constructors only; fake send captures bytes; no RF or firmware execution",
        "sdk_version": importlib.metadata.version("meshcore"),
        "isolation": {"bridge_or_config_imported": any(x in sys.modules for x in ("config", "src.bridge_core")), "dotenv_reads_blocked": blocked_dotenv_reads},
        "sdk_tx": sdk, "tuning": tuning,
        "builders": [{"action": a, "params": p, "actual_command": manager.build_repeater_command_payload(a, p)} for a, p in cases],
    }
    target = Path(__file__).with_name("reproduction.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sdk_cases": len(sdk), "tuning_cases": len(tuning), "builder_cases": len(cases), "output": str(target)}))


if __name__ == "__main__":
    asyncio.run(main())
