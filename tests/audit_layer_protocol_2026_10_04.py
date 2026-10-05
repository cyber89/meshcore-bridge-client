"""Explicit isolated audit harness; not part of pytest's automatic collection.

Run: .venv/Scripts/python.exe tests/audit_layer_protocol_2026_10_04.py
Documents current defects rather than asserting that production is correct.
No radio, broker, application server or operator configuration is opened.
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL = "ab" * 32
REMOTE = "cd" * 32
SOURCES = {
    "PI-01": ["src/admin/repeater_executor.py:1080"],
    "PI-02": ["src/admin_handler.py:371", "src/admin/cli_command_executor.py:125"],
    "PI-03": ["src/admin_handler.py:415", "src/admin_handler.py:423"],
    "PI-04": ["src/admin_handler.py:394"],
    "PI-05": ["src/admin/repeater_executor.py:862"],
    "PI-06": ["src/admin/repeater_executor.py:199"],
    "PI-07": ["src/sensor_decoder.py:402", "src/sensor_decoder.py:434"],
    "PI-08": ["src/sensor_decoder.py:19", "src/sensor_decoder.py:204"],
    "PI-09": ["src/admin/cli_command_executor.py:449"],
    "PI-10": ["src/admin/cli_command_executor.py:223"],
    "PI-11": ["src/admin/cli_command_executor.py:171"],
    "PI-12": ["src/admin/cli_command_executor.py:956"],
    "PI-13": ["src/admin/local_config_executor.py:850", "src/admin/local_config_executor.py:906"],
}


async def audit() -> dict:
    with tempfile.TemporaryDirectory(prefix="meshcore-protocol-audit-") as isolated:
        for name in ("DATA_DIR", "LOG_DIR"):
            os.environ[name] = isolated
        with patch("dotenv.load_dotenv", return_value=False):
            from meshcore.events import Event, EventType

            from src.admin_handler import AdminCommandHandler, AdminContext
            from src.contact_manager import NodeContactUpdate, NodeRegistry
            from src.repeater_manager import RepeaterManager
            from src.sensor_decoder import CayenneLPPDecoder, extract_telemetry_fields

        def station(role="REPEATER"):
            registry = NodeRegistry()
            registry.set_local_pubkey(LOCAL)
            registry.add_or_update(REMOTE, NodeContactUpdate(name="Audit", role=role))
            mc = SimpleNamespace(self_info={"public_key": LOCAL},
                                 contacts={REMOTE: {"public_key": REMOTE, "type": 2 if role == "REPEATER" else 1}},
                                 commands=SimpleNamespace())
            mqtt = MagicMock()
            ctx = AdminContext(lambda: mc, registry,
                               RepeaterManager(min_cmd_interval_s=0, min_telemetry_interval_s=0),
                               mqtt, AsyncMock())
            return AdminCommandHandler(ctx), mc, mqtt, registry

        findings = []

        def record(identifier, expected, observed, reproduced):
            assert reproduced, f"Defect {identifier} did not reproduce"
            findings.append({"id": identifier, "expected": expected, "observed": observed,
                             "priority": "P1" if identifier == "PI-02" else "P2",
                             "sources": SOURCES[identifier], "reproduced": True,
                             "command": ".venv/Scripts/python.exe tests/audit_layer_protocol_2026_10_04.py",
                             "environment": "isolated mocks / memory"})

        # Official SDK returns {tag: echo_timestamp, data: remote_timestamp_le + features}.
        handler, mc, _, registry = station()
        sender_ts, remote_ts = 1704067200, 1791072000
        mc.commands.req_basic_sync = AsyncMock(return_value={
            "tag": sender_ts.to_bytes(4, "little").hex(),
            "data": remote_ts.to_bytes(4, "little").hex() + "00"})
        result = await handler.handle({"action": "req_clock", "target_node": REMOTE})
        remote_date = datetime.fromtimestamp(remote_ts, timezone.utc).strftime("%H:%M - %d/%m/%Y UTC")
        sender_date = datetime.fromtimestamp(sender_ts, timezone.utc).strftime("%H:%M - %d/%m/%Y UTC")
        record("PI-01", remote_date,
               {"clock": result.get("clock"), "registry_clock": registry.get_node(REMOTE).clock},
               result.get("clock") == sender_date and result.get("clock") != remote_date)

        handler, mc, mqtt, _ = station()
        handler._local_config["pin"] = 654321
        result = await handler.handle({"action": "get_config"})
        payload = json.loads(mqtt.publish_safe.call_args.args[1])
        record("PI-02", "PIN redacted in MQTT admin/status",
               {"returned_pin": result["config"].get("pin"), "published_pin": payload["config"].get("pin")},
               payload["config"].get("pin") == 654321)

        # The local executor is strict, but handler int() erases the invalid type first.
        handler, mc, _, _ = station()
        mc.commands.set_autoadd_config = AsyncMock(return_value=Event(EventType.OK, {}))
        mc.commands.set_path_hash_mode = AsyncMock(return_value=Event(EventType.OK, {}))
        auto = await handler.handle({"action": "set_autoadd_config", "flags": True})
        path = await handler.handle({"action": "set_path_hash_mode", "mode": 1.9})
        record("PI-03", "422; zero writes for bool flags and fractional mode",
               {"autoadd": auto, "path_hash": path,
                "autoadd_sdk_args": list(mc.commands.set_autoadd_config.call_args.args),
                "path_hash_sdk_args": list(mc.commands.set_path_hash_mode.call_args.args)},
               auto["status"] == "ok" and path["status"] == "ok")

        handler, mc, _, _ = station()
        mc.commands.set_custom_var = AsyncMock(return_value=Event(EventType.OK, {}))
        result = await handler.handle({"action": "set_custom_vars", "vars": {"gps": "0", "bad,key": "1"}})
        record("PI-04", "Prevalidate all entries before first SDK write, or report applied partial values",
               {"response": result, "writes": [list(call.args) for call in mc.commands.set_custom_var.call_args_list],
                "cached_custom_vars": handler._local_config.get("custom_vars")},
               result["status"] == "error" and mc.commands.set_custom_var.await_count == 1 and "applied" not in result)

        async def no_response(*args, **kwargs):
            return None

        async def no_wait(seconds):
            return None

        # Exercise the real batch implementation, replacing only transport / clock waiting.
        with patch("src.admin.repeater_executor.asyncio.sleep", no_wait):
            handler, mc, _, _ = station()
            mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
            handler._repeater_executor._wait_for_repeater_response = no_response
            result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
            record("PI-05", "error / timeout when no remote result arrived",
                   {"response": result, "send_count": mc.commands.send_cmd.await_count},
                   result["status"] == "ok" and result["responses"] == {} and result["telemetry"] == {})

            handler, mc, _, _ = station("CLIENT")
            mc.commands.send_cmd = AsyncMock(return_value=Event(EventType.MSG_SENT, {}))
            handler._repeater_executor._wait_for_repeater_response = no_response
            result = await handler.handle({"action": "refresh_telemetry", "target_node": REMOTE})
            record("PI-06", "Reject repeater CLI batch for known CLIENT; zero admin RF calls",
                   {"status": result["status"], "send_count": mc.commands.send_cmd.await_count},
                   result["status"] == "ok" and mc.commands.send_cmd.await_count == 5)

        # Explicit units must take precedence over magnitude heuristics.
        scalar = extract_telemetry_fields({"solar_mv": 100, "fixed_position": "false"})
        record("PI-07", {"solar_v": 0.1, "fixed_position": False}, scalar,
               scalar.get("solar_v") == 100.0 and scalar.get("fixed_position") is True)

        readings, summary = CayenneLPPDecoder.decode(bytes.fromhex("01750064026700fa"))
        record("PI-08", "LPP current 117 (0.1 A), then temperature 103 (25 C)",
               {"readings": [{"type": item.data_type, "value": item.value} for item in readings], "summary": summary},
               readings[0].type_name == "unknown" and "temperature_c" not in summary)

        handler, mc, _, _ = station()
        mc.commands.get_time = AsyncMock(return_value=Event(EventType.ERROR, {}))
        result = await handler.handle({"action": "clock"})
        record("PI-09", "Node clock unknown / error when firmware query fails",
               {"status": result["status"], "result": result["result"]},
               result["status"] == "ok" and "Hora del Nodo:" in result["result"])

        handler, mc, _, _ = station()
        result = await handler.handle({"action": "acl"})
        record("PI-10", "Companion ACL unsupported / actual device evidence; do not invent authentication",
               {"status": result["status"], "result": result["result"]},
               "Autenticación por PIN activa" in result["result"] and not result["config"]["has_pin"])

        handler, mc, _, _ = station()
        handler._local_config["rx_delay"] = 10
        result = await handler.handle({"action": "tuning"})
        record("PI-11", "rx_delay is dimensionless base factor, firmware RX delay depends on airtime and score",
               result["result"], "Retardo RX: 10s" in result["result"])

        handler, mc, _, _ = station()
        result = await handler.handle({"action": "set tx abc"})
        record("PI-12", "Invalid numeric CLI input must carry status=error / 422",
               {"status": result["status"], "result": result["result"]},
               result["status"] == "ok" and "inválido" in result["result"])

        handler, mc, _, _ = station()
        wire = {}

        async def official_radio_conversion(freq, bw, sf, cr, repeat):
            # commands/device.py set_radio serializes integer Hz from MHz/kHz * 1000.
            wire["frequency"] = int(freq * 1000) / 1000
            wire["bandwidth"] = int(bw * 1000) / 1000
            return Event(EventType.OK, {})

        mc.commands.set_radio = AsyncMock(side_effect=official_radio_conversion)
        params = {"frequency": 915.0009, "bandwidth": 250.0009, "spreading_factor": 11, "coding_rate": 5}
        result = await handler.handle({"action": "set_local_config", "params": params})
        record("PI-13", "Reported applied fields equal the effective values serialized by the official SDK",
               {"status": result["status"], "applied": result["applied"], "wire_effective": wire},
               result["status"] == "ok" and result["applied"]["frequency"] != wire["frequency"])

        python_scope = list((ROOT / "src/admin").glob("*.py")) + [ROOT / p for p in (
            "src/admin_handler.py", "src/repeater_manager.py", "src/protocol_types.py", "src/sensor_decoder.py",
            "src/target_resolver.py", "src/mqtt_client.py", "src/mqtt_dispatcher.py", "config.py", "src/__main__.py")]
        metrics = []
        for path in python_scope:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            methods = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    branches = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)) for n in ast.walk(node))
                    methods.append({"name": node.name, "line": node.lineno, "lines": node.end_lineno - node.lineno + 1,
                                    "branch_nodes": branches})
            metrics.append({"path": path.relative_to(ROOT).as_posix(), "lines": len(text.splitlines()),
                            "classes": [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)],
                            "methods": methods})
        return {"baseline": "c9b2d3ce4c1776f2d0603f57481df2395d84ea2e", "findings": findings,
                "python_inventory": metrics,
                "limits": "Only deterministic mocks and static metrics; no hardware interoperability or load certification."}


if __name__ == "__main__":
    result = asyncio.run(audit())
    destination = ROOT / "docs/audits/layers-2026-10-04/protocol-integration.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"reproduced": len(result["findings"]), "evidence": str(destination)}, ensure_ascii=False))
