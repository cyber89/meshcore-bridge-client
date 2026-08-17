"""
Unit tests and fuzzing for CayenneLPP Environmental Sensor Decoder.
"""

import struct
import unittest

from src.sensor_decoder import CayenneLPPDecoder, LppDataType


class TestSensorDecoder(unittest.TestCase):
    def test_decode_standard_environmental_payload(self) -> None:
        # Construir payload CayenneLPP sintético:
        # Ch 1: Temp 22.5 °C (225)
        # Ch 2: Humidity 50.0 % (100)
        # Ch 3: Barometer 1013.2 hPa (10132)
        # Ch 4: Voltage 4.15 V (415)
        payload = bytearray()
        payload += bytes([1, LppDataType.TEMPERATURE]) + struct.pack(">h", 225)
        payload += bytes([2, LppDataType.HUMIDITY, 100])
        payload += bytes([3, LppDataType.BAROMETER]) + struct.pack(">H", 10132)
        payload += bytes([4, LppDataType.VOLTAGE]) + struct.pack(">H", 415)

        readings, summary = CayenneLPPDecoder.decode(payload)

        self.assertEqual(len(readings), 4)
        self.assertEqual(summary["temperature_c"], 22.5)
        self.assertEqual(summary["humidity_pct"], 50.0)
        self.assertEqual(summary["pressure_hpa"], 1013.2)
        self.assertEqual(summary["voltage_v"], 4.15)

    def test_decode_gps_and_accelerometer(self) -> None:
        # Ch 5: GPS Location (Lat: 40.7128, Lon: -74.0060, Alt: 15.5m)
        # Lat raw: 407128, Lon raw: -740060, Alt raw: 1550
        lat_bytes = (407128).to_bytes(3, byteorder="big", signed=True)
        lon_bytes = (-740060).to_bytes(3, byteorder="big", signed=True)
        alt_bytes = (1550).to_bytes(3, byteorder="big", signed=True)

        payload = bytearray([5, LppDataType.GPS_LOCATION]) + lat_bytes + lon_bytes + alt_bytes

        readings, summary = CayenneLPPDecoder.decode(payload)
        self.assertEqual(len(readings), 1)
        self.assertIn("gps", summary)
        self.assertEqual(summary["gps"]["latitude"], 40.7128)
        self.assertEqual(summary["gps"]["longitude"], -74.0060)
        self.assertEqual(summary["gps"]["altitude_m"], 15.5)

    def test_fuzzing_truncated_and_corrupt_payloads(self) -> None:
        # Casos truncados o corruptos no deben lanzar excepciones
        corrupt_inputs = [
            b"",
            b"\x01",
            b"\x01\x67",  # Falta el valor de temperatura
            b"\x05\x88\x01\x02",  # GPS incompleto (solo 2 de 9 bytes)
            b"\xFF\xFF\xFF",
        ]
        for data in corrupt_inputs:
            readings, summary = CayenneLPPDecoder.decode(data)
            self.assertIsInstance(readings, list)
            self.assertIsInstance(summary, dict)


if __name__ == "__main__":
    unittest.main()
