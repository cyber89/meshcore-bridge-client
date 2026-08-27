"""
Unit tests for MeshCore Protocol Types, Serialization, Framing, and CRC validation.
"""

import pytest

from src.protocol_types import (
    EOF_BYTE,
    ESC_BYTE,
    SOF_BYTE,
    AckPayload,
    FrameHeader,
    HardwareModel,
    MeshcoreFrame,
    NodeAdvertisement,
    PacketType,
    TelemetryPayload,
    TextMessagePayload,
)


class TestProtocolHeader:
    def test_valid_header_packing_and_unpacking(self) -> None:
        header = FrameHeader(
            packet_type=PacketType.TELEMETRY_RESPONSE,
            seq_num=42,
            src_node_id=0x1234,
            dst_node_id=0xFFFF,
            hop_limit=3,
            payload_len=17,
        )
        packed = header.pack()
        assert len(packed) == 9

        unpacked = FrameHeader.unpack(packed)
        assert unpacked.packet_type == PacketType.TELEMETRY_RESPONSE
        assert unpacked.seq_num == 42
        assert unpacked.src_node_id == 0x1234
        assert unpacked.dst_node_id == 0xFFFF
        assert unpacked.hop_limit == 3
        assert unpacked.payload_len == 17

    def test_header_validation_errors(self) -> None:
        with pytest.raises(ValueError, match="seq_num fuera de rango"):
            FrameHeader(PacketType.TELEMETRY_RESPONSE, 300, 1, 2, 3, 10)

        with pytest.raises(ValueError, match="payload_len excede"):
            FrameHeader(PacketType.TELEMETRY_RESPONSE, 1, 1, 2, 3, 500)


class TestTelemetryPayload:
    def test_telemetry_roundtrip(self) -> None:
        telem = TelemetryPayload(
            battery_mv=4150,
            solar_mv=5200,
            temperature_c=24.5,
            humidity_pct=65.2,
            pressure_hpa=1013.25,
            snr_db=9,
            rssi_dbm=-75,
            battery_pct=95,
        )
        packed = telem.pack()
        assert len(packed) == 16

        unpacked = TelemetryPayload.unpack(packed)
        assert unpacked.battery_mv == 4150
        assert unpacked.solar_mv == 5200
        assert abs(unpacked.temperature_c - 24.5) < 0.01
        assert abs(unpacked.humidity_pct - 65.2) < 0.01
        assert abs(unpacked.pressure_hpa - 1013.25) < 0.01
        assert unpacked.snr_db == 9
        assert unpacked.rssi_dbm == -75
        assert unpacked.battery_pct == 95


class TestTextMessagePayload:
    def test_text_roundtrip(self) -> None:
        txt = TextMessagePayload(
            channel_idx=0,
            sender_alias="NodeAlpha",
            text="Hello MeshCore LoRa Network!",
        )
        packed = txt.pack()
        unpacked = TextMessagePayload.unpack(packed)
        assert unpacked.channel_idx == 0
        assert unpacked.sender_alias == "NodeAlpha"
        assert unpacked.text == "Hello MeshCore LoRa Network!"


class TestNodeAdvertisementPayload:
    def test_advertisement_roundtrip(self) -> None:
        adv = NodeAdvertisement(
            node_id=0xABCD,
            short_name="HLT3",
            long_name="Heltec-Gateway-North",
            hw_model=HardwareModel.HELTEC_V3,
            fw_version="v1.17",
            latitude=-33.456789,
            longitude=-70.654321,
            altitude_m=560,
        )
        packed = adv.pack()
        assert len(packed) == 39

        unpacked = NodeAdvertisement.unpack(packed)
        assert unpacked.node_id == 0xABCD
        assert unpacked.short_name == "HLT3"
        assert unpacked.long_name == "Heltec-Gateway-North"
        assert unpacked.hw_model == HardwareModel.HELTEC_V3
        assert abs(unpacked.latitude - (-33.456789)) < 1e-5
        assert abs(unpacked.longitude - (-70.654321)) < 1e-5
        assert unpacked.altitude_m == 560


class TestAckPayload:
    def test_ack_roundtrip(self) -> None:
        ack = AckPayload(ack_seq_num=128, status_code=0)
        packed = ack.pack()
        unpacked = AckPayload.unpack(packed)
        assert unpacked.ack_seq_num == 128
        assert unpacked.status_code == 0


class TestMeshcoreFrameSerialization:
    def test_full_frame_serialization_and_deserialization(self) -> None:
        telem = TelemetryPayload(
            battery_mv=3800,
            solar_mv=0,
            temperature_c=19.8,
            humidity_pct=45.0,
            pressure_hpa=1018.5,
            snr_db=6,
            rssi_dbm=-90,
            battery_pct=75,
        )
        telem_bytes = telem.pack()
        header = FrameHeader(
            packet_type=PacketType.TELEMETRY_RESPONSE,
            seq_num=10,
            src_node_id=0x0102,
            dst_node_id=0xFFFF,
            hop_limit=3,
            payload_len=len(telem_bytes),
        )
        frame = MeshcoreFrame(
            header=header,
            payload=telem,
            raw_payload=telem_bytes,
            crc16=0,
            is_valid=True,
        )

        serialized = frame.serialize()
        assert serialized[0] == SOF_BYTE
        assert serialized[-1] == EOF_BYTE

        # Simular recepción en driver serial (des-escapar y parsear)
        body = serialized[1:-1]
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

        parsed_frame = MeshcoreFrame.parse_raw_packet(bytes(unescaped))
        assert parsed_frame.is_valid is True
        assert parsed_frame.header.packet_type == PacketType.TELEMETRY_RESPONSE
        assert parsed_frame.header.seq_num == 10
        assert parsed_frame.header.src_node_id == 0x0102
        assert isinstance(parsed_frame.payload, TelemetryPayload)
        assert parsed_frame.payload.battery_mv == 3800

        # Verificar formato de evento MQTT para n8n
        mqtt_evt = parsed_frame.to_mqtt_event()
        assert mqtt_evt["event_type"] == "TELEMETRY_RESPONSE"
        assert mqtt_evt["sender"]["node_id"] == "0x0102"
        assert mqtt_evt["recipient"]["is_broadcast"] is True
        assert mqtt_evt["payload"]["battery_mv"] == 3800
