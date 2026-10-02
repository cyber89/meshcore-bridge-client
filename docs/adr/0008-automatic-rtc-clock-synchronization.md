# ADR 0008: Sincronización Automática de Reloj RTC (Host Linux hacia Radio y Repetidores)

- **Estado**: Aceptado como intención; implementación parcial verificada por lectura
- **Fecha**: 2026-09-24
- **Revisión documental**: 2026-09-29
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

La decisión original establece las siguientes intenciones; el alcance implementado y las partes pendientes se distinguen después:
1. **Sincronización Local Inmediata (Host USB -> Radio Local)**:
   - Sincronizar el reloj local al conectar con la hora del host.
   - Se propuso una sincronización periódica de baja frecuencia cada 6 horas para compensar la deriva del oscilador. No se ha localizado ese scheduler en la implementación revisada; no es un comportamiento disponible ni una nueva autorización para crearlo.
2. **Sincronización Remota de Repetidores bajo Demanda**:
   - Proveer una acción explícita para ajustar el reloj remoto utilizando la hora del host y las guardas RF existentes. La implementación transmite un comando administrativo cifrado, no el opcode de ajuste de reloj local directamente al repetidor.
3. **Normalización en el Búfer RX**:
   - Se propuso anotar metadatos ante timestamps anteriores a 2024 o posteriores a la hora actual + 300 segundos. No se ha localizado esa validación en `rx_router.py`; permanece como intención histórica sin implementar.

## Implementación Observada y Límites (2026-09-29)

- `src/serial/sdk_adapter.py::connect()` programa `_initial_hardware_sync()`, que llama `commands.set_time(int(time.time()))` cuando el SDK dispone del método. La llamada se realiza después de consultas iniciales y registra los fallos; no garantiza sincronización exitosa ni cubre por sí sola el adaptador fallback.
- `src/admin/local_config_executor.py::sync_device_clock()` y `src/admin/cli_command_executor.py::_cli_sync_clock()` permiten sincronización local bajo demanda mediante `set_time()`. El primero distingue resultado parcial; el texto de éxito de la consola no basta para acreditar confirmación del hardware. El epoch es UTC, pero algunos textos de presentación usan `time.localtime()` del host.
- `src/repeater_manager.py::build_repeater_command_payload()` mapea `sync_clock` a `clock sync`; acciones de ajuste como `set_clock` / `set_time` generan `time <epoch>`. `repeater_executor.py` envía el comando remoto mediante su flujo RF. `CommonCLI.cpp` de referencia implementa `clock sync` a partir del timestamp del remitente y `time <epoch>`, rechazando retroceder el reloj.
- No se ha encontrado el scheduler de 6 horas ni el marcador RX de anomalías propuesto en este ADR. Esta revisión no agrega timers, consultas radio ni límites.

Fuentes: `src/serial/sdk_adapter.py`, `src/admin/local_config_executor.py`, `src/admin/cli_command_executor.py`, `src/admin/repeater_executor.py`, `src/repeater_manager.py`, `src/rx_router.py` y `reference/meshcore/src/helpers/CommonCLI.cpp`.

## Consecuencias

- **Positivas**:
  - Telemetría, balizas y logs de chat con marcas de tiempo UTC precisas y sincronizadas al segundo.
  - Mejora de correlación temporal cuando el hardware confirma la sincronización; no constituye una garantía universal del deduplicador o del cálculo de airtime.
  - Sincronización inicial en el adaptador SDK y acciones manuales de ajuste; la periodicidad y los metadatos RX propuestos siguen pendientes.
- **Negativas / Compensaciones**:
  - El host debe contar con acceso a internet para NTP o un módulo RTC hardware con batería en el SBC para garantizar hora exacta en entornos aislados (*air-gapped*).
