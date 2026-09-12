# ADR 0002: Directrices y Salvaguardas Obligatorias de Airtime y Ciclo de Trabajo LoRa

- **Estado**: Aceptado
- **Fecha**: 2026-09-12
- **Autores**: Agente 0 (Lead Orchestrator), Agente 2 (Bridge Architect), Agente 5 (Security Auditor)
- **Contexto**: `CONTEXT.md`, `AGENTS.md` (Sección 4 - Checklist de Impacto en la Malla LoRa)

---

## Contexto y Problema

LoRa opera en bandas ISM no licenciadas (433 MHz, 868 MHz, 915 MHz) con restricciones regulatorias de ciclo de trabajo (*Duty Cycle*, ej. 1% o 10% por hora) y es un medio half-duplex compartido. A Spreading Factors elevados (ej. SF11 o SF12), una sola transmisión de 100 bytes puede tardar más de 1.5 segundos en el aire. Además, en una topología de malla con saltos múltiples (*hop limit*), cada transmisión es reemitida por los repetidores cercanos, multiplicando exponencialmente la ocupación del espectro.

El envío descontrolado de pings automáticos, sondeos periódicos agresivos o timers en bucle puede saturar la red, provocar colisiones de paquetes e infringir las normativas legales de telecomunicaciones.

## Factores de Decisión

1. **Eficiencia Espectral**: La radio debe permanecer en silencio la mayor parte del tiempo, operando bajo el paradigma de "escucha pasiva".
2. **Mitigación de Tormentas de Tráfico (Broadcast Storms)**: Evitar ráfagas de paquetes causadas por reconexiones o eventos concurrentes en MQTT/WebSockets.
3. **Persistencia de Timers**: Los timers de sondeo o cooldown no deben resetearse a cero al guardar la configuración en la WebUI.

## Decisión

Se adopta como contrato inmutable el **Checklist de Impacto en la Malla LoRa** previo a la implementación de cualquier funcionalidad de transmisión:

1. **Pregunta 1: ¿Cuánto airtime consume en la malla?**
   - Prohibido el sondeo activo $O(N)$ (donde $N$ es el número de nodos).
   - Preferir siempre la recepción pasiva de anuncios (`ADVERT`) y telemetría no solicitada sobre el polling activo.
   - Pings, traceroutes y solicitudes remotas tienen intervalos mínimos garantizados de **5 a 15 minutos**.
2. **Pregunta 2: ¿Puede esta feature generar spam o bucles de feedback?**
   - Deduplicación obligatoria con `MessageDeduplicator` en cada paquete entrante y saliente.
   - Limitación de tasa con `RateLimiter` (algoritmo Token Bucket) por canal y por clave pública.
   - Guarda de origen local: el bridge descarta inmediatamente cualquier paquete cuyo remitente sea la clave pública de la propia estación base (`self_info.public_key`).
3. **Pregunta 3: ¿Un guardado de configuración rearma un timer de seguridad?**
   - El timestamp del último disparo de operaciones periódicas o cooldowns debe persistirse en archivo o base de datos, nunca exclusivamente en variables efímeras en RAM.

## Consecuencias

- **Positivas**:
  - Garantía de conformidad con regulaciones de telecomunicaciones.
  - La red de malla permanece descongestionada y con alta tasa de entrega de mensajes útiles.
  - Protección contra ataques de denegación de servicio (DoS) involuntarios o bucles entre MQTT y LoRa.
- **Negativas / Compensaciones**:
  - Respuestas más lentas en telemetría activa (debido a los cooldowns obligatorios).
