---
name: distributed-mesh-simulation
description: >-
  Simulación avanzada de redes de malla distribuidas e ingeniería del caos para LoRa/MeshCore.
  Protocolos de pruebas de estrés multi-nodo, particiones de red, latencia por saltos,
  inyección de tramas binarias corruptas, saturación de colas y análisis automatizado de logs.
---

# Distributed Mesh Simulation & Chaos Engineering Skill

Esta skill define los protocolos, directrices y herramientas para la validación integral y simulación de escenarios extremos en arquitecturas de red distribuida LoRa / MeshCore.

## Principios de Ingeniería del Caos en Redes de Malla

1. **Topología Heterogénea Realista**:
   - Modelar redes con múltiples clases de nodos: Estación Base Gateway, Repetidores de Infraestructura (`REPEATER`), Dispositivos de Usuario (`CLIENT`), Sensores de Telemetría (`SENSOR`) y Servidores de Sala Comunitaria (`ROOM`).
   - Diferentes perfiles de enlace RF: enlaces directos (0 saltos), rutas multihop intermedias (1 a 4 saltos) y nodos al borde de la cobertura.

2. **Inyección de Fallos y Resiliencia**:
   - **Flapping de Enlaces**: Desconexión y reconexión abrupta de repetidores para comprobar la reconfiguración dinámica de rutas en `LqiEngine`.
   - **Corrupción de Tramas (Fuzzing)**: Inyección de tramas con longitudes truncadas, CRC-16 corrupto, secuencias de escape no terminadas y payloads malformados.
   - **Pérdida de Paquetes y Asimetría**: Simular pérdida aleatoria de tramas RF (10-30%) para validar acuses de recibo (ACK) y ventanas de retransmisión.
   - **Saturación de Buffer y Backpressure**: Inyección de ráfagas concurrentes de tráfico para validar colas acotadas y prevención de fugas de memoria.

3. **Verificación Inmutable de Protocolo (SSoT)**:
   - Comprobar que ningún repetidor sea añadido a la lista de contactos (`ADR 0001`).
   - Comprobar que las tasas de envío respeten los tiempos de guarda de airtime (`ADR 0002`).
   - Verificar la ausencia de bucles de retransmisión local hacia la clave pública de la estación base.

4. **Analizador Automatizado de Logs**:
   - Parsear en tiempo real los ficheros de log generados durante las pruebas.
   - Filtrar y alertar inmediatamente ante cualquier `Traceback`, excepción no capturada o error no controlado.
   - Calcular métricas clave:
     - **PDR (Packet Delivery Ratio)**: Porcentaje de paquetes entregados con éxito sobre el total emitido.
     - **RTT (Round Trip Time)**: Cuantiles de latencia ($p50, p95, p99$) en respuestas directas y consultas remotas.
     - **Desglose de Errores**: Conteo categorizado de eventos de rechazo (`CRC_MISMATCH`, `ROUTE_UNREACHABLE`, `BUFFER_FULL`).

## Ejecución de Simulaciones
```bash
python scripts/simulate_extreme_scenarios.py
```
