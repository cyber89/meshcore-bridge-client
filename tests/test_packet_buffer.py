"""
Unit tests for PacketBuffer (In-Memory Circular Buffer, Wireshark PCAP, CSV and JSON Exports).
"""

from __future__ import annotations

import json
import struct
import unittest

from src.packet_buffer import CapturedPacket, PacketBuffer


class TestPacketBuffer(unittest.TestCase):
    def setUp(self) -> None:
        self.buffer = PacketBuffer(max_packets=10)

    def test_record_packet_and_circular_limit(self) -> None:
        """Verifica el registro correcto y la expulsión circular al superar max_packets."""
        self.assertEqual(len(self.buffer._buffer), 0)

        # Grabar 12 paquetes en un buffer de tamaño 10
        for i in range(1, 13):
            pkt = self.buffer.record(
                direction="rx" if i % 2 == 0 else "tx",
                channel_idx=0,
                packet_type="TEXT_MESSAGE",
                sender=f"node_{i:04d}",
                target="broadcast",
                text=f"Mensaje {i}",
                rssi=-60 - i,
                snr=10.0 - (i * 0.5),
                raw_bytes=f"raw_{i}".encode("utf-8"),
            )
            self.assertIsNotNone(pkt)
            self.assertEqual(pkt.packet_id, i)

        # Debe contener solo los últimos 10 (del ID 3 al 12)
        self.assertEqual(len(self.buffer._buffer), 10)
        first_pkt = self.buffer._buffer[0]
        last_pkt = self.buffer._buffer[-1]
        self.assertEqual(first_pkt.packet_id, 3)
        self.assertEqual(last_pkt.packet_id, 12)

    def test_filtering_and_pagination(self) -> None:
        """Verifica la paginación y filtrado por dirección y tipo de trama."""
        # Insertar tramas variadas
        self.buffer.record("rx", channel_idx=0, packet_type="TEXT_MESSAGE", text="Hola 1")
        self.buffer.record("tx", channel_idx=0, packet_type="TEXT_MESSAGE", text="Hola 2")
        self.buffer.record("rx", channel_idx=1, packet_type="TELEMETRY", text="Telem 1")
        self.buffer.record("rx", channel_idx=0, packet_type="NODE_DISCOVERY", text="Adv 1")

        # Filtrar solo RX
        rx_pkts, count_rx = self.buffer.get_packets(direction="rx")
        self.assertEqual(count_rx, 3)
        self.assertEqual(len(rx_pkts), 3)

        # Filtrar solo TX
        tx_pkts, count_tx = self.buffer.get_packets(direction="tx")
        self.assertEqual(count_tx, 1)
        self.assertEqual(tx_pkts[0]["text"], "Hola 2")

        # Filtrar por tipo
        telem_pkts, count_telem = self.buffer.get_packets(p_type="TELEMETRY")
        self.assertEqual(count_telem, 1)
        self.assertEqual(telem_pkts[0]["packet_type"], "TELEMETRY")

        # Paginación (limit=2, offset=1)
        all_paged, total = self.buffer.get_packets(limit=2, offset=1)
        self.assertEqual(total, 4)
        self.assertEqual(len(all_paged), 2)
        self.assertEqual(all_paged[0]["packet_id"], 2)

    def test_get_packet_by_id_and_clear(self) -> None:
        """Verifica la búsqueda por ID y el vaciado del búfer."""
        pkt = self.buffer.record("rx", channel_idx=0, packet_type="ACK", text="ACK_OK")
        self.assertIsNotNone(pkt)

        found = self.buffer.get_packet_by_id(pkt.packet_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "ACK_OK")

        not_found = self.buffer.get_packet_by_id(99999)
        self.assertIsNone(not_found)

        self.buffer.clear()
        self.assertEqual(len(self.buffer._buffer), 0)
        self.assertIsNone(self.buffer.get_packet_by_id(pkt.packet_id))

    def test_json_export_structure(self) -> None:
        """Verifica que el generador JSON cumpla con el esquema estructurado de exportación."""
        self.buffer.record("rx", channel_idx=0, packet_type="TEXT", text="Mensaje JSON", sender="aabbccdd")
        json_str = self.buffer.generate_json()

        data = json.loads(json_str)
        self.assertEqual(data["version"], "1.0")
        self.assertEqual(data["packet_count"], 1)
        self.assertEqual(len(data["packets"]), 1)
        self.assertEqual(data["packets"][0]["sender"], "aabbccdd")
        self.assertEqual(data["packets"][0]["text"], "Mensaje JSON")

    def test_csv_export_format(self) -> None:
        """Verifica que el generador CSV incluya cabeceras estándar y filas formateadas."""
        self.buffer.record("tx", channel_idx=2, packet_type="TEXT", text="Mensaje CSV, con comas", sender="11223344", rssi=-72)
        csv_str = self.buffer.generate_csv()

        lines = csv_str.strip().split("\r\n" if "\r\n" in csv_str else "\n")
        self.assertGreaterEqual(len(lines), 2)
        self.assertIn("ID,Timestamp_ISO,Epoch,Direction,Channel,Type", lines[0])
        self.assertIn("11223344", lines[1])
        self.assertIn("-72", lines[1])

    def test_pcap_export_binary_format(self) -> None:
        """Verifica que el generador PCAP produzca un archivo binario válido con DLT_USER0 (147)."""
        raw_payload = b"\xaa\x01\x02\x03\x55"
        self.buffer.record("rx", channel_idx=0, packet_type="RAW", raw_bytes=raw_payload)

        pcap_bytes = self.buffer.generate_pcap()

        # Cabecera global PCAP son 24 bytes
        self.assertGreaterEqual(len(pcap_bytes), 24 + 16 + len(raw_payload))

        # Desempaquetar cabecera global: magic, ver_major, ver_minor, thiszone, sigfigs, snaplen, network
        magic, v_maj, v_min, thiszone, sigfigs, snaplen, network = struct.unpack("<IHHiIII", pcap_bytes[:24])
        self.assertEqual(magic, 0xA1B2C3D4)
        self.assertEqual(v_maj, 2)
        self.assertEqual(v_min, 4)
        self.assertEqual(network, 147)  # DLT_USER0

        # Desempaquetar primer paquete: ts_sec, ts_usec, incl_len, orig_len
        pkt_header = pcap_bytes[24:40]
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack("<IIII", pkt_header)
        self.assertEqual(incl_len, len(raw_payload))
        self.assertEqual(orig_len, len(raw_payload))
        self.assertEqual(pcap_bytes[40:40 + incl_len], raw_payload)

    def test_capture_disabled(self) -> None:
        """Verifica que cuando capture_enabled=False no se almacenen tramas."""
        self.buffer.capture_enabled = False
        res = self.buffer.record("rx", text="Ignorado")
        self.assertIsNone(res)
        self.assertEqual(len(self.buffer._buffer), 0)


if __name__ == "__main__":
    unittest.main()
