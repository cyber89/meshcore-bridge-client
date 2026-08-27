# REPORT5: MeshCore Bridge — Incompatibilidades con el Stack Oficial

**Fecha**: 2026-08-27  
**Alcance**: Auditoría de compatibilidad del bridge (`/src/`) vs firmware oficial (`/reference/meshcore/`), SDK Python (`/reference/meshcore_py/`) y bridge oficial (`/reference/meshcoretomqtt/`).  
**Estado**: Análisis READ-ONLY — sin cambios de código.

---

## Resumen Ejecutivo

El bridge implementa un subconjunto del protocolo MeshCore con **desviaciones significativas** del SDK oficial y el bridge de referencia. Estas incompatibilidades causan:

1. **Pérdida de mensajes**: Tipos de evento/paquete no manejados se descartan silenciosamente
2. **Parsing incorrecto**: Diferencias en formatos de telemetría, contactos y stats
3. **Funcionalidad faltante**: ~30+ tipos de comando/paquete del SDK no están implementados
4. **Divergencia de topicos**: Estructura MQTT incompatible con el bridge oficial

---

## 1. Incompatibilidades de Protocolo (OpCodes y Tipos)

### 1.1 Naming y Estructura Diferente

| Bridge (`protocol_types.py`) | SDK Oficial (`packets.py`) | Estado |
|------------------------------|---------------------------|--------|
| `OpCode` (7 valores: TELEMETRY..ACK) | `PacketType` (40+ valores) | **INCOMPATIBLE** — diferente enum, diferentes valores |
| `FirmwareCommandType` | `CommandType` | **PARCIAL** — bridge tiene subset |
| `FirmwarePushCode` | `PacketType` (0x80-0x90) | **PARCIAL** — bridge tiene subset |

**Problema fundamental**: El bridge define `OpCode` como tipo de payload LoRa (0x01-0x07), pero el SDK usa `PacketType` para respuestas del host (0x00-0x1C) Y push notifications (0x80-0x90). Son **namespaces diferentes** que el bridge mezcla.

### 1.2 Comandos Faltantes en el Bridge

```python
# SDK CommandType tiene 45+ comandos. Bridge solo implementa ~20:
FALTANTES_EN_BRIDGE = {
    21: "SET_TUNING_PARAMS",
    23: "EXPORT_PRIVATE_KEY", 
    24: "IMPORT_PRIVATE_KEY",
    27: "SEND_STATUS_REQ",
    28: "HAS_CONNECTION",
    33: "SIGN_START",
    34: "SIGN_DATA",
    35: "SIGN_FINISH",
    37: "SET_DEVICE_PIN",
    38: "SET_OTHER_PARAMS",
    40: "GET_CUSTOM_VARS",
    41: "SET_CUSTOM_VAR",
    42: "GET_ADVERT_PATH",
    43: "GET_TUNING_PARAMS",
    51: "FACTORY_RESET",
    52: "PATH_DISCOVERY",
    54: "SET_FLOOD_SCOPE",
    55: "SEND_CONTROL_DATA",
    57: "SEND_ANON_REQ",
    58: "SET_AUTOADD_CONFIG",
    59: "GET_AUTOADD_CONFIG",
    60: "GET_ALLOWED_REPEAT_FREQ",
    61: "SET_PATH_HASH_MODE",
    63: "SET_DEFAULT_FLOOD_SCOPE",
    64: "GET_DEFAULT_FLOOD_SCOPE",
}
```

### 1.3 Paquetes/Respuestas Faltantes

```python
# SDK PacketType tiene 40+ tipos de respuesta. Bridge solo maneja ~5:
PAQUETES_NO_MANEJADOS = {
    0: "OK",
    1: "ERROR", 
    2: "CONTACT_START",
    3: "CONTACT",
    4: "CONTACT_END",
    5: "SELF_INFO",
    6: "MSG_SENT",
    7: "CONTACT_MSG_RECV",      # Bridge maneja parcialmente
    8: "CHANNEL_MSG_RECV",      # Bridge maneja parcialmente
    9: "CURRENT_TIME",
    10: "NO_MORE_MSGS",
    11: "CONTACT_URI",
    12: "BATTERY",
    13: "DEVICE_INFO",
    14: "PRIVATE_KEY",
    15: "DISABLED",
    16: "CONTACT_MSG_RECV_V3",  # Bridge NO maneja
    17: "CHANNEL_MSG_RECV_V3",  # Bridge NO maneja
    18: "CHANNEL_INFO",
    19: "SIGN_START",
    20: "SIGNATURE",
    21: "CUSTOM_VARS",
    22: "ADVERT_PATH",
    23: "TUNING_PARAMS",
    24: "STATS",                # Bridge maneja parcialmente
    25: "AUTOADD_CONFIG",
    26: "ALLOWED_REPEAT_FREQ",
    27: "CHANNEL_DATA_RECV",
    28: "DEFAULT_FLOOD_SCOPE",
}
```

