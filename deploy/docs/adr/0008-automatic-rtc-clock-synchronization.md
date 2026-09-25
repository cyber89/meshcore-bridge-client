# ADR 0008: Sincronización Automática de Reloj RTC (Host Linux hacia Radio y Repetidores)

- **Estado**: Aceptado
- **Fecha**: 2026-09-24
- **Autores**: Agente 0 (Lead Orchestrator & System Architect), Agente 1 (Protocol Investigator), Agente 2 (Bridge Architect)
- **Contexto**: `CONTEXT.md`, `reference/meshcore/`, `reference/meshcore_py/`, `src/admin/local_config_executor.py`, `docs/ARCHITECTURE.md`

---

## Contexto y Problema

Los transceptores y repetidores LoRa MeshCore basados en microcontroladores (ESP32, nRF52840, RP2040) carecen comúnmente de reloj de tiempo real (RTC) con batería de respaldo dedicada (ej. pila CR2032) y, en instalaciones interiores o repetidores de bajo coste, carecen de receptor satelital GPS.
Al encenderse o reiniciar tras un ciclo de energía:
1. El reloj del microcontrolador arranca en el Epoch Unix 0 (`1970-01-01 00:00:00`) o en un valor aleatorio.
2. Las balizas de telemetría y mensajes de texto se emiten con marcas de tiempo desfasadas por décadas.
3. Los filtros de deduplicación temporal y expiración de paquetes de la malla LoRa fallan o descartan paquetes legítimos considerándolos obsoletos o futuros.
4. Los registros de auditoría y análisis de latencia en la WebUI y en MQTT resultan inservibles para diagnóstico forense.

Por el contrario, el host del bridge (SBC Linux / Orange Pi / Raspberry Pi) cuenta con sincronización horaria precisa mediante `systemd-timesyncd`, NTP o GPS del sistema operativo.

## Factores de Decisión

1. **Integridad Temporal de la Malla**: La deduplicación por ventana deslizante (`PacketDeduplicator`) y la correlación de eventos de telemetría dependen de marcas de tiempo UTC consistentes entre el host y los transceptores.
2. **Eficiencia de Airtime (LoRa Duty Cycle)**: La sincronización no debe inundar el medio radioeléctrico. Debe ser local e instantánea para el transceptor USB, y bajo demanda o con enfriamientos prolongados (cooldowns > 1 hora) para nodos repetidores remotos.
3. **Resiliencia ante Reinicios**: La sincronización debe ser automática tras reconexiones del puerto serie USB o reinicios del proceso bridge sin requerir intervención manual del operador.

## Decisión

Se establece el protocolo de **Sincronización Automática de Reloj RTC**:
1. **Sincronización Local Inmediata (Host USB -> Radio Local)**:
   - Al establecer la conexión serie en `serial_driver.py` / `local_config_executor.py`, el bridge invoca inmediatamente el comando de firmware `set_device_time(int(time.time()))`.
   - Se programa una sincronización periódica pasiva de baja frecuencia cada 6 horas para compensar la deriva de cristal del oscilador del microcontrolador.
2. **Sincronización Remota de Repetidores bajo Demanda**:
   - En `repeater_executor.py`, se provee la función `sync_clock` que envía el opcode binario de ajuste de reloj al repetidor remoto utilizando la hora UTC exacta del host.
   - Dicha acción respeta estrictamente el limitador de tasa y no se ejecuta de forma descontrolada para preservar el airtime de la red de malla.
3. **Normalización en el Búfer RX**:
   - Si un paquete recibido presenta una marca de tiempo anómala (anterior al año 2024 o posterior al tiempo actual + 300 segundos), el router RX anota la discrepancia temporal en los metadatos sin descartar la carga útil.

## Consecuencias

- **Positivas**:
  - Telemetría, balizas y logs de chat con marcas de tiempo UTC precisas y sincronizadas al segundo.
  - Funcionamiento perfecto del deduplicador y el rastreador de airtime.
  - Cero esfuerzo manual para el operador tras cortes de energía o reinicios de hardware.
- **Negativas / Compensaciones**:
  - El host debe contar con acceso a internet para NTP o un módulo RTC hardware con batería en el SBC para garantizar hora exacta en entornos aislados (*air-gapped*).
