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
        raw_val = struct.unpack(">H", raw)[0]
        # Fix COMPAT-012: signed wrap fix for voltage (referencing reference/meshcore_py/src/meshcore/lpp_json_encoder.py)
        if raw_val > 32767:
            raw_val -= 65536
        val_volt = round(raw_val * 0.01, 2)
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

    @classmethod
    def decode_with_official_lib(cls, data: bytes | bytearray) -> tuple[list[SensorReading], dict[str, Any]]:
        """
        Decodifica un flujo usando la librería oficial pycayennelpp v2.x (LppFrame / LppData).
        Retorna al decoder nativo si hay problemas de formato o para compatibilidad total.
        """
        try:
            from cayennelpp import LppFrame

            buf = bytes(data)
            if not buf:
                return [], {}
            frame = LppFrame().from_bytes(buf)
            readings: list[SensorReading] = []
            summary: dict[str, Any] = {}
            for item in frame:
                ch = item.channel
                t_val = int(item.type)
                t_name = str(item.type.name).lower().replace(" ", "_")
                val = item.value[0] if isinstance(item.value, tuple) and len(item.value) == 1 else item.value
                if t_val == 136 and isinstance(item.value, tuple) and len(item.value) >= 3:
                    gps_data = {"latitude": item.value[0], "longitude": item.value[1], "altitude_m": item.value[2]}
                    summary["gps"] = gps_data
                    summary[f"ch_{ch}_gps"] = gps_data
                    readings.append(SensorReading(ch, t_val, "gps", gps_data, "deg/m"))
                else:
                    if t_name in ("temperature",):
                        summary["temperature_c"] = val
                        summary[f"ch_{ch}_temperature_c"] = val
                        readings.append(SensorReading(ch, t_val, "temperature", val, "°C"))
                    elif t_name in ("humidity",):
                        summary["humidity_pct"] = val
                        summary[f"ch_{ch}_humidity_pct"] = val
                        readings.append(SensorReading(ch, t_val, "humidity", val, "%"))
                    elif t_name in ("barometer", "pressure"):
                        summary["pressure_hpa"] = val
                        summary[f"ch_{ch}_pressure_hpa"] = val
                        readings.append(SensorReading(ch, t_val, "barometer", val, "hPa"))
                    elif t_name in ("voltage",):
                        summary["voltage_v"] = val
                        summary[f"ch_{ch}_voltage_v"] = val
                        readings.append(SensorReading(ch, t_val, "voltage", val, "V"))
                    elif t_name in ("analog_input", "analog_in"):
                        summary["analog_in"] = val
                        summary[f"ch_{ch}_analog_in"] = val
                        readings.append(SensorReading(ch, t_val, "analog_in", val, "V"))
                    else:
                        summary[t_name] = val
                        summary[f"ch_{ch}_{t_name}"] = val
                        readings.append(SensorReading(ch, t_val, t_name, val, ""))
            if readings:
                return readings, summary
        except Exception as ex:
            logging.debug(f"pycayennelpp decode_with_official_lib fallback to custom decoder: {ex}")
        return cls.decode(data)

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


