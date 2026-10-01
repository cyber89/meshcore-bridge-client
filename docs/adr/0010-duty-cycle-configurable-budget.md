# ADR 0010: Duty Cycle como Presupuesto Configurable y Load Shedding

- **Estado**: Aceptado
- **Fecha**: 2026-09-29
- **Autores**: Architecture/protocol audit
- **Contexto**: `src/rate_limiter.py`, configuración MeshCore por región y ADR 0004
- **Supersede**: ADR 0004 §Decisión 1 (“Modo Solo Alerta”) y lenguaje que trate 1% como límite legal universal

---

## Contexto y Problema

ADR 0004 describía `DUTY_CYCLE_LIMIT_PCT=1.0` como límite reglamentario universal y ordenaba
continuar transmitiendo incluso al 100%. Esa descripción no representa dos hechos actuales:

1. las obligaciones de espectro dependen de jurisdicción, banda, sub-banda y configuración del
   despliegue; MeshCore deja la selección regional bajo responsabilidad del operador;
2. el código actual de `TxRateLimiter` ya realiza **load shedding** de paquetes de baja prioridad
## Factores de Decisión

1. Variabilidad regional y regulatoria de los límites de transmisión LoRa en distintas jurisdicciones.
2. Comportamiento real del rate limiter (`TxRateLimiter`) implementando descarte selectivo (load shedding) y no mero aviso.
3. Evitar afirmaciones jurídicas absolutas no respaldadas por certificación formal del software.
4. Coherencia con la persistencia atómica y gobernanza de métricas de airtime.

## Decisión

1. `DUTY_CYCLE_LIMIT_PCT` se documenta como **presupuesto operativo configurable**, no como
   certificación ni valor legal universal.
2. El valor por defecto del proyecto puede ser conservador, pero el operador debe ajustarlo a su
   región y parámetros de radio.
3. Al alcanzar el umbral crítico configurado, `TxRateLimiter` puede suspender/descartar tráfico
   de baja prioridad según la política de colas vigente.
4. Tráfico de mayor prioridad no obtiene una exención legal automática: el bridge registra y
   alerta, mientras la responsabilidad de cumplimiento permanece en la configuración/despliegue.
5. El historial de airtime sigue persistiendo de forma atómica para evitar que reinicios borren el
   presupuesto observado.
6. Las alertas WebSocket/MQTT describen el estado del **presupuesto configurado**, no una conclusión
   jurídica sobre cumplimiento regulatorio.

## Consecuencias

- La documentación coincide con el comportamiento real del rate limiter.
- Se evita prometer cumplimiento regulatorio por un único valor porcentual.
- Los despliegues pueden configurar políticas conservadoras sin confundirlas con una norma global.
