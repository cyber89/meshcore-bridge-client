"""Reproduce the advert-handler exception without starting a bridge or transport."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

with patch("dotenv.load_dotenv", return_value=False):
    from src.routers.advert_handler import AdvertHandler
    from src.routers.base import RxMeta


async def main() -> None:
    payload = {"public_key": "22" * 32, "type": 2, "name": "Synthetic repeater"}
    registry = Mock()
    meta = RxMeta(
        ev_type_str="ADVERTISEMENT", ev_upper="ADVERTISEMENT",
        sender=payload["public_key"], sender_name=payload["name"], text="",
        channel_idx=0, hops=0, effective_rssi=-80, effective_snr=5.0,
        effective_hops=0, is_local_sender=False,
    )
    observation = {
        "base_head": "81f4260eccf9bdec6c6f7ba9caca5322997f6eeb",
        "scope": "Direct handler call, mock registry, no transport/services/dotenv",
        "input": payload,
    }
    try:
        await AdvertHandler().handle(SimpleNamespace(node_registry=registry), payload, meta, payload)
        observation.update(reproduced=False, outcome="No exception")
    except NameError as error:
        observation.update(reproduced=True, exception=type(error).__name__, message=str(error))
    observation["registry_discover_calls"] = registry.discover_node.call_count
    output = Path(__file__).with_name("reproduction.json")
    output.write_text(json.dumps(observation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(observation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