def extract_telemetry_fields(data: dict[str, Any]) -> dict[str, Any]:
    """
    Extrae, normaliza y aplana exhaustivamente todas las posibles lecturas de telemetría y estado:
    - Temperatura, humedad, presión barométrica
    - Batería (porcentaje y mV/V), voltaje, solar
    - Uptime, errores, tamaño de cola
    - LPP decodificado (lista de objetos o diccionario plano)
    - Ubicación GPS
    - Métricas de radio (ruido, airtime, paquetes)
    """
    res: dict[str, Any] = {}
    if not isinstance(data, dict):
        return res

    # 1. Si hay bytes sin procesar en CayenneLPP (raw_bytes o raw_hex)
    if "raw_bytes" in data and isinstance(data["raw_bytes"], (bytes, bytearray)):
        _, summary = CayenneLPPDecoder.decode(bytes(data["raw_bytes"]))
        res.update(summary)
    elif "raw_hex" in data and isinstance(data["raw_hex"], str):
        try:
            raw_b = bytes.fromhex(data["raw_hex"])
            _, summary = CayenneLPPDecoder.decode(raw_b)
            res.update(summary)
        except Exception:
            pass

    # 2. Si hay lista o estructura LPP proveniente de MeshCore SDK (LppFrame / lpp_data_list)
    lpp_cand = data.get("lpp")
    if isinstance(lpp_cand, list):
        for item in lpp_cand:
            if isinstance(item, dict):
                t = str(item.get("type", item.get("type_name", ""))).lower()
                val = item.get("value", item.get("val"))
                ch = item.get("channel", 1)
                if val is None:
                    continue

                if "temp" in t:
                    try:
                        res["temperature_c"] = round(float(val), 1)
                        res[f"ch_{ch}_temperature_c"] = res["temperature_c"]
                    except (ValueError, TypeError):
                        pass
                elif "humid" in t:
                    try:
                        res["humidity_pct"] = round(float(val), 1)
                        res[f"ch_{ch}_humidity_pct"] = res["humidity_pct"]
                    except (ValueError, TypeError):
                        pass
                elif "barom" in t or "press" in t:
                    try:
                        res["pressure_hpa"] = round(float(val), 1)
                        res[f"ch_{ch}_pressure_hpa"] = res["pressure_hpa"]
                    except (ValueError, TypeError):
                        pass
                elif "volt" in t:
                    try:
                        res["voltage_v"] = round(float(val), 2)
                        res[f"ch_{ch}_voltage_v"] = res["voltage_v"]
                    except (ValueError, TypeError):
                        pass
                elif "percent" in t or "bat" in t:
                    try:
                        res["battery_pct"] = int(val)
                    except (ValueError, TypeError):
                        pass
                elif "gps" in t or "loc" in t:
                    if isinstance(val, (list, tuple)) and len(val) >= 2:
                        try:
                            res["latitude"] = float(val[0])
                            res["longitude"] = float(val[1])
                            if len(val) >= 3:
                                res["altitude_m"] = float(val[2])
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(val, dict):
                        try:
                            if "lat" in val or "latitude" in val:
                                res["latitude"] = float(val.get("lat", val.get("latitude")))
                            if "lon" in val or "longitude" in val:
                                res["longitude"] = float(val.get("lon", val.get("longitude")))
                            if "alt" in val or "altitude" in val:
                                res["altitude_m"] = float(val.get("alt", val.get("altitude")))
                        except (ValueError, TypeError):
                            pass
                elif "illumin" in t or "lux" in t:
                    try:
                        res["illuminance_lux"] = int(val)
                    except (ValueError, TypeError):
                        pass
    elif isinstance(lpp_cand, dict):
        for k, v in lpp_cand.items():
            if isinstance(v, (int, float, str)):
                res[k] = v

    # 3. Temperatura
    temp = data.get("temperature_c", data.get("temp_c", data.get("temp", data.get("temperature"))))
    if temp is not None:
        try:
            res["temperature_c"] = round(float(temp), 1)
        except (ValueError, TypeError):
            pass

    # 4. Humedad
    hum = data.get("humidity_pct", data.get("humidity", data.get("hum", data.get("relative_humidity"))))
    if hum is not None:
        try:
            res["humidity_pct"] = round(float(hum), 1)
        except (ValueError, TypeError):
            pass

    # 5. Presión
    press = data.get("pressure_hpa", data.get("pressure", data.get("press", data.get("barometer", data.get("barometric_pressure")))))
    if press is not None:
        try:
            res["pressure_hpa"] = round(float(press), 1)
        except (ValueError, TypeError):
            pass

    # 6. Batería y Voltaje
    raw_bat = data.get("battery_pct", data.get("battery", data.get("bat", data.get("batt"))))
    raw_bat_mv = data.get("battery_mv", data.get("batt_mv", data.get("vbat_mv")))
    raw_volt = data.get("voltage_v", data.get("voltage", data.get("volt", data.get("vbat"))))

    if raw_bat_mv is not None:
        try:
            mv_val = float(raw_bat_mv)
            res["battery_mv"] = int(mv_val)
            res["voltage_v"] = round(mv_val / 1000.0, 2)
            if "battery_pct" not in res and raw_bat is None:
                res["battery_pct"] = max(0, min(100, int((mv_val - 3300) / (4200 - 3300) * 100)))
        except (ValueError, TypeError):
            pass

    if raw_volt is not None and "voltage_v" not in res:
        try:
            v_val = float(raw_volt)
            res["voltage_v"] = round(v_val, 2) if v_val < 100.0 else round(v_val / 1000.0, 2)
            if "battery_pct" not in res and raw_bat is None and v_val < 10.0:
                res["battery_pct"] = max(0, min(100, int((v_val - 3.3) / (4.2 - 3.3) * 100)))
        except (ValueError, TypeError):
            pass

    if raw_bat is not None:
        try:
            b_val = float(raw_bat)
            if b_val > 100.0:  # Es en mV
                res["battery_mv"] = int(b_val)
                res["voltage_v"] = round(b_val / 1000.0, 2)
                res["battery_pct"] = max(0, min(100, int((b_val - 3300) / (4200 - 3300) * 100)))
            else:
                res["battery_pct"] = int(b_val)
        except (ValueError, TypeError):
            pass

    # 7. Solar
    raw_solar = data.get("solar_v", data.get("solar_mv", data.get("solar")))
    if raw_solar is not None:
        try:
            s_val = float(raw_solar)
            res["solar_v"] = round(s_val / 1000.0, 2) if s_val > 100.0 else round(s_val, 2)
        except (ValueError, TypeError):
            pass

    # 8. Uptime
    raw_uptime = data.get("uptime_secs", data.get("uptime", data.get("uptime_sec", data.get("uptime_s"))))
    if raw_uptime is not None:
        if isinstance(raw_uptime, (int, float)):
            secs = int(raw_uptime)
            res["uptime_secs"] = secs
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins, s = divmod(rem, 60)
            if days > 0:
                res["uptime"] = f"{days}d {hours}h {mins}m"
            elif hours > 0:
                res["uptime"] = f"{hours}h {mins}m {s}s"
            else:
                res["uptime"] = f"{mins}m {s}s"
        else:
            res["uptime"] = str(raw_uptime)

    # 9. Errores y Cola de Repetidor
    errors = data.get("errors", data.get("packet_errors", data.get("recv_errors")))
    if errors is not None:
        try:
            res["packet_errors"] = int(errors)
        except (ValueError, TypeError):
            pass

    queue = data.get("queue_len", data.get("queue"))
    if queue is not None:
        try:
            res["queue_len"] = int(queue)
        except (ValueError, TypeError):
            pass

    # 10. Métricas de Radio (ruido, airtime, paquetes)
    noise = data.get("noise_floor", data.get("noise_floor_dbm", data.get("noise")))
    if noise is not None:
        try:
            res["noise_floor_dbm"] = int(noise)
        except (ValueError, TypeError):
            pass

    airtime = data.get("airtime_ms", data.get("tx_air_secs", data.get("airtime")))
    if airtime is not None:
        try:
            res["airtime_ms"] = int(float(airtime) * 1000) if float(airtime) < 10000 else int(airtime)
        except (ValueError, TypeError):
            pass

    sent = data.get("packets_sent", data.get("sent"))
    if sent is not None:
        try:
            res["packets_sent"] = int(sent)
        except (ValueError, TypeError):
            pass

    recv = data.get("packets_recv", data.get("recv"))
    if recv is not None:
        try:
            res["packets_recv"] = int(recv)
        except (ValueError, TypeError):
            pass

    # 11. GPS
    for lat_k in ("latitude", "lat", "gps_lat"):
        if lat_k in data and data[lat_k] is not None:
            try:
                res["latitude"] = float(data[lat_k])
                break
            except (ValueError, TypeError):
                pass

    for lon_k in ("longitude", "lon", "gps_lon"):
        if lon_k in data and data[lon_k] is not None:
            try:
                res["longitude"] = float(data[lon_k])
                break
            except (ValueError, TypeError):
                pass

    for alt_k in ("altitude_m", "altitude", "alt"):
        if alt_k in data and data[alt_k] is not None:
            try:
                res["altitude_m"] = float(data[alt_k])
                break
            except (ValueError, TypeError):
                pass

    return res


