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

from src.shared_utils import clean_battery_input, clean_numeric_value, normalize_battery


class LppDataType(IntEnum):
    """Tipos de datos estándar IPSO / CayenneLPP."""
    DIGITAL_INPUT = 0      # 1 byte
    DIGITAL_OUTPUT = 1     # 1 byte
    ANALOG_INPUT = 2       # 2 bytes, signed, resolution 0.01
    ANALOG_OUTPUT = 3      # 2 bytes, signed, resolution 0.01
    GENERIC_SENSOR = 100
    ILLUMINANCE = 101      # 2 bytes, unsigned, resolution 1 lux
    PRESENCE = 102         # 1 byte
    TEMPERATURE = 103      # 2 bytes, signed, resolution 0.1 °C
    HUMIDITY = 104         # 1 byte, unsigned, resolution 0.5 %
    ACCELEROMETER = 113    # 6 bytes, signed int16 * 3, resolution 0.001 G
    BAROMETER = 115        # 2 bytes, unsigned, resolution 0.1 hPa
    GYROSCOPE = 134        # 6 bytes, signed int16 * 3, resolution 0.01 °/s
    GPS_LOCATION = 136     # 9 bytes: Lat (3B), Lon (3B), Alt (3B)
    VOLTAGE = 116          # 2 bytes, signed, resolution 0.01 V
    CURRENT = 117
    FREQUENCY = 118
    PERCENTAGE = 120       # 1 byte, unsigned, resolution 1 %
    ALTITUDE = 121
    LOAD = 122             # Python SDK extension
    CONCENTRATION = 125
    POWER = 128
    DISTANCE = 130
    ENERGY = 131
    DIRECTION = 132
    TIME = 133
    COLOUR = 135
    SWITCH = 142


# (name, bytes, divisor, signed, unit, summary key). No padding or inner CRC.
# CayenneLPP 1.6.1 uses big endian; MeshCore's Python SDK also supports LOAD.
_EXTENDED_SCALARS: dict[int, tuple[str, int, int, bool, str, str]] = {
    100: ("generic_sensor", 4, 1, False, "", "generic_sensor"),
    117: ("current", 2, 1000, True, "A", "current_a"),
    118: ("frequency", 4, 1, False, "Hz", "frequency_hz"),
    121: ("altitude", 2, 1, True, "m", "altitude_m"),
    122: ("load", 3, 1000, True, "", "load"),
    125: ("concentration", 2, 1, False, "ppm", "concentration_ppm"),
    128: ("power", 2, 1, False, "W", "power_w"),
    130: ("distance", 4, 1000, False, "m", "distance_m"),
    131: ("energy", 4, 1000, False, "kWh", "energy_kwh"),
    132: ("direction", 2, 1, False, "deg", "direction_deg"),
    133: ("time", 4, 1, False, "s", "unix_time"),
    142: ("switch", 1, 1, False, "", "switch"),
}


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
    extended = _EXTENDED_SCALARS.get(type_val)
    if extended is not None:
        name, size, divisor, signed, unit, summary_key = extended
        raw = stream.read(size)
        if len(raw) != size:
            return None
        integer = int.from_bytes(raw, "big", signed=signed)
        value = integer if divisor == 1 else integer / divisor
        summary[summary_key] = value
        summary[f"ch_{channel}_{summary_key}"] = value
        return SensorReading(channel, type_val, name, value, unit)

    if type_val == LppDataType.COLOUR:
        raw = stream.read(3)
        if len(raw) != 3:
            return None
        colour = dict(zip(("red", "green", "blue"), raw, strict=True))
        summary[f"ch_{channel}_colour"] = colour
        return SensorReading(channel, type_val, "colour", colour, "RGB")

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
    if type_val in (LppDataType.ACCELEROMETER, LppDataType.GYROSCOPE):
        raw = stream.read(6)
        if len(raw) < 6:
            return None
        x, y, z = struct.unpack(">hhh", raw)
        if type_val == LppDataType.GYROSCOPE:
            gyroscope = {"x": x / 100.0, "y": y / 100.0, "z": z / 100.0}
            summary[f"ch_{channel}_gyroscope_dps"] = gyroscope
            return SensorReading(channel, type_val, "gyrometer", gyroscope, "°/s")
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
        summary["latitude"] = lat
        summary["longitude"] = lon
        summary["altitude_m"] = alt
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
                elif type_val in (LppDataType.ACCELEROMETER, LppDataType.GYROSCOPE, LppDataType.GPS_LOCATION):
                    reading = _decode_multiaxis_or_gps(stream, channel, type_val, summary)
                else:
                    reading = _decode_scalar_sensors(stream, channel, type_val, summary)

                if reading is None:
                    reading = SensorReading(channel, type_val, "unknown", None, "")
                    readings.append(reading)
                    # Sin tamaño conocido no se puede encontrar el siguiente registro.
                    # Un valor truncado tampoco constituye una lectura completa.
                    break

                readings.append(reading)

            except Exception as e:
                logging.warning(f"Error decoding CayenneLPP payload: {e}", exc_info=True)
                break

        return readings, summary


