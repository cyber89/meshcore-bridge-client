# Especificación derivada de protocolo e integración MeshCore

> **Estado**: especificación derivada del proyecto, no fuente primaria.  
> **Auditoría técnica**: 2026-09-29.  
> **Fuentes primarias**:
> - [MeshCore — Companion Protocol](https://docs.meshcore.io/companion_protocol/)
> - [MeshCore — Packet Format](https://docs.meshcore.io/packet_format/)
> - [MeshCore — Payloads](https://docs.meshcore.io/payloads/)
> - [MeshCore — CLI Commands](https://docs.meshcore.io/cli_commands/)
> - [meshcore-dev/MeshCore](https://github.com/meshcore-dev/MeshCore)
> - [meshcore-dev/meshcore_py](https://github.com/meshcore-dev/meshcore_py)
>
> La autoridad documental del proyecto está definida en [docs/README.md](README.md). Ante una
> discrepancia, prevalece el firmware/SDK/documentación upstream correspondiente a la capa.

---

## 1. Las tres capas que no deben confundirse

MeshCore Bridge interactúa con tres representaciones binarias diferentes:

1. **Companion Host ↔ Radio**: stream usado por USB Serial y por conexiones TCP del SDK.
2. **Paquete LoRa on-air**: unidad RF definida por `Packet.h`.
3. **Formato sintético legado del bridge**: `MeshcoreFrame` con `0xAA/0x55/0x1B` y CRC-16,
   conservado únicamente para herramientas/simuladores internos.

El formato 3 **no es** el protocolo Companion oficial y **no es** el formato LoRa on-air.

---

## 2. Transporte Companion oficial

### 2.1 App/Host → Radio

```text
+--------+----------------------+-------------------------+
| 0x3C   | length uint16 LE     | command payload         |
| '<'    | 2 bytes              | length bytes            |
+--------+----------------------+-------------------------+
```

### 2.2 Radio → App/Host

```text
+--------+----------------------+-------------------------+
| 0x3E   | length uint16 LE     | response/event payload  |
| '>'    | 2 bytes              | length bytes            |
+--------+----------------------+-------------------------+
```

El primer byte del **payload Companion** es el `CommandType` o `PacketType`; no hay un
`seq_num/src_node_id/dst_node_id` genérico en esta capa.

La implementación actual de `meshcore_py` busca `0x3E` al recibir, emite `0x3C` al enviar y
descarta frames cuya longitud declarada supera 300 bytes. MeshCore Bridge mantiene su proxy TCP
dentro de ese límite por compatibilidad con el SDK Python auditado.

> El límite de 300 bytes es una restricción de la implementación actual del SDK, no debe
> confundirse con `MAX_PACKET_PAYLOAD` del paquete LoRa.

---

## 3. Paquete LoRa on-air (`Packet.h`)

La estructura RF actual es:

```text
[header:1]
[transport_codes:4, solo ROUTE_TYPE_TRANSPORT_*]
[path_len:1]
[path: hop_count * hash_size, hasta MAX_PATH_SIZE]
[payload: hasta MAX_PACKET_PAYLOAD]
```

Constantes oficiales observadas en upstream:

- `MAX_PATH_SIZE = 64`
- `MAX_PACKET_PAYLOAD = 184`

### 3.1 Header de 1 byte

`header = 0bVVPPPPRR`:

| Bits | Campo | Máscara | Significado |
|---|---|---:|---|
| 0–1 | Route Type | `0x03` | Tipo de routing |
| 2–5 | Payload Type | `0x3C` | Tipo de payload |
| 6–7 | Payload Version | `0xC0` | Versión |

### 3.2 Route Types

| Valor | Constante |
|---:|---|
| `0x00` | `ROUTE_TYPE_TRANSPORT_FLOOD` |
| `0x01` | `ROUTE_TYPE_FLOOD` |
| `0x02` | `ROUTE_TYPE_DIRECT` |
| `0x03` | `ROUTE_TYPE_TRANSPORT_DIRECT` |

### 3.3 Payload Types

| Valor | Constante |
|---:|---|
| `0x00` | `PAYLOAD_TYPE_REQ` |
| `0x01` | `PAYLOAD_TYPE_RESPONSE` |
| `0x02` | `PAYLOAD_TYPE_TXT_MSG` |
| `0x03` | `PAYLOAD_TYPE_ACK` |
| `0x04` | `PAYLOAD_TYPE_ADVERT` |
| `0x05` | `PAYLOAD_TYPE_GRP_TXT` |
| `0x06` | `PAYLOAD_TYPE_GRP_DATA` |
| `0x07` | `PAYLOAD_TYPE_ANON_REQ` |
| `0x08` | `PAYLOAD_TYPE_PATH` |
| `0x09` | `PAYLOAD_TYPE_TRACE` |
| `0x0A` | `PAYLOAD_TYPE_MULTIPART` |
| `0x0B` | `PAYLOAD_TYPE_CONTROL` |
| `0x0C..0x0E` | Reservados |
| `0x0F` | `PAYLOAD_TYPE_RAW_CUSTOM` |

### 3.4 `path_len` no es un conteo de bytes

`path_len` empaqueta dos valores:

- bits 0–5: número de hashes/hops;
- bits 6–7: tamaño de hash menos 1.

Ejemplos:

- `0x05`: 5 hashes × 1 byte = 5 bytes de ruta;
- `0x45`: 5 hashes × 2 bytes = 10 bytes;
- `0x8A`: 10 hashes × 3 bytes = 30 bytes.

El descriptor debe satisfacer `Packet::isValidPathLen()`, es decir, el tamaño efectivo de la
ruta no puede exceder `MAX_PATH_SIZE`.

---

## 4. No existe CRC-16 de aplicación en las capas canónicas anteriores

La especificación Companion actual utiliza marcador + longitud + payload. La estructura
`Packet.h` documentada para LoRa tampoco añade un campo CRC-16 de aplicación.

Por tanto, el CRC-16-CCITT de `src/protocol_types.py::MeshcoreFrame` pertenece exclusivamente al
**formato sintético legado del bridge**. No debe utilizarse para describir capturas Companion u
on-air reales ni como prueba de integridad del protocolo MeshCore.

La radio física/LoRa y las capas de transporte pueden disponer de sus propios mecanismos de
integridad a otros niveles; eso no convierte al CRC del formato legado en parte de MeshCore.

---

## 5. Tipos de nodo anunciados

`src/helpers/AdvertDataHelpers.h` define:

| Valor | Tipo upstream | Rol del proyecto |
|---:|---|---|
| 0 | `ADV_TYPE_NONE` | `CLIENT` cuando se trata de un cliente sin tipo explícito |
| 1 | `ADV_TYPE_CHAT` | `CLIENT` |
| 2 | `ADV_TYPE_REPEATER` | `REPEATER` |
| 3 | `ADV_TYPE_ROOM` | `ROOM` |
| 4 | `ADV_TYPE_SENSOR` | `SENSOR` |

Las reglas de producto sobre quién puede aparecer en Contactos o recibir chat están en
[`CONTEXT.md`](../CONTEXT.md); no se duplican aquí.

---

## 6. Payload de contacto Companion

El parser actual de `meshcore_py` consume, después del byte `PacketType.CONTACT`, 147 bytes:

| Offset dentro del payload de contacto | Campo | Tamaño |
|---:|---|---:|
| 0 | public key | 32 |
| 32 | type | 1 |
| 33 | flags | 1 |
| 34 | encoded out_path_len | 1 |
| 35 | out_path storage | 64 |
| 99 | advert/name | 32 |
| 131 | last_advert | 4 LE |
| 135 | latitude | 4 LE signed, /1e6 |
| 139 | longitude | 4 LE signed, /1e6 |
| 143 | lastmod | 4 LE |

Este es un **payload Companion serializado**, no debe confundirse con el layout en memoria o en
filesystem de `ContactInfo` dentro del firmware.

---

## 7. Canales

El protocolo Companion permite consultar la capacidad del dispositivo mediante
`PacketType.DEVICE_INFO`; `meshcore_py` expone `max_channels`. Por ello el bridge no debe
tratar “8 canales” como una propiedad universal del protocolo.

La documentación Companion muestra dispositivos/formatos con índices `0..7`, pero la capacidad
efectiva debe negociarse con el hardware.

### Canal público

El canal público de MeshCore usa una clave/secret conocida públicamente. En consecuencia:

- el tráfico no debe describirse como “sin cifrado”;
- **sí debe considerarse público**, porque cualquiera que conozca la clave pública del canal puede
  participar/descifrar según el protocolo.

El `SET_CHANNEL` Companion documentado utiliza nombre de 32 bytes y secret de 16 bytes.

---

## 8. CommandType Host → Radio

La tabla principal sigue el firmware Companion actual y el SDK oficial cuando coinciden.

| Dec | Hex | CommandType |
|---:|---:|---|
| 1 | 01 | APP_START |
| 2 | 02 | SEND_TXT_MSG |
| 3 | 03 | SEND_CHANNEL_TXT_MSG |
| 4 | 04 | GET_CONTACTS |
| 5 | 05 | GET_DEVICE_TIME |
| 6 | 06 | SET_DEVICE_TIME |
| 7 | 07 | SEND_SELF_ADVERT |
| 8 | 08 | SET_ADVERT_NAME |
| 9 | 09 | ADD_UPDATE_CONTACT |
| 10 | 0A | SYNC_NEXT_MESSAGE |
| 11 | 0B | SET_RADIO_PARAMS |
| 12 | 0C | SET_RADIO_TX_POWER |
| 13 | 0D | RESET_PATH |
| 14 | 0E | SET_ADVERT_LATLON |
| 15 | 0F | REMOVE_CONTACT |
| 16 | 10 | SHARE_CONTACT |
| 17 | 11 | EXPORT_CONTACT |
| 18 | 12 | IMPORT_CONTACT |
| 19 | 13 | REBOOT |
| 20 | 14 | GET_BATT_AND_STORAGE |
| 21 | 15 | SET_TUNING_PARAMS |
| 22 | 16 | DEVICE_QUERY |
| 23 | 17 | EXPORT_PRIVATE_KEY |
| 24 | 18 | IMPORT_PRIVATE_KEY |
| 25 | 19 | SEND_RAW_DATA |
| 26 | 1A | SEND_LOGIN |
| 27 | 1B | SEND_STATUS_REQ |
| 28 | 1C | HAS_CONNECTION |
| 29 | 1D | LOGOUT |
| 30 | 1E | GET_CONTACT_BY_KEY |
| 31 | 1F | GET_CHANNEL |
| 32 | 20 | SET_CHANNEL |
| 33 | 21 | SIGN_START |
| 34 | 22 | SIGN_DATA |
| 35 | 23 | SIGN_FINISH |
| 36 | 24 | SEND_TRACE_PATH |
| 37 | 25 | SET_DEVICE_PIN |
| 38 | 26 | SET_OTHER_PARAMS |
| 39 | 27 | SEND_TELEMETRY_REQ |
| 40 | 28 | GET_CUSTOM_VARS |
| 41 | 29 | SET_CUSTOM_VAR |
| 42 | 2A | GET_ADVERT_PATH |
| 43 | 2B | GET_TUNING_PARAMS |
| 50 | 32 | BINARY_REQ |
| 51 | 33 | FACTORY_RESET |
| 52 | 34 | PATH_DISCOVERY |
| 54 | 36 | SET_FLOOD_SCOPE |
| 55 | 37 | SEND_CONTROL_DATA |
| 56 | 38 | GET_STATS |
| 57 | 39 | SEND_ANON_REQ |
| 58 | 3A | SET_AUTOADD_CONFIG |
| 59 | 3B | GET_AUTOADD_CONFIG |
| 60 | 3C | GET_ALLOWED_REPEAT_FREQ |
| 61 | 3D | SET_PATH_HASH_MODE |
| 62 | 3E | SEND_CHANNEL_DATA |
| 63 | 3F | SET_DEFAULT_FLOOD_SCOPE |
| 64 | 40 | GET_DEFAULT_FLOOD_SCOPE |
| 65 | 41 | SEND_RAW_PACKET |

### Nota de compatibilidad upstream

A fecha de la auditoría:

- el firmware Companion y la documentación oficial contienen `CMD_SEND_CHANNEL_DATA = 62`;
- `meshcore_py 2.3.14` **no lo enumera** en `CommandType`;
- `meshcore_py 2.3.14` sí enumera `RUN_CLI_COMMAND = 66` y expone un helper, pero ese comando no
  fue confirmado en el `MyMesh.cpp` upstream auditado.

Estas diferencias se consideran **surface mismatch upstream**, no licencia para inventar soporte.
El bridge debe negociar/capturar errores y no asumir que todo símbolo del SDK existe en todos los
firmwares.

### `SET_PATH_HASH_MODE`

El valor configura el tamaño de hash de ruta:

- modo 0 → 1 byte por hash;
- modo 1 → 2 bytes;
- modo 2 → 3 bytes;
- modo 3 → reservado/no válido en el formato actual.

---

## 9. PacketType Radio → Host

| Dec/Hex | PacketType |
|---:|---|
| 0 / 00 | OK |
| 1 / 01 | ERROR |
| 2 / 02 | CONTACT_START |
| 3 / 03 | CONTACT |
| 4 / 04 | CONTACT_END |
| 5 / 05 | SELF_INFO |
| 6 / 06 | MSG_SENT |
| 7 / 07 | CONTACT_MSG_RECV |
| 8 / 08 | CHANNEL_MSG_RECV |
| 9 / 09 | CURRENT_TIME |
| 10 / 0A | NO_MORE_MSGS |
| 11 / 0B | CONTACT_URI |
| 12 / 0C | BATTERY |
| 13 / 0D | DEVICE_INFO |
| 14 / 0E | PRIVATE_KEY |
| 15 / 0F | DISABLED |
| 16 / 10 | CONTACT_MSG_RECV_V3 |
| 17 / 11 | CHANNEL_MSG_RECV_V3 |
| 18 / 12 | CHANNEL_INFO |
| 19 / 13 | SIGN_START |
| 20 / 14 | SIGNATURE |
| 21 / 15 | CUSTOM_VARS |
| 22 / 16 | ADVERT_PATH |
| 23 / 17 | TUNING_PARAMS |
| 24 / 18 | STATS |
| 25 / 19 | AUTOADD_CONFIG |
| 26 / 1A | ALLOWED_REPEAT_FREQ |
| 27 / 1B | CHANNEL_DATA_RECV |
| 28 / 1C | DEFAULT_FLOOD_SCOPE |
| 29 / 1D | CLI_REPLY |
| 0x80 | ADVERTISEMENT |
| 0x81 | PATH_UPDATE |
| 0x82 | ACK |
| 0x83 | MESSAGES_WAITING |
| 0x84 | RAW_DATA |
| 0x85 | LOGIN_SUCCESS |
| 0x86 | LOGIN_FAILED |
| 0x87 | STATUS_RESPONSE |
| 0x88 | LOG_DATA |
| 0x89 | TRACE_DATA |
| 0x8A | PUSH_CODE_NEW_ADVERT |
| 0x8B | TELEMETRY_RESPONSE |
| 0x8C | BINARY_RESPONSE |
| 0x8D | PATH_DISCOVERY_RESPONSE |
| 0x8E | CONTROL_DATA |
| 0x8F | CONTACT_DELETED |
| 0x90 | CONTACTS_FULL |

---

## 10. Telemetría y CayenneLPP

Las respuestas de telemetría pueden contener CayenneLPP. A diferencia de los enteros Companion,
los tipos multi-byte de CayenneLPP siguen el endianness definido por CayenneLPP.

El bridge debe delegar el parsing a una implementación CayenneLPP probada y no asumir que todo
sensor utiliza un layout fijo propio del proyecto.

---

## 11. Flooding, rutas y límites

La CLI oficial expone parámetros como `flood.max`; los valores permitidos pueden llegar a 64.
Esto es distinto de `path_len` y de `MAX_PATH_SIZE`.

Reglas:

- no documentar “máximo 7 hops” como invariante MeshCore;
- no tratar `path_len` como número directo de bytes;
- validar siempre `hash_count × hash_size <= MAX_PATH_SIZE`;
- para automatizaciones RF, aplicar además las guardas de airtime del proyecto documentadas en
  los ADR y `CONTEXT.md`.

---

## 12. Interfaz TCP Companion del bridge

`MeshCoreCompanionServer` expone por defecto el puerto 5000 del **bridge**, configurable mediante
`TCP_SERVER_PORT`.

Ese puerto es una decisión del proyecto. No debe presentarse como puerto universal de todo firmware
MeshCore.

El servidor:

1. recibe `0x3C + len + command_payload` del cliente;
2. entrega el payload al transporte Companion conectado a la radio;
3. recibe payloads Companion de la radio;
4. emite `0x3E + len + response_payload` a los clientes TCP.

El límite actual del proxy es 300 bytes para ser compatible con el parser del SDK oficial auditado.

---

## 13. Contratos propios del bridge: REST, MQTT y WebSocket

REST, MQTT, n8n, WebSocket, persistencia JSON, políticas de contactos y rate limiting son capas del
**proyecto MeshCore Bridge**, no parte del protocolo MeshCore upstream.

Sus contratos vigentes se documentan en:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md)
- [CONTEXT.md](../CONTEXT.md)
- [ADR](adr/)

Nunca usar una decisión REST/MQTT del bridge para inferir un opcode o layout del firmware.

---

## 14. Formato sintético legado `MeshcoreFrame`

Para compatibilidad con herramientas históricas existen:

- `SOF = 0xAA`
- `EOF = 0x55`
- `ESC = 0x1B`
- CRC-16-CCITT
- una cabecera interna de 9 bytes.

Este formato está marcado **legacy/test-only**. `RawSerialFramingAdapter` falla cerrado al intentar
usarse como transporte de producción y `MeshCoreBridge` ya no lo selecciona como fallback.

Si en el futuro se elimina toda dependencia de simuladores sobre este formato, estas constantes y
`MeshcoreFrame` deberían retirarse en una migración explícita en vez de seguir presentándose como
MeshCore.
