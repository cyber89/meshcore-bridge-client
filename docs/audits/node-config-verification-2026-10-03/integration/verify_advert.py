"""Recheck discovery after the historical NameError fix, without transport."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
with patch("dotenv.load_dotenv", return_value=False):
    from src.routers.advert_handler import AdvertHandler
    from src.routers.base import RxMeta


async def main() -> None:
    observations = []
    for event, timestamp in (
        ("ADVERTISEMENT", None), ("ADVERTISEMENT", "not-numeric"),
        ("ADVERTISEMENT", "1791000000"), ("NEXT_CONTACT", "1791000000"),
    ):
        payload = {"public_key": "22" * 32, "type": 2, "name": "SyntheticRepeater"}
        if timestamp is not None:
            payload["last_advert"] = timestamp
        registry = Mock()
        registry.discover_node.return_value = (False, None)
        registry.add_or_update.return_value = SimpleNamespace(to_dict=lambda: {})
        ctx = SimpleNamespace(node_registry=registry, _handle_mesh_telemetry_msg=Mock())
        meta = RxMeta(
            ev_type_str=event, ev_upper=event, sender=payload["public_key"],
            sender_name=payload["name"], text="", channel_idx=0, hops=0,
            effective_rssi=-80, effective_snr=5.0, effective_hops=0,
            is_local_sender=False,
        )
        await AdvertHandler().handle(ctx, payload, meta, payload)
        update = registry.add_or_update.call_args.args[1]
        observations.append({
            "event": event, "input_last_advert": timestamp,
            "discover_calls": registry.discover_node.call_count,
            "update_calls": registry.add_or_update.call_count,
            "last_advert": update.last_advert,
            "last_advert_heard_at_present": update.last_advert_heard_at is not None,
        })
        assert registry.discover_node.call_count == 1
        assert update.last_advert == (1791000000.0 if timestamp == "1791000000" else None)
        assert (update.last_advert_heard_at is None) == (event == "NEXT_CONTACT")
    output = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": "Real handler; mock registry; dotenv blocked; no RF, MQTT or filesystem persistence",
        "passed": len(observations), "observations": observations,
    }
    Path(__file__).with_name("advert-results.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
