"""
CayenneLPP Environmental Sensor Decoder for MeshCore Bridge.
Decodificador determinista y modular para el estándar IPSO Cayenne Low Power Payload (LPP).
Soporta canales ambientales: Temperatura, Humedad, Barómetro, Voltaje, GPS y Acelerómetro.
"""

from __future__ import annotations

import io
import logging
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class LppDataType(IntEnum):
    """Tipos de datos estándar IPSO / CayenneLPP."""
    DIGITAL_INPUT = 0      # 1 byte
    DIGITAL_OUTPUT = 1     # 1 byte
    ANALOG_INPUT = 2       # 2 bytes, signed, resolution 0.01
    ANALOG_OUTPUT = 3      # 2 bytes, signed, resolution 0.01
    ILLUMINANCE = 101      # 2 bytes, unsigned, resolution 1 lux
    PRESENCE = 102         # 1 byte
    TEMPERATURE = 103      # 2 bytes, signed, resolution 0.1 °C
    HUMIDITY = 104         # 1 byte, unsigned, resolution 0.5 %
    ACCELEROMETER = 113    # 6 bytes, signed int16 * 3, resolution 0.001 G
    BAROMETER = 115        # 2 bytes, unsigned, resolution 0.1 hPa
    GYROSCOPE = 134        # 6 bytes, signed int16 * 3, resolution 0.01 °/s
    GPS_LOCATION = 136     # 9 bytes: Lat (3B), Lon (3B), Alt (3B)
    VOLTAGE = 116          # 2 bytes, unsigned, resolution 0.01 V
    PERCENTAGE = 120       # 1 byte, unsigned, resolution 1 %


@dataclass(frozen=True)
class SensorReading:
    """Lectura individual de un sensor CayenneLPP."""
    channel: int
    data_type: int
    type_name: str
    value: Any
    unit: str


def _decode_digital_io(stream: io.BytesIO, channel: int, type_val: int, summary: dict[str, Any]) -> SensorReading | None:
    raw = stream.read(1)
    if len(raw) < 1:
        return None
    val_int = int(raw[0])
    name = "digital_in" if type_val == LppDataType.DIGITAL_INPUT else "digital_out"
    summary[f"ch_{channel}_{name}"] = val_int
    return SensorReading(channel, type_val, name, val_int, "")


def _decode_analog_io(stream: io.BytesIO, channel: int, type_val: int, summary: dict[str, Any]) -> SensorReading | None:
    raw = stream.read(2)
    if len(raw) < 2:
        return None
    raw_val = struct.unpack(">h", raw)[0]
    val_float = round(raw_val * 0.01, 2)
    name = "analog_in" if type_val == LppDataType.ANALOG_INPUT else "analog_out"
    summary[f"ch_{channel}_{name}"] = val_float
    return SensorReading(channel, type_val, name, val_float, "V")


def _decode_scalar_sensors(stream: io.BytesIO, channel: int, type_val: int, summary: dict[str, Any]) -> SensorReading | None:
    if type_val == LppDataType.ILLUMINANCE:
        raw = stream.read(2)
        if len(raw) < 2:
            return None
        val_int = int(struct.unpack(">H", raw)[0])
        summary[f"ch_{channel}_illuminance_lux"] = val_int
        return SensorReading(channel, type_val, "illuminance", val_int, "lux")

    if type_val == LppDataType.PRESENCE:
        raw = stream.read(1)
        if len(raw) < 1:
            return None
        val_bool = bool(raw[0] > 0)
        summary[f"ch_{channel}_presence"] = val_bool
        return SensorReading(channel, type_val, "presence", val_bool, "")

    if type_val == LppDataType.TEMPERATURE:
        raw = stream.read(2)
        if len(raw) < 2:
            return None
        val_temp = round(struct.unpack(">h", raw)[0] * 0.1, 1)
        summary["temperature_c"] = val_temp
        summary[f"ch_{channel}_temperature_c"] = val_temp
        return SensorReading(channel, type_val, "temperature", val_temp, "°C")

    if type_val == LppDataType.HUMIDITY:
        raw = stream.read(1)
        if len(raw) < 1:
            return None
        val_hum = round(raw[0] * 0.5, 1)
        summary["humidity_pct"] = val_hum
        summary[f"ch_{channel}_humidity_pct"] = val_hum
        return SensorReading(channel, type_val, "humidity", val_hum, "%")

    if type_val == LppDataType.BAROMETER:
        raw = stream.read(2)
        if len(raw) < 2:
            return None
        val_baro = round(struct.unpack(">H", raw)[0] * 0.1, 1)
        summary["pressure_hpa"] = val_baro
        summary[f"ch_{channel}_pressure_hpa"] = val_baro
        return SensorReading(channel, type_val, "barometer", val_baro, "hPa")

    if type_val == LppDataType.VOLTAGE:
        raw = stream.read(2)
        if len(raw) < 2:
            return None
        val_volt = round(struct.unpack(">H", raw)[0] * 0.01, 2)
        summary["voltage_v"] = val_volt
        summary[f"ch_{channel}_voltage_v"] = val_volt
        return SensorReading(channel, type_val, "voltage", val_volt, "V")

    if type_val == LppDataType.PERCENTAGE:
        raw = stream.read(1)
        if len(raw) < 1:
            return None
        val_pct = int(raw[0])
        summary["battery_pct"] = val_pct
        summary[f"ch_{channel}_percentage"] = val_pct
        return SensorReading(channel, type_val, "percentage", val_pct, "%")

    return None