---

## 2. Sistema de Eventos Diferente

### 2.1 Tipos de Evento

| Bridge | SDK (`events.py`) | Compatibilidad |
|--------|-------------------|----------------|
| `int` (numérico) | `EventType` (string enum) | **INCOMPATIBLE** |
| Solo 4 tipos manejados | 60+ tipos | **CRÍTICO** |

Bridge solo maneja:
- `CONTACT_MSG_RECV` (7)
- `CHANNEL_MSG_RECV` (8)  
- `CURRENT_TIME` (9)
- `STATS` (24)

SDK tiene eventos adicionales críticos no manejados:
- `BATTERY`, `DEVICE_INFO`, `MSG_SENT`, `ADVERT_PATH`
- `TELEMETRY_RESPONSE`, `BINARY_RESPONSE`, `TRACE_DATA`
- `LOG_DATA`, `RX_LOG_DATA`, `CONTROL_DATA`
- `CHANNEL_DATA_RECV`, `CHANNEL_INFO`
- `PATH_RESPONSE`, `NEIGHBOURS_RESPONSE`
- Y 40+ más...

### 2.2 Estructura de Evento

```python
# SDK Event:
@dataclass
class Event:
    type: EventType      # Enum string
    payload: Any         # Dict con campos específicos
    attributes: Dict     # Para filtering

# Bridge: usa tuples (event_type: int, data: Any)
# Diferencia: bridge pierde attributos y filtering
```

---

## 3. Parsing de Telemetría/Status

### 3.1 Doble Implementación

Bridge tiene **dos** parsers de telemetría que se superponen:

1. **`TelemetryPayload.unpack()`** (`protocol_types.py:274-288`):
   - Formato: `<HHhhIbhB` (16 bytes)
   - Campos: battery_mv, solar_mv, temperature, humidity, pressure, snr, rssi, battery_pct

2. **`parse_telemetry_from_sdk()`** (`protocol_types.py:293-340`):
   - Formato: 52-56 bytes (diferente layout)
   - Replica `parse_status()` del SDK

**Problema**: `TelemetryPayload` **NO existe en el firmware real**. El firmware envía `STATUS_RESPONSE` (0x87) con el formato de `parse_status()`. El bridge intenta parsear con `TelemetryPayload` y falla silenciosamente.

### 3.2 Status Response Parsing

```python
# SDK (reader.py:658-678):
# STATUS_RESPONSE (0x87): 60 bytes
# Formato: 1 type + 1 reserved + 6 pubkey + 52 status fields
res = parse_status(data, offset=8)

# Bridge (serial_driver.py:361-374):
# Solo ignora el evento, no publica status
elif event_type == getattr(EventType, "STATUS_RESPONSE", ...):
    pass  # ← PERDIDO!
```

### 3.3 Stats Response

```python
# SDK (reader.py:452-537):
# STATS (24) con sub-tipos:
#   stats_type=0: CORE (battery_mv, uptime, errors, queue)
#   stats_type=1: RADIO (noise_floor, rssi, snr, airtime)
#   stats_type=2: PACKETS (recv, sent, flood/direct stats)

# Bridge (serial_driver.py:370-372):
elif event_type == getattr(EventType, "STATS", 24):
    pass  # ← PERDIDO!
```

---

## 4. CayenneLPP Decoder

### 4.1 Diferencias de Implementación

| Característica | Bridge (`sensor_decoder.py`) | SDK (`parsing.py`) |
|----------------|------------------------------|---------------------|
| Decoder principal | Custom `CayenneLPPDecoder` | `cayennelpp` library |
| Fallback | `decode_with_official_lib()` | N/A |
| MMA parsing | No implementado | `lpp_parse_mma()` |
| ACL parsing | No implementado | `parse_acl()` |
| JSON encoding | `asdict()` | `lpp_json_encoder` |

### 4.2 Telemetry LPP

