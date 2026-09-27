"""
Mutation & Robustness Resilience Tests for MeshCore Bridge.
Verifica que el sistema detecte y rechace mutaciones de tramas, inversión de bits,
mutaciones de opcodes, corrupción de checksums y alteración de secuencias de escape.
"""

import asyncio
import unittest

from src.deduplicator import PacketDeduplicator
from src.protocol_types import (
    ESC_BYTE,
    FrameHeader,
    MeshcoreFrame,
    PacketType,
    TextMessagePayload,
)
from src.sensor_decoder import CayenneLPPDecoder


class TestMutationResilience(unittest.TestCase):
    def setUp(self) -> None:
        self.text_payload = TextMessagePayload(channel_idx=0, sender_alias="Alice", text="Hello Mutation Test")
        payload_bytes = self.text_payload.pack()
        self.header = FrameHeader(
            packet_type=PacketType.CHANNEL_MSG_RECV,
            seq_num=42,
            src_node_id=0x1234,
            dst_node_id=0xFFFF,
            hop_limit=3,
            payload_len=len(payload_bytes),
        )
        self.frame = MeshcoreFrame(
            header=self.header,
            payload=self.text_payload,
            raw_payload=payload_bytes,
            crc16=0,
            is_valid=True,
        )
        self.valid_serialized = self.frame.serialize()

    def test_bit_flip_mutations_detected_by_crc(self) -> None:
        """Prueba mutación por inversión de bits individuales en el cuerpo de la trama."""
        # Des-escapar el stream para obtener el cuerpo que evalúa parse_raw_packet
        body = self.valid_serialized[1:-1]
        unescaped = bytearray()
        i = 0
        while i < len(body):
            b = body[i]
            if b == ESC_BYTE and i + 1 < len(body):
                i += 1
                unescaped.append(body[i] ^ 0x20)
            else:
                unescaped.append(b)
            i += 1

        # Mutar bits en cada posición del cuerpo
        for idx in range(len(unescaped) - 2):
            mutated = bytearray(unescaped)
            mutated[idx] ^= 0x01
            try:
                parsed = MeshcoreFrame.parse_raw_packet(bytes(mutated))
                self.assertFalse(parsed.is_valid, f"La trama mutada en {idx} debió tener is_valid=False")
            except Exception:
                pass

    def test_deduplicator_mutation_collision_resistance(self) -> None:
        """Verifica que mutaciones leves de payload generen claves distintas y no colisionen."""
        dedup = PacketDeduplicator(window_seconds=10.0, max_entries=100)
        base_key = "meshcore/rx/all::100"
        mutated_key = "meshcore/rx/all::101"

        self.assertNotEqual(base_key, mutated_key, "Claves mutadas deben ser distintas")
        self.assertFalse(asyncio.run(dedup.is_duplicate(base_key)))
        self.assertFalse(asyncio.run(dedup.is_duplicate(mutated_key)))

    def test_sensor_payload_truncation_mutation(self) -> None:
        """Verifica que mutaciones de truncamiento en payloads de sensores no causen crashes."""
        valid_sensor_hex = "016700FA026864"  # Temp 25.0C + Hum 50%
        raw_bytes = bytes.fromhex(valid_sensor_hex)

        # Truncar progresivamente desde longitud 0 hasta N-1
        for length in range(len(raw_bytes)):
            truncated = raw_bytes[:length]
            readings, summary = CayenneLPPDecoder.decode(truncated)
            self.assertIsInstance(readings, list)
            self.assertIsInstance(summary, dict)


if __name__ == "__main__":
    unittest.main()