def _extract_lpp_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae y decodifica tramas CayenneLPP binarias, hex o estructuras SDK."""
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

    lpp_cand = data.get("lpp")
    if isinstance(lpp_cand, list):
        _parse_lpp_candidate_list(lpp_cand, res)
    elif isinstance(lpp_cand, dict):
        for k, v in lpp_cand.items():
            if isinstance(v, (int, float, str)):
                res[k] = v


def _parse_lpp_candidate_list(lpp_list: list[Any], res: dict[str, Any]) -> None:
    """Parsea la lista de objetos LPP provenientes de MeshCore SDK."""
    for item in lpp_list:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type", item.get("type_name", ""))).lower()
        val = item.get("value", item.get("val"))
        ch = item.get("channel", 1)
        if val is None:
            continue

        _map_lpp_item_to_res(t, val, ch, res)


def _map_lpp_item_to_res(t: str, val: Any, ch: Any, res: dict[str, Any]) -> None:
    """Mapea un elemento individual de LPP al diccionario de resultados."""
    try:
        if t.isdigit() and int(t) in _EXTENDED_SCALARS:
            t = _EXTENDED_SCALARS[int(t)][0]
        if isinstance(val, (list, tuple)) and len(val) == 1:
            val = val[0]
        for name, _, _, _, _, key in _EXTENDED_SCALARS.values():
            if t.replace(" ", "_") == name:
                number = clean_numeric_value(val)
                if number is not None:
                    res[key] = number
                    res[f"ch_{ch}_{key}"] = number
                return
        if t in ("colour", "color") and isinstance(val, dict):
            colour = {key: clean_numeric_value(val.get(key)) for key in ("red", "green", "blue")}
            if all(value is not None for value in colour.values()):
                res[f"ch_{ch}_colour"] = colour
            return
        if "temp" in t:
            clean_t = clean_numeric_value(val)
            if clean_t is not None:
                res["temperature_c"] = round(clean_t, 1)
                res[f"ch_{ch}_temperature_c"] = res["temperature_c"]
        elif "humid" in t:
            clean_h = clean_numeric_value(val)
            if clean_h is not None:
                res["humidity_pct"] = round(clean_h, 1)
                res[f"ch_{ch}_humidity_pct"] = res["humidity_pct"]
        elif "barom" in t or "press" in t:
            clean_p = clean_numeric_value(val)
            if clean_p is not None:
                res["pressure_hpa"] = round(clean_p, 1)
                res[f"ch_{ch}_pressure_hpa"] = res["pressure_hpa"]
        elif "volt" in t:
            clean_v = clean_numeric_value(val)
            if clean_v is not None:
                norm_v = round(clean_v, 2)
                res["voltage_v"] = norm_v
                res[f"ch_{ch}_voltage_v"] = norm_v
                if "battery_pct" not in res and 2.5 <= norm_v <= 4.5:
                    pct_from_v, _ = normalize_battery(norm_v)
                    res["battery_pct"] = int(round(pct_from_v))
        elif "percent" in t or "bat" in t:
            clean_b = clean_numeric_value(val)
            if clean_b is not None:
                pct = max(0, min(100, int(round(clean_b))))
                res["battery_pct"] = pct
                res[f"ch_{ch}_percentage"] = pct
        elif "illumin" in t or "lux" in t:
            clean_l = clean_numeric_value(val)
            if clean_l is not None:
                res["illuminance_lux"] = int(round(clean_l))
                res[f"ch_{ch}_illuminance_lux"] = res["illuminance_lux"]
        elif "gps" in t or "loc" in t:
            _parse_lpp_gps_val(val, res)
    except (ValueError, TypeError):
        pass


def _parse_lpp_gps_val(val: Any, res: dict[str, Any]) -> None:
    """Extrae coordenadas GPS desde estructuras de lista, tupla o diccionario."""
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        c_lat = clean_numeric_value(val[0])
        c_lon = clean_numeric_value(val[1])
        if c_lat is not None:
            res["latitude"] = round(c_lat, 5)
        if c_lon is not None:
            res["longitude"] = round(c_lon, 5)
        if len(val) >= 3:
            c_alt = clean_numeric_value(val[2])
            if c_alt is not None:
                res["altitude_m"] = round(c_alt, 1)
    elif isinstance(val, dict):
        v_lat = val.get("lat", val.get("latitude"))
        if v_lat is not None:
            c_lat = clean_numeric_value(v_lat)
            if c_lat is not None:
                res["latitude"] = round(c_lat, 5)
        v_lon = val.get("lon", val.get("longitude"))
        if v_lon is not None:
            c_lon = clean_numeric_value(v_lon)
            if c_lon is not None:
                res["longitude"] = round(c_lon, 5)
        v_alt = val.get("alt", val.get("altitude", val.get("altitude_m", val.get("alt_m"))))
        if v_alt is not None:
            c_alt = clean_numeric_value(v_alt)
            if c_alt is not None:
                res["altitude_m"] = round(c_alt, 1)


def _extract_environment_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae lecturas de temperatura, humedad y presión atmosférica."""
    temp = data.get("temperature_c", data.get("temp_c", data.get("temp", data.get("temperature"))))
    if temp is not None:
        clean_t = clean_numeric_value(temp)
        if clean_t is not None:
            res["temperature_c"] = round(clean_t, 1)

    hum = data.get("humidity_pct", data.get("humidity", data.get("hum", data.get("relative_humidity"))))
    if hum is not None:
        clean_h = clean_numeric_value(hum)
        if clean_h is not None:
            res["humidity_pct"] = round(clean_h, 1)

    press = data.get("pressure_hpa", data.get("pressure", data.get("press", data.get("barometer", data.get("barometric_pressure")))))
    if press is not None:
        clean_p = clean_numeric_value(press)
        if clean_p is not None:
            res["pressure_hpa"] = round(clean_p, 1)