```python
# SDK (reader.py:776-806):
# TELEMETRY_RESPONSE (0x8B):
#   1 byte reserved
#   6 bytes pubkey_prefix
#   remaining: LPP data → LppFrame → JSON

# Bridge (sensor_decoder.py):
# Intenta decodificar LPP raw pero no tiene contexto de evento
```

---

## 5. Estructura MQTT

### 5.1 Topicos

| Bridge | SDK Oficial (`topics.py`) | Compatible |
|--------|--------------------------|------------|
| `{prefix}/bridge/state` | Configurable con `{IATA}`, `{PUBLIC_KEY}` | **NO** |
| `{prefix}/bridge/health` | `topics.get_topic(state, 'health')` | **NO** |
| `{prefix}/tx` | `topics.get_topic(state, 'tx')` | **NO** |
| `{prefix}/admin/cmd` | `topics.get_topic(state, 'admin')` | **NO** |

**Problema**: El bridge oficial usa sistema de topicos configurable con placeholders. El bridge hardcodea topicos, making incompatible con configuraciones existentes.

### 5.2 Formato de Mensaje

```python
# SDK official bridge (mqtt_publish.py):
# {
#   "from": pubkey_prefix,
#   "to": dest_key,
#   "text": message,
#   "channel": channel_idx,
#   "txt_type": type,
#   "timestamp": time,
#   "signature": sig,  # optional
# }

# Bridge actual:
# {
#   "event_type": "TEXT_MSG",
#   "sender": {"node_id": "0xFFFF"},
#   "payload": {...}
# }
```

---

## 6. Comunicación Serial

### 6.1 Protocolo Diferente

| Bridge | SDK Oficial (`serial_connection.py`) |
|--------|--------------------------------------|
| Binario framing (SOF/EOF/ESC/CRC) | Texto CLI (`get name`, `ver`, etc.) |
| `MeshcoreSDKAdapter` | `RealSerialConnection` |
| `RawSerialFramingAdapter` | N/A |

**Problema**: El bridge oficial usa **CLI de texto** para comandos de configuración (`get name`, `get public.key`, `stats-core`, etc.). El bridge usa protocolo binario. Son **protocolos fundamentalmente diferentes**.

### 6.2 Comandos No Soportados

```python
# SDK official bridge ejecuta comandos CLI como:
cmds = [
    "time {epoch}",           # SET_DEVICE_TIME
    "get name",               # GET_NAME
    "get public.key",         # GET_PUBKEY
    "get prv.key",            # GET_PRIVKEY  
    "get radio",              # GET_RADIO_INFO
    "ver",                    # GET_FIRMWARE_VERSION
    "board",                  # GET_BOARD_TYPE
    "stats-core",             # GET_STATS (core)
    "stats-radio",            # GET_STATS (radio)
    "stats-packets",          # GET_STATS (packets)
]

# Bridge solo soporta comandos binarios via SDK:
# send_msg, send_chan_msg, reboot, set_tx_power, etc.
```

---

## 7. Gestión de Contactos

### 7.1 Formato Diferente

```python
# SDK Contact (reader.py:100-140):
# 32 bytes pubkey
# 1 byte type
# 1 byte flags  
# 1 byte plen (path_len + hash_mode)
# 64 bytes path
# 32 bytes adv_name
# 4 bytes last_advert
# 4 bytes adv_lat (signed, /1e6)
# 4 bytes adv_lon (signed, /1e6)
# 4 bytes lastmod
# Total: ~147 bytes

# Bridge NodeAdvertisement (protocol_types.py:368-418):
# 2 bytes node_id
# 4 bytes short_name
# 20 bytes long_name  
# 1 byte hw_model
# 1 byte fw_version
# 4 bytes lat (signed, /1e7)
# 4 bytes lon (signed, /1e7)
# 2 bytes altitude
# Total: 39 bytes
```

**Problema**: Bridge usa `NodeAdvertisement` (39B) que **NO existe en el protocolo real**. El firmware envía `CONTACT` (tipo 3) con formato de 147+ bytes.

### 7.2 Sync de Contactos

```python
# SDK (reader.py:96-163):
# Secuencia: CONTACT_START → CONTACT* → CONTACT_END
# Bridge: No implementa esta secuencia
```

---

## 8. Mensajes de Texto

### 8.1 Formato Diferente

