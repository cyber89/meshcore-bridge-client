# Auditoría de Protocolo MeshCore — 2026-09-29

## Alcance

Auditoría estática de la frontera MeshCore del bridge contrastando:

- documentación oficial de MeshCore (`docs.meshcore.io`);
- firmware upstream `meshcore-dev/MeshCore` (`Packet.h`, `Packet.cpp`, `AdvertDataHelpers.h`, Companion `MyMesh.cpp`, `BaseChatMesh.*`);
- SDK oficial `meshcore-dev/meshcore_py`, auditado en la release `2.3.14`;
- implementación actual de `src/`;
- documentación, ADRs, agentes, skills y fuentes de diagramas del proyecto.

No se ejecutaron pytest, Playwright ni fuzzing durante esta fase, conforme a la política de `AGENTS.md`.

## Fuentes primarias

- https://docs.meshcore.io/companion_protocol/
- https://docs.meshcore.io/packet_format/
- https://docs.meshcore.io/payloads/
- https://docs.meshcore.io/cli_commands/
- https://github.com/meshcore-dev/MeshCore
- https://github.com/meshcore-dev/meshcore_py
- https://pypi.org/project/meshcore/2.3.14/

## Hallazgos y remediaciones

### P-01 — Framing MeshCore confundido con un formato sintético

**Severidad**: alta.

La documentación y `RawSerialFramingAdapter` trataban `0xAA/0x55/0x1B + CRC-16` como si fuera MeshCore. Upstream confirma dos capas diferentes:

- Companion Serial/TCP: `0x3C/0x3E + uint16_le(length) + payload`;
- LoRa on-air: `Packet.h` (`header`, transport codes opcionales, `path_len`, path, payload).

**Acción**: `PROTOCOL_SPEC.md` reescrito por capas; `ARCHITECTURE.md`, ADR 0003/0006, skills y JSON de diagramas corregidos; formato `MeshcoreFrame` etiquetado legacy/test-only.

### P-02 — Fallback de producción podía reportar conexión/envío falsos

**Severidad**: alta.

`MeshCoreBridge` podía seleccionar `RawSerialFramingAdapter`. Ese adaptador no abría hardware y `connect()`/`send_message()` podían aparentar éxito.

**Acción**: producción usa `MeshcoreSDKAdapter`; `MeshCoreBridge.start()` exige una sesión Companion válida; `RawSerialFramingAdapter` falla cerrado; la radio se conecta antes de arrancar MQTT/rate-limiter.

### P-03 — Límite de texto incorrecto (238 bytes)

**Severidad**: alta.

El firmware upstream define `MAX_TEXT_LEN = 10 * CIPHER_BLOCK_SIZE = 160` bytes. Para mensajes de canal, `BaseChatMesh::sendGroupMessage()` antepone `"<sender_name>: "` dentro del mismo presupuesto y trunca el texto si se supera.

**Acción**: validación de DM a 160 bytes UTF-8; validación de canal descuenta el prefijo del nombre local; se evita truncamiento silencioso antes de llamar al SDK.

### P-04 — Canales codificados como 0..7 / 0..15

**Severidad**: media.

El SDK/firmware expone `max_channels` en `DEVICE_INFO`; la capacidad debe tratarse como propiedad del dispositivo.

**Acción**: `sdk_adapter` centraliza `_get_max_channels()`; envío/configuración valida contra la capacidad anunciada; `ChannelsController` deja de fijar `0..7`; README ya no presenta ocho canales como universal.

### P-05 — Puerto TCP implícito 4000

**Severidad**: media.

`meshcore-cli` documenta puerto TCP Companion por defecto `5000`, pero `MeshcoreSDKAdapter` interpretaba `tcp://host` sin puerto como `4000`.

**Acción**: fallback cambiado a `5000`.

### P-06 — Especificación on-air incompleta/incorrecta

**Severidad**: alta documental.

Se mezclaban CRC, framing Companion y paquete RF. También `path_len` se describía de forma ambigua y aparecía un “Hop Limit máximo 7” que no corresponde al modelo actual de MeshCore.

**Acción**: `MAX_PACKET_PAYLOAD = 184`; `MAX_PATH_SIZE = 64`; `path_len` se documenta como 6 bits de count + 2 bits de tamaño de hash menos uno; `Packet::calculatePacketHash()` se documenta según `Packet.cpp`; se elimina el “máximo 7 hops” y se separa de `flood.max`.

### P-07 — Superficie de comandos no idéntica entre firmware y SDK

**Severidad**: media / upstream.

En la auditoría: firmware/docs contienen `CMD_SEND_CHANNEL_DATA = 62`; `meshcore_py 2.3.14` no enumera ese comando; `meshcore_py 2.3.14` enumera `RUN_CLI_COMMAND = 66` y `CLI_REPLY = 29`; esas dos superficies no se confirmaron en el `MyMesh.cpp` auditado.

**Acción**: el proyecto documenta explícitamente el mismatch; `CommandType` conserva 62 por evidencia firmware/docs y 66 por superficie SDK, marcado version-dependent; `PacketType.CLI_REPLY = 29` añadido y marcado version-dependent en la especificación.

### P-08 — SDK mínimo demasiado antiguo para la superficie auditada

**Severidad**: media.

El proyecto aceptaba `meshcore>=2.3.8`, mientras la auditoría y contratos actuales se realizaron contra la release oficial `2.3.14`.

**Acción**: `requirements.txt` y `pyproject.toml` ahora requieren `meshcore>=2.3.14`.

### P-09 — Duty cycle presentado como valor legal universal

**Severidad**: media documental/operativa.

ADRs anteriores presentaban `1%` como límite legal global y “solo alerta”, mientras la configuración regional depende del despliegue y el código actual ya hace load shedding de baja prioridad en estado crítico.

**Acción**: nuevo ADR 0010; ADR 0004 marcado parcialmente supersedido; comentarios/copy hablan de “presupuesto operativo configurado”, no certificación legal.

### P-10 — Diagramas derivados conservaban HDLC/CRC

**Severidad**: media documental.

Los JSON fuente de Archify aún describían HDLC, SOF/EOF y CRC.

**Acción**: JSON fuente corregidos. Los HTML/SVG generados previos quedan marcados como obsoletos hasta su próxima regeneración.

## ADR nuevos

- `0009-official-companion-protocol-layers.md`
- `0010-duty-cycle-configurable-budget.md`

## Riesgos / trabajo pendiente

1. Regenerar los HTML/SVG de `docs/diagrams/` desde los JSON corregidos.
2. Ejecutar, cuando exista autorización explícita, las suites centradas en startup sin SDK/radio, límites UTF-8 de 160 bytes, prefijo de canal, `max_channels` y proxy TCP Companion.
3. Considerar eliminar definitivamente `MeshcoreFrame`/`RawSerialFramingAdapter` cuando ningún simulador o prueba dependa de ellos.
4. Vigilar upstream para resolver el mismatch `SEND_CHANNEL_DATA=62` vs `RUN_CLI_COMMAND=66/CLI_REPLY=29`.
