# ADR 0003: Arquitectura Asíncrona, Resiliencia Serie y Concurrencia No Bloqueante

- **Estado**: Aceptado
- **Fecha**: 2026-09-12
- **Autores**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect)
- **Contexto**: `CONTEXT.md`, `ARCHITECTURE.md`

---

## Contexto y Problema

MeshCore Bridge se ejecuta en hardware embebido (SBCs tipo Raspberry Pi Zero 2W, Raspberry Pi 4/5, Orange Pi) gestionando concurrentemente:
1. Comunicación serie UART/USB bidireccional continua con el transceptor LoRa.
2. Clientes WebSockets y peticiones REST API HTTP.
3. Conexión de red MQTT bidireccional hacia brokers externos.
4. Lecturas/escrituras en persistencia local JSON (decisión vigente: ADR 0005).

Cualquier operación bloqueante (como `time.sleep()`, lecturas síncronas de socket o queries pesadas de disco) en el event loop principal congelaría la recepción de paquetes UART, provocando desbordamiento de búfer en el controlador serie del kernel y pérdida irreversible de tramas de radio.

## Factores de Decisión

1. **Determinismo Temporal**: El procesamiento de bytes entrantes por UART debe ser inmediato para evitar buffers llenos en el chip FTDI/CH340/CP2102.
2. **Resiliencia ante Desconexión Física**: Si el transceptor USB es desconectado o se reinicia eléctricamente, el bridge debe reconectarse automáticamente con *exponential backoff* sin crashear.
3. **Manejo de Backpressure**: Si un suscriptor lento (ej. cliente WebSocket con latencia) no consume los mensajes, la memoria RAM del bridge no debe crecer de forma desmedida.

## Decisión

1. **`asyncio` Puro de Extremo a Extremo**:
   - Todo el flujo del core utiliza corutinas nativas de Python (`async def` / `await`).
   - El puerto serie se gestiona mediante adaptadores asíncronos: SDK Companion oficial y fallback propio `RawSerialFramingAdapter`. El parsing/escaping del fallback no es el framing Companion oficial.
2. **Backpressure mediante Colas Limitadas (`asyncio.Queue(maxsize=...)`)**:
   - Los buses de eventos internos tienen un tamaño máximo prefijado. Si una cola se llena, se descartan los eventos más antiguos o se frena al productor de forma controlada.
3. **Reconexión Automática con Backoff en `src/serial/watchdog.py`**:
   - Se implementa un bucle supervisor que detecta desconexiones del puerto (`SerialException`, `OSError`).
   - `SerialWatchdog` comienza su backoff en 5s, lo multiplica por 1.5 ante fallos y lo limita a 30s; la espera efectiva también está acotada por su intervalo. No se ha identificado jitter en esa implementación. `src/serial_driver.py` es la fachada de compatibilidad hacia `src/serial/`.
4. **Persistencia No Bloqueante y Atómica**:
   - Operaciones de I/O pesadas deben delegarse al executor de hilos (`asyncio.to_thread()`); las escrituras de estado usan temporal adyacente y reemplazo atómico. Atomicidad y no bloqueo son propiedades independientes: `AirtimeTracker.save_history()` realiza actualmente I/O síncrono, por lo que esta directriz no está implementada uniformemente.

## Consecuencias

- **Positivas**:
  - Reducción del riesgo de pérdida de tramas mediante procesamiento asíncrono y supervisión de conexión; no garantiza pérdida cero.
  - Recuperación ante desconexiones cuando el adaptador y hardware permiten reconectar.
  - CPU y memoria acotadas como objetivos de diseño; requieren medición en el hardware y carga de despliegue, no cifras universales garantizadas.
- **Negativas / Compensaciones**:
  - Exige rigurosidad absoluta en el código: prohibición de cualquier función bloqueante síncrona en corutinas.
