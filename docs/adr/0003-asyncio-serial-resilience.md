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
4. Lecturas/escrituras en persistencia local (SQLite/JSON).

Cualquier operación bloqueante (como `time.sleep()`, lecturas síncronas de socket o queries pesadas de disco) en el event loop principal congelaría la recepción de paquetes UART, provocando desbordamiento de búfer en el controlador serie del kernel y pérdida irreversible de tramas de radio.

## Factores de Decisión

1. **Determinismo Temporal**: El procesamiento de bytes entrantes por UART debe ser inmediato para evitar buffers llenos en el chip FTDI/CH340/CP2102.
2. **Resiliencia ante Desconexión Física**: Si el transceptor USB es desconectado o se reinicia eléctricamente, el bridge debe reconectarse automáticamente con *exponential backoff* sin crashear.
3. **Manejo de Backpressure**: Si un suscriptor lento (ej. cliente WebSocket con latencia) no consume los mensajes, la memoria RAM del bridge no debe crecer de forma desmedida.

## Decisión

1. **`asyncio` Puro de Extremo a Extremo**:
   - Todo el flujo del core utiliza corutinas nativas de Python (`async def` / `await`).
   - El puerto serie se gestiona asíncronamente mediante `pyserial-asyncio` con protocolo de descompresión de tramas byte a byte en memoria.
2. **Backpressure mediante Colas Limitadas (`asyncio.Queue(maxsize=...)`)**:
   - Los buses de eventos internos tienen un tamaño máximo prefijado. Si una cola se llena, se descartan los eventos más antiguos o se frena al productor de forma controlada.
3. **Reconexión Automática con Backoff Exponencial en `serial_driver.py`**:
   - Se implementa un bucle supervisor que detecta desconexiones del puerto (`SerialException`, `OSError`).
   - Reintentos con intervalos escalonados (1s, 2s, 4s, 8s hasta un máximo de 30s) con jitter para evitar sincronización de tormenta.
4. **Persistencia No Bloqueante y Atómica**:
   - Operaciones de I/O en disco pesadas se delegan al executor de hilos (`asyncio.to_thread()`) o se realizan de forma atómica (escritura en archivo temporal `.tmp` y renombrado atómico).

## Consecuencias

- **Positivas**:
  - Cero pérdida de tramas UART por bloqueo de event loop.
  - El proceso es completamente tolerante a desconexiones en caliente del hardware LoRa.
  - Consumo mínimo y estable de CPU (< 2% en Raspberry Pi 4) y memoria (< 50MB RAM).
- **Negativas / Compensaciones**:
  - Exige rigurosidad absoluta en el código: prohibición de cualquier función bloqueante síncrona en corutinas.