def _decode_multiaxis_or_gps(stream: io.BytesIO, channel: int, type_val: int, summary: dict[str, Any]) -> SensorReading | None:
    if type_val == LppDataType.ACCELEROMETER:
        raw = stream.read(6)
        if len(raw) < 6:
            return None
        x, y, z = struct.unpack(">hhh", raw)
        val_accel = {"x": round(x * 0.001, 3), "y": round(y * 0.001, 3), "z": round(z * 0.001, 3)}
        summary[f"ch_{channel}_accel_g"] = val_accel
        return SensorReading(channel, type_val, "accelerometer", val_accel, "G")

    if type_val == LppDataType.GPS_LOCATION:
        raw = stream.read(9)
        if len(raw) < 9:
            return None
        lat = round(int.from_bytes(raw[0:3], byteorder="big", signed=True) / 10000.0, 4)
        lon = round(int.from_bytes(raw[3:6], byteorder="big", signed=True) / 10000.0, 4)
        alt = round(int.from_bytes(raw[6:9], byteorder="big", signed=True) / 100.0, 2)
        gps_data = {"latitude": lat, "longitude": lon, "altitude_m": alt}
        summary["gps"] = gps_data
        summary[f"ch_{channel}_gps"] = gps_data
        return SensorReading(channel, type_val, "gps", gps_data, "deg/m")

    return None


class CayenneLPPDecoder:
    """Decodificador modular de tramas binarias CayenneLPP hacia diccionarios y lecturas tipadas."""

    @staticmethod
    def decode(data: bytes | bytearray) -> tuple[list[SensorReading], dict[str, Any]]:
        """
        Decodifica un flujo binario CayenneLPP.
        Retorna una tupla de (lista_de_lecturas, diccionario_resumen_json).
        """
        readings: list[SensorReading] = []
        summary: dict[str, Any] = {}
        stream = io.BytesIO(data)

        while True:
            ch_bytes = stream.read(1)
            if not ch_bytes:
                break
            channel = ch_bytes[0]

            type_bytes = stream.read(1)
            if not type_bytes:
                break
            type_val = type_bytes[0]

            try:
                reading: SensorReading | None = None
                if type_val in (LppDataType.DIGITAL_INPUT, LppDataType.DIGITAL_OUTPUT):
                    reading = _decode_digital_io(stream, channel, type_val, summary)
                elif type_val in (LppDataType.ANALOG_INPUT, LppDataType.ANALOG_OUTPUT):
                    reading = _decode_analog_io(stream, channel, type_val, summary)
                elif type_val in (LppDataType.ACCELEROMETER, LppDataType.GPS_LOCATION):
                    reading = _decode_multiaxis_or_gps(stream, channel, type_val, summary)
                else:
                    reading = _decode_scalar_sensors(stream, channel, type_val, summary)

                if reading is None:
                    reading = SensorReading(channel, type_val, "unknown", None, "")

                readings.append(reading)

            except Exception as e:
                logging.warning(f"Error decoding CayenneLPP payload: {e}", exc_info=True)
                break

        return readings, summary
