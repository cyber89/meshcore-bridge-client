---
name: lora-packet-simulator
description: >-
  Simulador de entorno de malla LoRa y reproductor de tramas serie (PCAP / Hex log) en memoria.
  Permite verificar flujos completos de radio, topologías de múltiples nodos y conmutación de
  repetidores sin hardware físico ni ocupar el espectro radioeléctrico.
---

# LoRa Packet Simulator & Virtual Mesh Skill

Esta skill proporciona un entorno de simulación en memoria para depurar y verificar el comportamiento de **MeshCore Bridge** ante tráfico LoRa real o sintetizado, eliminando la dependencia de hardware físico (transceptores USB SX1262/SX1276).

---

## 1. Capacidades Principales

1. **`VirtualSerialAdapter` en Memoria**:
   - Emula la capa UART del transceptor MeshCore utilizando colas asíncronas `asyncio.Queue`.
   - Permite inyectar tramas serie delimitadas con `SOF` (`0xAA 0x55`), byte stuffing y `EOF` (`0x55 0xAA`).
2. **Reproducción de Trazas (Packet Replay)**:
   - Lee archivos de captura en formato JSON, CSV o volcado hexadecimal (`.hex`, `.log`) y los reproduce con temporización configurable.
3. **Simulación de Topologías de Malla**:
   - Simula escenarios de múltiples saltos (*hops*): Emisor $\to$ Repetidor $\to$ Estación Base Local.
   - Introduce de forma determinista:
     - Pérdida artificial de paquetes (Packet Error Rate / PER).
     - Variación de RSSI y SNR para evaluar el cálculo de métricas LQI.
     - Duplicación de tramas para probar el búfer de `MessageDeduplicator`.

---

## 2. Ejecución del Simulador

Para ejecutar un escenario de prueba en memoria:

```bash
# Simular ráfaga de 10 paquetes broadcast y 2 directos a través de un repetidor virtual
python .agents/skills/lora-packet-simulator/scripts/simulate_virtual_mesh.py --scenario multi_hop --nodes 5

# Replay de un archivo de log hexadecimal capturado en campo
python .agents/skills/lora-packet-simulator/scripts/simulate_virtual_mesh.py --replay data/sample_packets.json
```

---

## 3. Integración con el Protocolo de Testing

- Al depurar un bug en el parser o en el enrutamiento LQI, **usar esta skill para construir el bucle de reproducción rojo antes de modificar el código**.
- Garantiza cumplimiento de la regla de airtime: todas las pruebas ocurren en memoria RAM, con cero emisiones al espectro físico.
