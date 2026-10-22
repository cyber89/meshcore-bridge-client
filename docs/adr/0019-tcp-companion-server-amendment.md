# ADR 0019: Enmienda al Servidor Proxy TCP Companion: Propietario de Respuesta, Clasificación de Tráfico y Límite de 300 Bytes

- **Estado**: Aceptado
- **Fecha**: 2026-10-21
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: Enmienda formal a [ADR 0006](0006-tcp-companion-server-proxy.md), `src/tcp_companion_server.py`, `src/bridge_core.py`, `nuevo.md` (H13)

---

## Contexto y Discrepancia Histórica

El [ADR 0006](0006-tcp-companion-server-proxy.md) describía originalmente un modelo de proxy TCP puramente difusor (*broadcast*) de todas las tramas recibidas desde la radio hacia todos los clientes TCP conectados, con un tamaño máximo de buffer de 512 bytes.

La evolución del código de producción en `src/tcp_companion_server.py` y `src/bridge_core.py` implementó optimizaciones de aislamiento transaccional y límites estrictos dictados por el SDK oficial de MeshCore que no habían sido reflejados en el ADR original:

1. **Tamaño Máximo de Trama (300 Bytes)**:
   - El parser Serial/TCP del SDK oficial `meshcore_py 2.3.14` descarta silenciosamente cualquier trama que exceda 300 bytes.
   - En consecuencia, `src/tcp_companion_server.py:29` fijó `MAX_FRAME_SIZE = 300`. Retener una especificación documental de 512 bytes inducía al error de suponer soporte de tramas sobredimensionadas.

2. **Clasificación de Tráfico y Propietario de Respuesta (`response_owner`)**:
   - Cuando un cliente móvil o CLI envía un comando de control local a la radio (opcodes `< 0x80`), la radio responde con una trama síncrona dirigida a esa transacción específica.
   - Difundir respuestas de control a todos los clientes TCP provocaba interferencias en las máquinas de estado de las aplicaciones móviles conectadas concurrentemente.
   - La implementación actual en `src/tcp_companion_server.py:154–157` clasifica el tráfico:
     - Trama con `opcode < 0x80`: Si existe un `response_owner` asignado a la transacción activa, la trama se envía **únicamente** a ese cliente.
     - Trama con `opcode >= 0x80` (eventos asíncronos de la malla, beacons, mensajes LoRa recibidos): Se difunde en broadcast a todos los clientes TCP activos.

## Decisión

1. **Ratificar formalmente el límite de 300 bytes (`MAX_FRAME_SIZE = 300`)** como la restricción canónica del proxy TCP Companion.
2. **Ratificar el mecanismo de `response_owner` y arbitraje transaccional** implementado en `MeshCoreCompanionServer`:
   - Las transacciones de comandos reservan la asociación con el `StreamWriter` del cliente emisor.
   - Las respuestas unicast no cruzan hacia otros sockets TCP.
   - El broadcast queda restringido a eventos de radio y telemetría asíncrona.
3. **Preservar el texto histórico de ADR 0006**, incorporando una referencia a esta enmienda.

## Consecuencias

- **Positivas**:
  - Elimina la ambigüedad entre la documentación de diseño y el código en producción.
  - Asegura que los desarrolladores y agentes conozcan el límite exacto de 300 bytes y el enrutamiento dirigido de respuestas de control.
- **Negativas / Compensaciones**:
  - Los clientes TCP que requieran payloads mayores a 300 bytes deben fragmentarlos a nivel de aplicación según la especificación de MeshCore.
