#!/usr/bin/env python3
"""Simulador de Malla LoRa y Replay de Paquetes en Memoria para MeshCore Bridge.

Permite probar el pipeline de decodificación, deduplicación y cálculo de LQI
sin requerir hardware físico ni emitir paquetes de radio reales.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Any

# Asegurar que el root del proyecto esté en sys.path y encoding UTF-8
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../")))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.deduplicator import PacketDeduplicator
from src.lqi_engine import LinkQualityEngine
from src.protocol_types import FirmwareAdvertType
from src.virtual_mesh_adapter import VirtualMeshAdapter


class VirtualSerialChannel:
    """Canal serie bidireccional virtual basado en asyncio.Queue."""

    def __init__(self) -> None:
        self.to_bridge: asyncio.Queue[bytes] = asyncio.Queue()
        self.from_bridge: asyncio.Queue[bytes] = asyncio.Queue()

    async def emit_to_bridge(self, frame: bytes) -> None:
        await self.to_bridge.put(frame)

    async def read_from_bridge(self, timeout: float = 1.0) -> bytes | None:
        try:
            return await asyncio.wait_for(self.from_bridge.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


def build_mock_advert_payload(
    name: str,
    adv_type: FirmwareAdvertType = FirmwareAdvertType.CHAT,
    battery: int = 95,
) -> dict[str, Any]:
    """Genera una estructura de anuncio sintética."""
    return {
        "type": adv_type.name,
        "adv_type": int(adv_type.value),
        "name": name,
        "battery": battery,
        "timestamp": time.time(),
    }


async def run_scenario_multi_hop(num_nodes: int = 3) -> None:
    print(f"📡 [SIMULADOR] Iniciando escenario multi-hop con {num_nodes} nodos virtuales...")
    dedup = PacketDeduplicator(window_seconds=10.0, max_entries=500)
    _adapter = VirtualMeshAdapter()
    print(f"  🔧 Adaptador virtual listo: {_adapter.__class__.__name__}")

    node_scores: dict[str, tuple[float, str]] = {}

    # 1. Anuncio del Repetidor Central
    repeater_key = "a1b2c3d4e5f60001"
    print(f"  🏢 Emulando anuncio de Repetidor: 'Torre Central' ({repeater_key})")
    lqi_rep = LinkQualityEngine.compute_instant_lqi(snr=9.5, rssi=-65.0, hops=0)
    status_rep = LinkQualityEngine.classify_lqi_status(lqi_rep)
    node_scores[repeater_key] = (lqi_rep, status_rep)
    await dedup.is_duplicate(f"adv_{repeater_key}_{int(time.time())}")

    # 2. Emisión de clientes a través del repetidor
    for i in range(1, num_nodes + 1):
        client_key = f"beefcafe0000000{i}"
        client_name = f"VirtualClient_{i}"
        rssi = -75.0 - (i * 3)
        snr = 8.0 - (i * 0.5)

        lqi_val = LinkQualityEngine.compute_instant_lqi(snr=snr, rssi=rssi, hops=1)
        status_val = LinkQualityEngine.classify_lqi_status(lqi_val)
        node_scores[client_key] = (lqi_val, status_val)

        print(f"  👤 Nodo Cliente #{i}: '{client_name}' ({client_key}) -> RSSI: {rssi:.1f} dBm, SNR: {snr:.1f} dB, LQI: {lqi_val:.1f}% ({status_val})")

        # Simular paquete de texto
        pkt_hash = f"msg_{client_key}_{i}"
        is_dup = await dedup.is_duplicate(pkt_hash)
        assert not is_dup, "El paquete no debe ser duplicado en primera instancia"

        # Simular retransmisión por repetidor (debe ser deduplicado)
        is_dup_retransmit = await dedup.is_duplicate(pkt_hash)
        assert is_dup_retransmit, "La retransmisión por repetidor debe ser detectada como duplicada"

    print(f"\n📊 [SIMULADOR] Simulación completada con éxito. Nodos evaluados en LQI: {len(node_scores)}")
    for k, (score, st) in node_scores.items():
        print(f"   • {k[:14]}... -> LQI: {score:.1f}% [{st}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de Malla LoRa en Memoria")
    parser.add_argument("--scenario", choices=["multi_hop", "flood", "stress"], default="multi_hop")
    parser.add_argument("--nodes", type=int, default=4, help="Número de nodos a simular")
    args = parser.parse_args()

    asyncio.run(run_scenario_multi_hop(args.nodes))


if __name__ == "__main__":
    main()
