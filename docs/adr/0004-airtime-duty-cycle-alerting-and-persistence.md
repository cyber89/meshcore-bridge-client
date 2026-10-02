# ADR 0004: Persistencia Atómica de Airtime y Alertas Progresivas de Duty Cycle LoRa

- **Estado**: Aceptado históricamente; política de solo alerta superada parcialmente por la implementación actual
- **Fecha**: 2026-09-18
- **Revisión documental**: 2026-09-29 (evolución registrada el 2026-09-28)
- **Autores**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 4 (Web UI/UX Architect), Agente 5 (Security Auditor)
- **Contexto**: `CONTEXT.md`, `AGENTS.md` (Sección 4 - Checklist de Impacto en la Malla LoRa), Entrevista técnica `/grill-me`

---

## Contexto y Problema

El protocolo MeshCore opera sobre transceptores LoRa (Semtech SX1262/SX1276) en bandas ISM (868 MHz / 915 MHz / 433 MHz), donde las regulaciones de telecomunicaciones (ej. ETSI en la Unión Europea) imponen un límite estricto de ciclo de trabajo (*Duty Cycle*, comúnmente 1% por hora, equivalente a un máximo de 36 segundos de emisión por ventana de 3600 segundos).

Con anterioridad a este ADR:
1. El historial de transmisiones (`AirtimeTracker`) residía exclusivamente en memoria RAM en una cola efímera (`collections.deque`). Un reinicio del bridge, una recarga de configuración o un fallo de proceso reseteaba a cero el cálculo de tiempo en el aire, violando la regla del Checklist de Impacto en la Malla LoRa (*"¿Un guardado de configuración rearma un timer de seguridad?"*).
2. No existían mecanismos reactivos ni alertas progresivas de dos niveles para advertir a los operadores sobre saturación inminente antes de sobrepasar el 100% del cupo horario.
3. El frontend calculaba de forma fija una escala sobre el 10.0% en vez del límite dinámico configurable por el usuario.

---

## Factores de Decisión

1. **Disponibilidad Operativa en Emergencias vs. Bloqueo**: Ante saturación de duty cycle, bloquear de golpe las transmisiones puede interrumpir comunicaciones críticas o dejar inoperativo un centro de mando en el terreno. Se requirió definir si el bridge debe estrangular, pausar o alertar sin bloquear.
2. **Conformidad Regulatoria y Prevención**: Disparar advertencias tempranas antes de agotar el presupuesto de 36 segundos por hora.
3. **Persistencia No Bloqueante**: La persistencia en disco de las marcas de tiempo debe ser atómica (evitando archivos corruptos en caídas de tensión) y con debounce para no degradar el I/O en SBCs como Raspberry Pi o microSD.

---

## Decisión

La siguiente decisión conserva el acuerdo histórico de 2026-09-18. Su política de solo alerta no describe íntegramente el comportamiento actual; véase la evolución documentada más abajo.

1. **Modo Solo Alerta (Sin Bloqueo)**:
   - El subsistema de transmisión LoRa (`TxRateLimiter` / `AirtimeTracker`) calcula y supervisa en tiempo continuo el tiempo en el aire de cada paquete saliente según los parámetros de modulación Semtech (SF, BW, CR, preámbulo).
   - Al alcanzar o sobrepasar el límite horario (100%), el sistema **emite alertas críticas visuales y telemétricas**, pero **continúa transmitiendo sin descartar ni retrasar paquetes**, priorizando la continuidad operativa del enlace.

2. **Umbrales Progresivos en Dos Fases**:
   - **Nivel Preventivo (Advertencia - Ámbar)**: Disparado al alcanzar el **80%** del límite horario reglamentario (`DUTY_CYCLE_WARN_THRESHOLD_PCT = 80.0`).
   - **Nivel Crítico (Alarma - Rojo)**: Disparado al alcanzar o superar el **100%** del límite horario (`DUTY_CYCLE_LIMIT_PCT = 1.0`).
   - Ambas transiciones se notifican de manera instantánea mediante:
     - Evento WebSocket `duty_cycle_alert` hacia la SPA web.
     - Publicación MQTT en `{TOPIC_PREFIX}/bridge/alert` con nivel de QoS 1.
     - Indicador dinámico visual en el chip de cabecera (`#headerAirtimeChip`) y barra en el panel de Analítica (`AnalyticsModule`).
     - Notificaciones Toast no intrusivas en el navegador.