def _extract_power_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae y normaliza métricas de batería, voltaje y panel solar respetando unidades explícitas."""
    raw_bat = data.get("battery_pct", data.get("battery", data.get("bat", data.get("batt", data.get("level")))))
    raw_bat_mv = data.get("battery_mv", data.get("batt_mv", data.get("vbat_mv")))
    raw_volt = data.get("voltage_v", data.get("voltage", data.get("volt", data.get("vbat"))))

    if raw_bat_mv is not None:
        clean_mv = clean_numeric_value(raw_bat_mv)
        if clean_mv is not None:
            res["battery_mv"] = int(round(clean_mv))
            if "voltage_v" not in res and raw_volt is None:
                res["voltage_v"] = clean_mv / 1000.0
            if "battery_pct" not in res and raw_bat is None and 2500 <= clean_mv <= 4500:
                pct_norm, _ = normalize_battery(clean_mv)
                res["battery_pct"] = int(round(pct_norm))

    if raw_volt is not None:
        clean_v = clean_numeric_value(raw_volt)
        if clean_v is not None:
            res["voltage_v"] = clean_v
            if "battery_pct" not in res and raw_bat is None and 2.5 <= clean_v <= 4.5:
                pct_norm, _ = normalize_battery(clean_v)
                res["battery_pct"] = int(round(pct_norm))

    if raw_bat is not None:
        has_explicit_pct_key = "battery_pct" in data
        clean_b = clean_numeric_value(raw_bat)
        if clean_b is not None:
            if has_explicit_pct_key or (0 <= clean_b <= 100 and not isinstance(raw_bat, str)):
                res["battery_pct"] = max(0, min(100, int(round(clean_b))))
                if "voltage_v" not in res and raw_volt is None and raw_bat_mv is None:
                    _, volt_norm = normalize_battery(clean_b)
                    if volt_norm > 0:
                        res["voltage_v"] = volt_norm
                        res["battery_mv"] = int(volt_norm * 1000.0)
            else:
                pct_norm, volt_norm = normalize_battery(raw_bat)
                res["battery_pct"] = int(round(pct_norm))
                if volt_norm > 0:
                    if "voltage_v" not in res:
                        res["voltage_v"] = volt_norm
                    if "battery_mv" not in res:
                        res["battery_mv"] = int(volt_norm * 1000.0)

    # Estimación de porcentaje a partir de voltaje SOLO si battery_pct no fue provisto
    eff_v = res.get("voltage_v")
    if eff_v is not None and 2.5 <= eff_v <= 4.5 and res.get("battery_pct") is None:
        calc_pct, _ = normalize_battery(eff_v)
        res["battery_pct"] = int(round(calc_pct))

    for key in ("solar_v", "solar_voltage", "solar_mv", "solar"):
        if data.get(key) is None:
            continue
        clean_s = clean_battery_input(data[key])
        if clean_s is not None:
            # Only the legacy unitless alias retains its magnitude heuristic.
            millivolts = key == "solar_mv" or (key == "solar" and clean_s > 100.0)
            res["solar_v"] = clean_s / 1000.0 if millivolts else clean_s
        break


def _extract_system_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae uptime formateado, colas y contadores de errores."""
    raw_uptime = data.get("uptime_secs", data.get("uptime", data.get("uptime_sec", data.get("uptime_s"))))
    if raw_uptime is not None:
        clean_up = clean_numeric_value(raw_uptime)
        if clean_up is not None and (
            isinstance(raw_uptime, (int, float)) or str(raw_uptime).strip().isdigit() or str(raw_uptime).strip().endswith("s")
        ):
            secs = int(clean_up)
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

    if "clock" in data and data["clock"] is not None:
        res["clock"] = str(data["clock"])
    if "fixed_position" in data and data["fixed_position"] is not None:
        value = data["fixed_position"]
        if isinstance(value, bool):
            res["fixed_position"] = value
        elif isinstance(value, int) and value in (0, 1):
            res["fixed_position"] = bool(value)
        elif isinstance(value, str) and value.strip().lower() in ("true", "false", "0", "1", "on", "off", "yes", "no"):
            res["fixed_position"] = value.strip().lower() in ("true", "1", "on", "yes")

    errors = data.get("errors", data.get("packet_errors", data.get("recv_errors")))
    if errors is not None:
        clean_err = clean_numeric_value(errors)
        if clean_err is not None:
            res["packet_errors"] = int(clean_err)

    queue = data.get("queue_len", data.get("queue"))
    if queue is not None:
        clean_q = clean_numeric_value(queue)
        if clean_q is not None:
            res["queue_len"] = int(clean_q)