```python
# SDK CONTACT_MSG_RECV (reader.py:219-244):
# 6 bytes pubkey_prefix
# 1 byte plen (path info)
# 1 byte txt_type
# 4 bytes sender_timestamp
# [4 bytes signature si txt_type=2]
# remaining: text UTF-8

# SDK CHANNEL_MSG_RECV (reader.py:275-309):
# 1 byte channel_idx
# 1 byte plen (path info)
# 1 byte txt_type
# 4 bytes sender_timestamp
# remaining: text UTF-8 (null-padded)

# Bridge TextMessagePayload (protocol_types.py:343-365):
# 1 byte channel_idx
# 16 bytes sender_alias
# 1 byte text_len
# N bytes text
```

**Problema**: Bridge espera formato fijo de 18+ bytes. SDK usa formato variable con path info y timestamps.

### 8.2 V3 Messages No Manejados

```python
# SDK tiene CONTACT_MSG_RECV_V3 (16) y CHANNEL_MSG_RECV_V3 (17)
# que incluyen SNR y reserved bytes adicionales
# Bridge NO maneja estos tipos
```

---

## 9. Tabla Resumen de Incompatibilidades

| # | Categoría | Severidad | Descripción |
|---|-----------|-----------|-------------|
| 1 | Protocol | **CRÍTICA** | `OpCode` vs `PacketType` — namespaces diferentes |
| 2 | Protocol | **CRÍTICA** | ~30+ comandos SDK no implementados |
| 3 | Protocol | **CRÍTICA** | ~35+ tipos de paquete no manejados |
| 4 | Eventos | **ALTA** | Sistema de eventos numérico vs string enum |
| 5 | Eventos | **ALTA** | Solo 4/60+ eventos manejados |
| 6 | Telemetría | **ALTA** | `TelemetryPayload` no existe en firmware real |
| 7 | Telemetría | **ALTA** | STATUS_RESPONSE se descarta silenciosamente |
| 8 | Stats | **ALTA** | STATS response se descarta silenciosamente |
| 9 | MQTT | **MEDIA** | Topic structure incompatible con bridge oficial |
| 10 | MQTT | **MEDIA** | Formato de mensaje diferente |
| 11 | Serial | **ALTA** | Protocolo binario vs CLI de texto |
| 12 | Contactos | **ALTA** | `NodeAdvertisement` vs `CONTACT` format |
| 13 | Contactos | **MEDIA** | Sin secuencia CONTACT_START/END |
| 14 | Mensajes | **ALTA** | Formato fijo vs variable con path/timestamp |
| 15 | Mensajes | **MEDIA** | V3 messages no soportados |
| 16 | LPP | **MEDIA** | Sin MMA/ACL parsing |
| 17 | LPP | **BAJA** | Encoder diferente |

---

## 10. Recomendaciones

### Prioridad Crítica (Rompe compatibilidad)

1. **Unificar namespace de tipos**: Mapear `OpCode` → `PacketType` correctamente
2. **Implementar parser de STATUS_RESPONSE**: Usar `parse_status()` del SDK
3. **Implementar parser de STATS**: Manejar sub-tipos CORE/RADIO/PACKETS
4. **Corregir CONTACT parsing**: Usar formato real de 147+ bytes

### Prioridad Alta (Pierde funcionalidad)

5. **Expandir event handler**: Soportar al menos 20+ eventos principales
6. **Implementar V3 messages**: `CONTACT_MSG_RECV_V3`, `CHANNEL_MSG_RECV_V3`
7. **Alinear topicos MQTT**: Usar sistema configurable del SDK
8. **Implementar CHANNEL_DATA_RECV**: Para datos binarios en canales

### Prioridad Media (Mejora compatibilidad)

9. **Agregar MMA/ACL parsing**: Para telemetría avanzada
10. **Implementar faltantes críticos**: BATTERY, DEVICE_INFO, MSG_SENT, etc.
11. **Soporte para Private Key export/import**: Para setup inicial

---

## 11. Conclusión

El bridge tiene una **capa de abstracción bem definida** (BaseSerialAdapter, MeshcoreSDKAdapter) pero su implementación interna **diverge significativamente** del protocolo real. El código actual está optimizado para un caso de uso específico (text messaging básico) y pierde la mayoría de las funcionalidades del firmware.

**Nivel de compatibilidad actual**: ~25% del protocolo SDK  
**Esfuerzo estimado para completar**: 40-60 horas de desarrollo

---

*Reporte generado por el Lead Orchestrator & System Architect Agent*  
*Basado en análisis de /src/ vs /reference/meshcore_py/ y /reference/meshcoretomqtt/*