3. **Persistencia Atómica en Disco (`data/airtime_history.json`)**:
   - Las marcas de tiempo, duración de aire en milisegundos y canal de cada transmisión saliente en una ventana deslizante de 24 horas se guardan en formato JSON estructurado.
   - La escritura se realiza de forma atómica escribiendo a un archivo temporal (`.tmp`) y reemplazando con `os.replace()`.
   - Las escrituras tienen un mecanismo de debounce temporal (máximo una escritura cada 10 segundos bajo tráfico normal, inmediata ante cambios de estado de alerta y obligatoria en el apagado graceful de `MeshCoreBridge.stop()`).
   - Al iniciar, el bridge carga el archivo, poda automáticamente los registros que superen las 24 horas y rehidrata el consumo horario y diario acumulado, manteniendo el duty cycle real tras reinicios.

4. **Alcance Global con Desglose Estadístico por Canal**:
   - El límite de duty cycle supervisa el consumo total del transceptor LoRa físico.
   - Se mantiene un desglose independiente de paquetes y airtime acumulado para cada canal de la malla (Canal 0 y canales 1..7) para auditoría de tráfico por canal.

---

## Evolución e Implementación Observada (2026-09-29)

El hito de 2026-09-28 «Implementación de Airtime Cutoff Dinámico y Pre-Send Delay para Repetidores» amplió la protección del canal. Esta revisión registra el código existente; no introduce políticas, umbrales ni temporizadores nuevos.

- **Duty cycle de TX**: `src/rate_limiter.py::TxRateLimiter._worker_loop()` descarta elementos `TxPriority.LOW` cuando `AirtimeTracker.get_stats()` indica `is_critical`, completando su future con error. La política efectiva ya no es «continuar sin descartar paquetes». Las prioridades superiores siguen el flujo de transmisión y pacing existente; no implica que todas las rutas de envío pasen por esta cola.
- **Ocupación de canal**: es una métrica distinta del duty cycle TX horario. `AirtimeTracker.update_channel_utilization()` aplica cutoff con histéresis, gobernado por `AIRTIME_CUTOFF_ENABLED`, `AIRTIME_CUTOFF_THRESHOLD_PCT` y `AIRTIME_CUTOFF_RESUME_PCT` en `config.py`. Los valores actuales por defecto son 35% para activar y 30% para reanudar. `RepeaterManager` bloquea consultas marcadas `is_automated` durante el cutoff; no es un bloqueo universal de comandos manuales.
- **Persistencia**: `load_history()` / `save_history()` conservan registros de TX, ocupación y estado del cutoff. El airtime TX se registra como estimación (`TxItem.estimated_airtime_ms`), no como medición exhaustiva de todo el tráfico RF. El guardado usa `.tmp` y `os.replace()` con debounce; en esta implementación no usa `fsync()` ni delega esta escritura a `asyncio.to_thread()`.
- **Canales**: el desglose usa índices presentes en los registros; 0..7 de la decisión original no es una capacidad universal del firmware (véase `docs/PROTOCOL_SPEC.md`, sección 8).

## Consecuencias

Las consecuencias siguientes corresponden a la decisión histórica; el alcance actual se describe en la evolución anterior.

- **Positivas**:
  - Máxima transparencia y trazabilidad del uso del espectro radioeléctrico.
  - Alerta temprana que permite al operador moderar el tráfico antes de violar la normativa de telecomunicaciones.
  - La ventana deslizante de duty cycle no se falsifica ni se resetea por un reinicio del bridge.
  - No interrumpe la entrega de mensajes directos, de canal o comandos de administración en situaciones de tráfico denso.
  - Esta consecuencia correspondía al acuerdo de solo alerta. Actualmente existe descarte LOW y suspensión selectiva de consultas automáticas, como se detalla en la evolución.
- **Compensaciones / Mitigaciones**:
  - En modo solo alerta, un operador que ignore las advertencias podría exceder el límite legal de ciclo de trabajo en su región; por ello, las alertas visuales en el header usan micro-animaciones prominentes y se publica el evento en MQTT para supervisión remota en n8n o Home Assistant.