def format_telemetry_summary(data: dict[str, Any]) -> str:
    """
    Genera una cadena de resumen visual estructurada y rica con los sensores y métricas presentes.
    Ejemplo: '🌡️ 24.5°C | 💧 60% | 🌀 1013.2 hPa | 🔋 85% (4.12V) | ⏱️ 3h 25m | ⚠️ 0 err'
    """
    extracted = extract_telemetry_fields(data)
    badges: list[str] = []

    if "temperature_c" in extracted:
        badges.append(f"🌡️ {extracted['temperature_c']}°C")
    if "humidity_pct" in extracted:
        badges.append(f"💧 {extracted['humidity_pct']}%")
    if "pressure_hpa" in extracted:
        badges.append(f"🌀 {extracted['pressure_hpa']} hPa")

    # Batería y Voltaje
    bat_pct = extracted.get("battery_pct")
    volt = extracted.get("voltage_v")
    bat_mv = extracted.get("battery_mv")
    if bat_pct is not None and volt is not None:
        badges.append(f"🔋 {bat_pct}% ({volt}V)")
    elif bat_pct is not None:
        badges.append(f"🔋 {bat_pct}%")
    elif volt is not None:
        badges.append(f"⚡ {volt}V")
    elif bat_mv is not None:
        badges.append(f"🔋 {bat_mv}mV")

    if "solar_v" in extracted:
        badges.append(f"☀️ {extracted['solar_v']}V")
    if "uptime" in extracted:
        badges.append(f"⏱️ {extracted['uptime']}")
    elif "uptime_secs" in extracted:
        badges.append(f"⏱️ {extracted['uptime_secs']}s")

    if "packet_errors" in extracted:
        badges.append(f"⚠️ {extracted['packet_errors']} err")
    if "queue_len" in extracted:
        badges.append(f"📦 Cola: {extracted['queue_len']}")
    if "noise_floor_dbm" in extracted:
        badges.append(f"📻 Ruido: {extracted['noise_floor_dbm']} dBm")

    if "latitude" in extracted and "longitude" in extracted:
        badges.append(f"📍 ({extracted['latitude']:.4f}, {extracted['longitude']:.4f})")

    if not badges:
        # Extraer cualquier clave informativa omitiendo metadatos internos
        ignored_keys = {
            "type", "event_type", "sender", "sender_name", "recipient", "timestamp",
            "rssi", "snr", "hops", "raw", "raw_hex", "raw_bytes", "txt_type",
            "is_outgoing", "channel_idx", "channel",
        }
        for k, v in data.items():
            if k not in ignored_keys and v is not None and not isinstance(v, (dict, list)):
                badges.append(f"{k}: {v}")

    return " | ".join(badges) if badges else "Sin lecturas adicionales"

