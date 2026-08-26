"""
Unit tests and fuzzing for CayenneLPP Environmental Sensor Decoder.
"""

import struct
import unittest

from src.sensor_decoder import (
    CayenneLPPDecoder,
    LppDataType,
    extract_telemetry_fields,
    format_telemetry_summary,
)


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

    def test_extract_telemetry_fields_dict_and_lpp(self) -> None:
        # Prueba con estructura LPP list de meshcore_py
        raw_lpp_data = {
            "lpp": [
                {"channel": 1, "type": "temperature", "value": 24.8},
                {"channel": 2, "type": "relative_humidity", "value": 58.2},
                {"channel": 3, "type": "barometer", "value": 1012.4},
                {"channel": 4, "type": "voltage", "value": 4.14},
                {"channel": 5, "type": "percentage", "value": 92},
            ],
            "battery_mv": 4140,
            "uptime_secs": 86450,
            "errors": 0,
            "queue_len": 2,
            "noise_floor": -105,
        }
        extracted = extract_telemetry_fields(raw_lpp_data)
        self.assertEqual(extracted["temperature_c"], 24.8)
        self.assertEqual(extracted["humidity_pct"], 58.2)
        self.assertEqual(extracted["pressure_hpa"], 1012.4)
        self.assertEqual(extracted["voltage_v"], 4.14)
        self.assertEqual(extracted["battery_pct"], 92)
        self.assertEqual(extracted["battery_mv"], 4140)
        self.assertEqual(extracted["uptime_secs"], 86450)
        self.assertIn("1d 0h 0m", extracted["uptime"])
        self.assertEqual(extracted["packet_errors"], 0)
        self.assertEqual(extracted["queue_len"], 2)
        self.assertEqual(extracted["noise_floor_dbm"], -105)

        summary_str = format_telemetry_summary(extracted)
        self.assertIn("24.8°C", summary_str)
        self.assertIn("58.2%", summary_str)
        self.assertIn("1012.4 hPa", summary_str)
        self.assertIn("92% (4.14V)", summary_str)
        self.assertIn("Cola: 2", summary_str)
        self.assertIn("0 err", summary_str)

    def test_extract_telemetry_fields_battery_mv_conversion(self) -> None:
        # Si solo viene battery_mv (ej: 4050 mV de stats_core)
        data = {"battery_mv": 4050, "uptime_secs": 3665}
        extracted = extract_telemetry_fields(data)
        self.assertEqual(extracted["battery_mv"], 4050)
        self.assertEqual(extracted["voltage_v"], 4.05)
        self.assertTrue(0 <= extracted["battery_pct"] <= 100)
        self.assertEqual(extracted["uptime"], "1h 1m 5s")

        summary_str = format_telemetry_summary(data)
        self.assertIn("4.05V", summary_str)
        self.assertIn("1h 1m 5s", summary_str)

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
