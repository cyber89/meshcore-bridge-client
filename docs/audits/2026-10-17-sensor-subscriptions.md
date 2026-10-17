# Auditoría de Capa 5: `BINARY_RESPONSE (0x8C)` y Suscripciones Manuales a Sensores (`0x08` / `0x09`)

**Fecha:** 2026-10-17  
**Alcance:** Compatibilidad MeshCore 1.18 (`companion-v1.18.0`, Protocolo Companion v14) — Normalización segura de `BINARY_RESPONSE (0x8C)` y suscripciones manuales de telemetría de sensores (`REQ_TYPE_SUBSCRIBE = 0x08`, `REQ_TYPE_UNSUBSCRIBE = 0x09`).

---

## 1. Contrato Binario Oficial Verificado (`SensorMesh.cpp` & `meshcore_py`)

1. **`BinaryReqType.SUBSCRIBE = 0x08`**:
   - **Solicitud (`CMD_SEND_BINARY_REQ = 0x32`)**: `push_tag (4B non-zero) | timeout_secs (uint16 LE) | reserved (0x00) | min_deltas_len (uint8, 3..14) | min_deltas (CayenneLPP)`.
   - **Preset Equilibrado**: `timeout_secs = 3600` (1 hora), `min_deltas = 016700050174000a` (Canal 1 Temperatura `0.5 °C`, Canal 1 Voltaje `0.10 V`).
   - **Respuesta (`0x8C` `BINARY_RESPONSE`)**: Tras extraer el `tag` de 4B (`expected_ack`) en `meshcore_py/reader.py`, `data` contiene `actual_timeout_secs (uint16 LE) | 0x0000 (2B) | scope_name (c-string)` (o `0x0000` si el sensor rechaza la suscripción).
2. **`BinaryReqType.UNSUBSCRIBE = 0x09`**:
   - **Solicitud (`CMD_SEND_BINARY_REQ = 0x32`)**: Payload vacío (`b""`).
   - **Respuesta (`0x8C` `BINARY_RESPONSE`)**: Tras extraer el `tag` de 4B (`expected_ack`), `data` contiene `8 bytes en cero (0x00 * 8) + 2 bytes aleatorios` (10 bytes en total).
3. **Empuje de Telemetría de Sensor (`0x8C` `PKT_TYPE_ANON_RESPONSE`)**:
   - `SensorMesh::sendPushToSubscriber` envía `push_tag (4B) | sample_timestamp (uint32 LE) | CayenneLPP bytes`.
   - `meshcore_py/reader.py` expone `event.payload["tag"] = push_tag.hex()` y `event.payload["data"] = (sample_timestamp + lpp_bytes).hex()`.

---

## 2. Invariantes de Dominio y Seguridad Aplicadas

- **Sin atribución de emisor no verificada**: `RxEventRouter._extract_normalized_meta` limpia cualquier campo `sender`/`sender_name` en eventos `BINARY_RESPONSE` antes de la correlación por `tag` en `SystemHandler`, impidiendo la creación o contaminación de nodos en `NodeRegistry` ante tramas `0x8C` huérfanas o falsificadas.
- **Protección del token `push_tag`**: El `push_tag` de 4 bytes se almacena exclusivamente en la tabla SQLite `sensor_subscriptions` y se excluye de las vistas públicas (`get_sensor_subscription_public_view`, `/api/nodes`, WebSockets y respuestas REST).
- **Expiración determinista sin renovación automática**: Las suscripciones vencidas (`now >= expires_at`) pasan a `status = 'expired'` en SQLite y nunca se renuevan en segundo plano, preservando el presupuesto de Airtime LoRa.
- **Restricción estricta de roles (`AGENTS.md` §1.1)**: Las acciones `subscribe_sensor` y `unsubscribe_sensor` exigen destino `SENSOR` (`adv_type == 4`) con clave pública completa de 64 caracteres hexadecimales, rechazando `REPEATER`, `ROOM`, `CLIENT` y `LOCAL` con HTTP 422. Los nodos `SENSOR` nunca se incluyen en `list_client_contacts()` ni exponen controles de chat DM.
