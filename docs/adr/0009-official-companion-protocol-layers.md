# ADR 0009: Separación de Capas MeshCore y Transporte Companion Fail-Closed

- **Estado**: Aceptado
- **Fecha**: 2026-09-29
- **Autores**: Protocol/Firmware audit
- **Contexto**: documentación oficial MeshCore, `meshcore_py`, `docs/PROTOCOL_SPEC.md`, ADR 0003 y ADR 0006
- **Supersede/Refina**: cualquier afirmación previa que describa `0xAA/0x55/0x1B + CRC-16` como framing oficial MeshCore

---

## Contexto y Problema

El proyecto conservaba un formato sintético interno (`MeshcoreFrame`) con SOF `0xAA`, EOF `0x55`,
escape `0x1B` y CRC-16. Parte de la documentación lo presentó como framing MeshCore y
`MeshCoreBridge` podía seleccionar `RawSerialFramingAdapter` como fallback de producción.

La auditoría contra upstream confirmó que son capas diferentes:

1. Companion USB/TCP: `0x3C/0x3E + uint16_le(length) + payload`.
2. LoRa on-air: `Packet.h` (`header`, transport codes opcionales, `path_len`, path, payload).
3. `MeshcoreFrame`: formato sintético propio del bridge.

El fallback era además fail-open: el adaptador raw podía reportar conexión/envío sin abrir un
transporte MeshCore real.

## Factores de Decisión

1. Fidelidad al firmware y SDK oficiales.
2. Evitar falsos positivos de conectividad.
3. Hacer explícita la frontera entre Companion, RF on-air y APIs propias del bridge.
4. Mantener temporalmente herramientas legadas sin otorgarles autoridad de protocolo.

## Decisión

1. `MeshcoreSDKAdapter` es el adaptador de producción.
2. `MeshCoreBridge.start()` requiere una sesión Companion válida con el transceptor.
3. `RawSerialFramingAdapter` queda marcado como legacy/test-only y no como transporte transparente de producción.
4. `PROTOCOL_SPEC.md` describe por separado Companion y `Packet.h`.
5. Los diagramas, skills y guías no pueden presentar el CRC/formato sintético como MeshCore.
6. El proxy TCP usa el framing Companion y limita frames a 300 bytes para coincidir con
   `meshcore_py 2.3.14` auditado. Este límite es de compatibilidad de SDK, no MTU LoRa.
7. Cualquier nuevo opcode debe trazarse al firmware, SDK o documentación upstream y registrar
   discrepancias entre esas superficies.

## Consecuencias

- Un entorno sin `meshcore_py` o sin radio válida no debe operar aparentando conectividad ficticia.
- Simuladores que dependan de `MeshcoreFrame` pueden seguir usándolo explícitamente en tests aislados.
- Las incompatibilidades de firmware/SDK aparecen como errores visibles en vez de ser ocultadas por
  un fallback no equivalente.
- Una futura eliminación de `MeshcoreFrame` requiere una migración explícita de herramientas/tests.
