# Especificación Formal del Protocolo MeshCore (UART / LoRa / MQTT)

> **Documento de Contrato de Interfaz**  
> **Single Source of Truth de Protocolo para Agentes de Antigravity**  
> **Versión**: 2.0.0  
> **Firmware Target**: MeshCore Companion USB v1.17+  
> **Arquitectura Target**: ESP32-S3, ESP32-C3, nRF52840, RP2040 (ARM Cortex-M / RISC-V)  
> **Documentación Técnica de Referencia**:
> - [01. Firmware C/C++ Internals](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/reference_analysis/01_FIRMWARE_C_CPP.md)
> - [02. Python SDK & OpCodes](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/reference_analysis/02_PYTHON_SDK.md)
> - [03. CLI & Repeater Management](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/reference_analysis/03_CLI_AND_REPEATER_MANAGEMENT.md)
> - [04. Agent Integration Guide](file:///c:/Users/Ruby/Desktop/meshcore-bridge/docs/reference_analysis/04_INTEGRATION_GUIDE_FOR_AGENTS.md)

---

## 1. Capa Física y Transporte Serial (UART)

| Parámetro | Valor de Configuración | Notas de Implementación |
| :--- | :--- | :--- |
| **Baud Rate** | `115200` bps | Estándar por defecto para bridges USB-CDC y UART nativo |
| **Data Bits** | `8` | Byte completo sin paridad |
| **Parity** | `None` (N) | Sin bit de paridad |
| **Stop Bits** | `1` | 8N1 |
| **Flow Control** | `None` | Control por software / Watchdog activo |
| **Inter-byte Timeout** | `20 ms` | Límite máximo para recepción continua de bytes |
| **Endianness** | `Little-Endian` (LE) | Todos los enteros multi-byte (uint16_t, uint32_t, int16_t, float) |

---

## 2. Capa de Enlace y Framing Determinista

Para garantizar la integridad del flujo serie continuo y evitar falsos positivos ante ruido electromagnético, se utiliza **Framing Delimitado con Byte Stuffing (Escaping)**.

```text
+------+--------+--------+------------+----------+-------+------------+--------------------+-------+------+
| SOF  | OpCode | SeqNum | Src NodeID | Dst Node | Flags | Length (L) | Payload (0..256 B) | CRC16 | EOF  |
| 1 B  |  1 B   |  1 B   |    2 B     |   2 B    |  1 B  |    2 B     |      L Bytes       |  2 B  | 1 B  |
+------+--------+--------+------------+----------+-------+------------+--------------------+-------+------+
```

### Constantes de Delimitación y Escaping
```c
#define MESHCORE_SOF         0xAA   // Start of Frame
#define MESHCORE_EOF         0x55   // End of Frame
#define MESHCORE_ESC         0x1B   // Escape Byte
#define MESHCORE_ESC_MASK    0x20   // XOR mask applied to escaped bytes
#define MESHCORE_BROADCAST_ID 0xFFFF // ID de difusión / canal público
#define MESHCORE_MAX_PAYLOAD 256    // Tamaño máximo de payload útil en bytes
```

### Reglas de Byte Stuffing
Al serializar la trama (Header + Payload + CRC), cualquier byte cuyo valor coincida con `SOF (0xAA)`, `EOF (0x55)` o `ESC (0x1B)` se reemplaza por:
$$\text{Output} \leftarrow [\text{MESHCORE\_ESC},\, \text{Byte} \oplus \text{MESHCORE\_ESC\_MASK}]$$

Al deserializar:
$$\text{Byte Original} \leftarrow \text{Byte Escapado} \oplus \text{MESHCORE\_ESC\_MASK}$$

---

## 3. Algoritmo de Verificación de Integridad (CRC-16 CCITT)

El checksum protege todos los bytes desde `OpCode` hasta el final del `Payload` (antes del CRC y antes de aplicar escaping).

- **Polinomio**: $0x1021$ ($x^{16} + x^{12} + x^5 + 1$)
- **Valor Inicial**: $0xFFFF$
- **XOR Salida**: $0x0000$
- **Endianness en Trama**: Big-Endian (MSB primero) o Little-Endian según flag.

### Implementación Canónica en C/C++:
```c
uint16_t meshcore_crc16_ccitt(const uint8_t *data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= ((uint16_t)data[i] << 8);
        for (int b = 0; b < 8; ++b) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc = (crc << 1);
            }
        }
    }
    return crc;
}
```

---

## 4. Catálogo de OpCodes y Tipos de Paquetes

| OpCode | Mnemónico | Dirección | Descripción |
| :--- | :--- | :--- | :--- |
| `0x01` | `OPCODE_TELEMETRY` | Node $\to$ Bridge | Métricas de batería, sensor solar, temperatura, SNR, RSSI |
| `0x02` | `OPCODE_TEXT_MSG` | Bidireccional | Mensajes de texto en canal público, privado o directo |
| `0x03` | `OPCODE_NODE_ADVERT` | Node $\to$ Bridge | Anuncios de presencia de nodo, alias, modelo de hardware y GPS |
| `0x04` | `OPCODE_ROUTING_INFO` | Node $\leftrightarrow$ Bridge | Tabla de saltos (Next Hop), métricas SNR de enlace y vecinos |
| `0x05` | `OPCODE_ADMIN_CMD` | Bridge $\to$ Node | Comandos de control (reboot, set radio params, channel keys) |
| `0x06` | `OPCODE_ADMIN_RESP` | Node $\to$ Bridge | Respuesta / status code de ejecución de comando admin |
| `0x07` | `OPCODE_ACK` | Bidireccional | Confirmación de recepción de paquete por secuencia |

---

## 5. Layouts de Memoria Binaria (C/C++ Structs)

### 5.1 Cabecera Genérica de Trama (`meshcore_header_t`)
```c
typedef struct __attribute__((packed)) {
    uint8_t  opcode;        // Código de operación (0x01 .. 0x07)
    uint8_t  seq_num;       // Secuencia incremental (0..255)
    uint16_t src_node_id;   // ID del nodo emisor (Little-Endian)
    uint16_t dst_node_id;   // ID del nodo receptor (0xFFFF = Broadcast)
    uint8_t  hop_limit;     // Hops restantes para retransmisión LoRa (0..7)
    uint16_t payload_len;   // Longitud en bytes del payload que le sigue
} meshcore_header_t; // Tamaño: 9 Bytes
```

### 5.2 Payload de Telemetría (`meshcore_telemetry_t`) — OpCode `0x01`
```c
typedef struct __attribute__((packed)) {
    uint16_t battery_mv;    // Voltaje de batería en milivoltios (ej. 4150 = 4.15V)
    uint16_t solar_mv;      // Voltaje panel solar en milivoltios
    int16_t  temp_cdeg;     // Temperatura en centésimas de grado C (ej. 2450 = 24.50 °C)
    uint16_t humidity_pct;  // Humedad relativa en centésimas de % (ej. 6550 = 65.50%)
    uint32_t pressure_pa;   // Presión atmosférica en Pascales (ej. 101325 Pa)
    int8_t   snr_db;        // Relación Señal-Ruido (SNR) en dB del último enlace LoRa
    int16_t  rssi_dbm;      // RSSI en dBm (ej. -95)
    uint8_t  battery_pct;   // Porcentaje de batería 0..100%
} meshcore_telemetry_t; // Tamaño: 16 Bytes
```

### 5.3 Payload de Mensaje de Texto (`meshcore_text_msg_t`) — OpCode `0x02`
```c
typedef struct __attribute__((packed)) {
    uint8_t  channel_idx;   // 0 = Canal público primario, 1..7 = Canales secundarios
    char     sender_alias[16]; // Alias legible del emisor (terminado en null o truncado)
    uint8_t  text_len;      // Longitud del mensaje UTF-8
    char     text[238];     // Buffer de contenido de texto UTF-8
} meshcore_text_msg_t;
```

### 5.4 Payload de Anuncio de Nodo (`meshcore_node_advert_t`) — OpCode `0x03`
```c
typedef struct __attribute__((packed)) {
    uint16_t node_id;       // ID numérico único del nodo
    char     short_name[4]; // Identificador corto (ej: "HEL1")
    char     long_name[20]; // Nombre descriptivo completo
    uint8_t  hw_model;      // 0x01: Heltec V3, 0x02: LilyGO T-Beam, 0x03: RAK4631, etc.
    uint16_t fw_version;    // Versión en formato BCD (ej: 0x0117 = v1.17)
    int32_t  latitude_e7;   // Latitud en grados * 1e7
    int32_t  longitude_e7;  // Longitud en grados * 1e7
    int16_t  altitude_m;    // Altitud sobre el nivel del mar en metros
} meshcore_node_advert_t; // Tamaño: 41 Bytes
```

---

## 6. Mapeo Serial $\to$ JSON $\to$ Tópicos MQTT para n8n

Cada trama binaria validada por el bridge se deserializa a un modelo tipado y se publica en el broker MQTT según la siguiente matriz de enrutamiento:

```mermaid
graph LR
    UART_RX[Trama UART Binaria] --> PARSER[De-framer & Validator]
    PARSER -->|OpCode 0x01| TOPIC_TELEM[meshcore/rx/telemetry]
    PARSER -->|OpCode 0x02 (Ch 0)| TOPIC_PUB[meshcore/rx/public]
    PARSER -->|OpCode 0x02 (Ch > 0)| TOPIC_CH[meshcore/rx/channel/ch_N]
    PARSER -->|OpCode 0x02 (Direct)| TOPIC_DIR[meshcore/rx/direct/NODE_ID]
    PARSER -->|OpCode 0x03| TOPIC_NODES[meshcore/rx/nodes]
    PARSER -->|Todos los eventos| TOPIC_ALL[meshcore/rx/all]

    TOPIC_TELEM --> N8N_NODE[Webhook / MQTT Trigger en n8n]
    TOPIC_PUB --> N8N_NODE
    TOPIC_ALL --> N8N_NODE
```

### 6.1 Formato JSON Emitido por el Bridge (Contrato n8n)
```json
{
  "timestamp": "2026-08-17T16:55:00.123Z",
  "event_type": "TELEMETRY",
  "opcode": 1,
  "seq_num": 42,
  "sender": {
    "node_id": "0x1A2B",
    "node_id_int": 6699,
    "alias": "Heltec-Tower-01"
  },
  "recipient": {
    "node_id": "0xFFFF",
    "is_broadcast": true
  },
  "lora_metrics": {
    "snr_db": 8,
    "rssi_dbm": -82,
    "hop_limit": 3
  },
  "payload": {
    "battery_mv": 4120,
    "battery_pct": 94,
    "solar_mv": 5100,
    "temperature_c": 23.4,
    "humidity_pct": 58.2,
    "pressure_hpa": 1014.2
  },
  "bridge_metadata": {
    "port": "/dev/ttyACM0",
    "crc_valid": true,
    "store_and_forward": false
  }
}
```

---

## 7. Comandos de Transmisión (n8n $\to$ Bridge $\to$ Hardware)

Para emitir mensajes LoRa desde n8n, se publica en el tópico `meshcore/tx`:

```json
{
  "dest_node_id": "0xFFFF",
  "channel_idx": 0,
  "text": "Alerta de Telemetría: Temperatura normalizada.",
  "ack_required": false
}
```

El bridge encola la solicitud en el **Rate Limiter** asíncrono (respetando la ventana de transmisión reglamentaria LoRa para evitar sobrecalentamiento del RF), genera la trama binaria con framing `SOF/EOF/ESC/CRC` y responde en `meshcore/tx/status`:

```json
{
  "status": "SENT",
  "seq_num": 43,
  "dest_node_id": "0xFFFF",
  "airtime_ms": 142,
  "queue_depth": 0
}
```