def _extract_radio_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae métricas RF: piso de ruido, airtime, contadores de paquetes y parámetros RF."""
    noise = data.get("noise_floor", data.get("noise_floor_dbm", data.get("noise")))
    if noise is not None:
        clean_n = clean_numeric_value(noise)
        if clean_n is not None:
            res["noise_floor_dbm"] = int(round(clean_n))

    if "airtime_ms" in data and data["airtime_ms"] is not None:
        clean_at = clean_numeric_value(data["airtime_ms"])
        if clean_at is not None:
            res["airtime_ms"] = int(clean_at)
    elif "tx_air_secs" in data and data["tx_air_secs"] is not None:
        clean_at = clean_numeric_value(data["tx_air_secs"])
        if clean_at is not None:
            res["airtime_ms"] = int(round(clean_at * 1000))
    elif "airtime" in data and data["airtime"] is not None:
        val = data["airtime"]
        clean_at = clean_numeric_value(val)
        if clean_at is not None:
            raw_s = str(val).strip().lower()
            if raw_s.endswith("ms"):
                res["airtime_ms"] = int(clean_at)
            else:
                res["airtime_ms"] = int(round(clean_at * 1000))

    duty = data.get("duty_cycle_pct", data.get("duty_cycle", data.get("dutycycle")))
    if duty is not None:
        clean_d = clean_numeric_value(duty)
        if clean_d is not None:
            res["duty_cycle_pct"] = round(clean_d, 2)

    sent = data.get("packets_sent", data.get("sent"))
    if sent is not None:
        clean_s = clean_numeric_value(sent)
        if clean_s is not None:
            res["packets_sent"] = int(clean_s)

    recv = data.get("packets_recv", data.get("recv"))
    if recv is not None:
        clean_r = clean_numeric_value(recv)
        if clean_r is not None:
            res["packets_recv"] = int(clean_r)

    freq = data.get("frequency", data.get("freq"))
    if freq is not None:
        clean_f = clean_numeric_value(freq)
        if clean_f is not None:
            res["frequency"] = round(clean_f, 3)

    pwr = data.get("tx_power", data.get("power"))
    if pwr is not None:
        clean_p = clean_numeric_value(pwr)
        if clean_p is not None:
            res["tx_power"] = int(round(clean_p))

    sf = data.get("spreading_factor", data.get("sf"))
    if sf is not None:
        clean_sf = clean_numeric_value(sf)
        if clean_sf is not None:
            res["spreading_factor"] = int(round(clean_sf))

    bw = data.get("bandwidth", data.get("bw"))
    if bw is not None:
        clean_bw = clean_numeric_value(bw)
        if clean_bw is not None:
            res["bandwidth"] = round(clean_bw, 1)

    adv_int = data.get("advert_interval")
    if adv_int is not None:
        clean_ai = clean_numeric_value(adv_int)
        if clean_ai is not None:
            res["advert_interval"] = int(round(clean_ai))

    hop_lim = data.get("hop_limit", data.get("max_hops"))
    if hop_lim is not None:
        clean_hl = clean_numeric_value(hop_lim)
        if clean_hl is not None:
            res["hop_limit"] = int(round(clean_hl))

    hops = data.get("hops", data.get("hop_count"))
    if hops is not None:
        clean_h = clean_numeric_value(hops)
        if clean_h is not None:
            res["hops"] = int(round(clean_h))

    for util_k in ("channel_utilization", "ch_util", "air_util_tx", "air_util", "utilization"):
        if util_k in data and data[util_k] is not None:
            clean_u = clean_numeric_value(data[util_k])
            if clean_u is not None:
                res["channel_utilization"] = round(clean_u, 2)
                res["ch_util"] = round(clean_u, 2)
                break



def _extract_location_telemetry(data: dict[str, Any], res: dict[str, Any]) -> None:
    """Extrae coordenadas GPS (latitud, longitud, altitud), soportando estructuras anidadas y adverts."""
    source_dicts: list[dict[str, Any]] = []
    for d in (res, data):
        if isinstance(d, dict) and d not in source_dicts:
            source_dicts.append(d)
        for nested_k in ("gps", "position", "location", "geo"):
            nested = d.get(nested_k) if isinstance(d, dict) else None
            if isinstance(nested, dict) and nested not in source_dicts:
                source_dicts.append(nested)

    for src in source_dicts:
        if "latitude" not in res:
            for lat_k in ("latitude", "lat", "gps_lat", "adv_lat"):
                if lat_k in src and src[lat_k] is not None:
                    clean_lat = clean_numeric_value(src[lat_k])
                    if clean_lat is not None:
                        res["latitude"] = clean_lat
                        break

        if "longitude" not in res:
            for lon_k in ("longitude", "lon", "gps_lon", "adv_lon"):
                if lon_k in src and src[lon_k] is not None:
                    clean_lon = clean_numeric_value(src[lon_k])
                    if clean_lon is not None:
                        res["longitude"] = clean_lon
                        break

        if "altitude_m" not in res:
            for alt_k in ("altitude_m", "alt_m", "altitude", "alt", "gps_alt"):
                if alt_k in src and src[alt_k] is not None:
                    clean_alt = clean_numeric_value(src[alt_k])
                    if clean_alt is not None:
                        res["altitude_m"] = clean_alt
                        break

    if "latitude" in res and "adv_lat" not in res:
        res["adv_lat"] = res["latitude"]
    if "longitude" in res and "adv_lon" not in res:
        res["adv_lon"] = res["longitude"]


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

    _extract_lpp_telemetry(data, res)
    _extract_environment_telemetry(data, res)
    _extract_power_telemetry(data, res)
    _extract_system_telemetry(data, res)
    _extract_radio_telemetry(data, res)
    _extract_location_telemetry(data, res)

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
        # Extraer cualquier clave informativa omitiendo metadatos internos y credenciales de canal
        ignored_keys = {
            "type", "event_type", "sender", "sender_name", "recipient", "timestamp",
            "rssi", "snr", "hops", "raw", "raw_hex", "raw_bytes", "txt_type",
            "is_outgoing", "channel_idx", "channel", "messages_available",
            "channel_name", "channel_secret", "channel_hash", "psk", "secret", "is_local",
        }
        for k, v in data.items():
            if k not in ignored_keys and v is not None and not isinstance(v, (dict, list)):
                badges.append(f"{k}: {v}")

    return " | ".join(badges) if badges else "Sin lecturas adicionales"




