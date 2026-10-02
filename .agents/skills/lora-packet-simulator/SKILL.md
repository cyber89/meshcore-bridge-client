---
name: lora-packet-simulator
description: Reproducir escenarios virtuales y regresiones MeshCore sin hardware; no sustituye la interoperabilidad con radio oficial ni incluye replay PCAP genérico.
---

# Simulación de paquetes

Leer [AGENTS.md](../../../AGENTS.md) y [TESTING.md](../../../docs/TESTING.md).
Ejecutar simulaciones bajo autorización de pruebas, con configuración/datos temporales.
El adaptador del proyecto es [VirtualMeshAdapter](../../../src/virtual_mesh_adapter.py).
Para regresiones del parser raw usar process_incoming_bytes directamente; ese framing
es propio y distinto del Companion oficial, ver [PROTOCOL_SPEC.md](../../../docs/PROTOCOL_SPEC.md).

El helper [simulate_virtual_mesh.py](scripts/simulate_virtual_mesh.py) implementa
únicamente multi_hop: comprobaciones sintéticas de LQI y deduplicación en memoria.
Los nombres flood y stress todavía no tienen implementación y se rechazan con un
error explícito; no ejecutan multi_hop como sustituto. No implementa --replay.

```bash
python .agents/skills/lora-packet-simulator/scripts/simulate_virtual_mesh.py --scenario multi_hop --nodes 5
```

Leer antes los scripts históricos de scripts/: algunos crean un bridge y escriben
datos del DATA_DIR configurado. Priorizar fixtures pytest aisladas para cobertura mantenida.
Guardar regresiones de fallos demostrados en tests/, no únicamente en scratch/.
La simulación comprueba contratos del host; no demuestra pérdida RF real, PDR físico
ni compatibilidad de comandos con todas las versiones de firmware.
