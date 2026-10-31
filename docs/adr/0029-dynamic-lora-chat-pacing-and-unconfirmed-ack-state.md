# ADR 0029: Pacing Dinámico de Chat LoRa y Transición a ACK No Confirmado

- **Estado**: Aceptado
- **Fecha**: 2026-10-31
- **Autores**: Lead Orchestrator & System Architect
- **Contexto**: `src/web/static/js/modules/chat.js`, `src/rate_limiter.py`, `src/core/ack_tracker.py`, `tests/test_chat_reading_browser.py`, `tests/test_playwright_e2e_simulation.py`

---

## Contexto y Problema

LoRa es un medio de comunicación inalámbrico compartido, *half-duplex* y de ancho de banda severamente restringido. Cada transmisión ocupa el espectro durante cientos de milisegundos o incluso segundos, según el factor de dispersión (*Spreading Factor*, SF) y ancho de banda (*Bandwidth*, BW) configurados.

En la aplicación cliente (`ChatModule` en `src/web/static/js/modules/chat.js`), existían dos problemas que degradaban la salud de la red y la fiabilidad de la interfaz:

1. **Riesgo de Saturación Local y Colisiones en la Malla**:
   - Tras enviar un mensaje de texto o directo (DM), el campo de texto y el botón de envío se re-habilitaban de inmediato. Un usuario podía presionar repetidamente el botón de envío o pegar ráfagas de texto rápidamente, saturando la cola interna del transceptor UART y provocando colisiones en el aire o rechazos por límite de ciclo de trabajo (*duty cycle*).
2. **Estados Pendientes Indefinidos (*Stuck Pending ACKs*)**:
   - Cuando un mensaje solicitaba confirmación de entrega (*ACK*), la interfaz asignaba el estado visual `pending` (mostrando un reloj de espera).
   - Si el nodo destino se encontraba fuera de cobertura, apagado o el paquete ACK de retorno se perdía por ruido RF, el mensaje permanecía en estado "enviando" indefinidamente en la vista del usuario. Esto generaba confusión, induciendo al operador a retransmitir el mismo mensaje repetidas veces y congestionando aún más la malla.

---

## Factores de Decisión

1. **Disciplina de Espectro y Pacing en el Cliente**:
   - Establecer un retraso de cortesía proporcional a la longitud del mensaje antes de permitir una nueva transmisión, mitigando ráfagas no intencionadas.
2. **Determinismo Visual en la Entrega de Mensajes**:
   - La interfaz no debe prometer que un mensaje se está enviando eternamente si la ventana de acuse de recibo de la malla ha expirado.
3. **Semántica Precisa de Estados de Entrega**:
   - Distinguir claramente entre:
     - `sent`: Transmitido con éxito al módem local (confirmado por radio).
     - `delivered`: Confirmado de forma remota por el destinatario mediante ACK correlacionado.
     - `failed`: Rechazado por el hardware local o la cola de transmisión.
     - `ack-unconfirmed`: Transmitido al aire con éxito local, pero sin acuse de recibo recibido tras una ventana de tiempo razonable.

---

## Decisión

Se implementa en `src/web/static/js/modules/chat.js` una política combinada de pacing dinámico y máquina de estados visual:

### 1. Pacing Dinámico de Envío de Chat
Al enviar un mensaje desde la interfaz, el botón `#btnSendMessage` se deshabilita temporalmente durante un intervalo calculado dinámicamente según la carga útil (*payload*):
```javascript
const pacingMs = Math.min(5000, Math.max(1200, 800 + text.length * 25));
```
- Longitudes cortas (ej. "hola"): ~1.2 segundos de enfriamiento.
- Mensajes largos (hasta el límite de 160–200 caracteres): escalan progresivamente hasta 5.0 segundos.
- El botón muestra un estado atenuado durante el enfriamiento y se reactiva automáticamente, protegiendo el búfer de radio del bridge.

### 2. Ventana de Timeout de ACK (45 Segundos)
Para los mensajes que solicitan ACK:
- Al recibir la confirmación local de transmisión (`sent`), se inicia un temporizador de protección en el cliente de 45 segundos.
- Si dentro de los 45 segundos se recibe el evento WebSocket `EVENTS.MESSAGE_ACK_MATCHED` (o actualización de mensaje con `delivered: true`), el temporizador se cancela y se dibuja el doble check verde de entrega confirmada.
- Si el temporizador expira sin recibir confirmación remota, el mensaje transiciona visualmente al estado `ack-unconfirmed`:
  - Se sustituye el icono de reloj por una marca de acuse no confirmado (reloj grisáceo con punto o signo de interrogación discreto).
  - El tooltip explicativo informa al operador: *"Transmitido por radio localmente; sin acuse de recibo recibido en 45 s."*
  - Se respeta la persistencia de SQLite en el backend, donde el registro permanece inmutablemente como `sent` sin alterar datos históricos.

---

## Consecuencias

### Positivas
- **Conservación de Airtime**: Previene el spam impulsivo y respeta los tiempos físicos de propagación de LoRa.
- **Transparencia Operativa**: El operador comprende con exactitud si el mensaje salió de su estación base local y si el destinatario confirmó o no la recepción.
- **Cero Fugas de Memoria**: Los temporizadores de ACK en el cliente se cancelan limpiamente si el mensaje se confirma antes de los 45 s o si se cambia de conversación activa.

### Negativas / Restricciones
- En operaciones de emergencia donde el operador requiera enviar ráfagas manuales continuas, el pacing impone una breve pausa de 1 a 5 s entre mensajes.

---

## Trazabilidad de Código y Verificación

- **Implementación**:
  - `src/web/static/js/modules/chat.js`
  - `src/rate_limiter.py`
  - `src/core/ack_tracker.py`
- **Suites de Verificación**:
  - `tests/test_chat_reading_browser.py` (Mantenimiento de posición de lectura y estados de envío).
  - `tests/test_playwright_e2e_simulation.py` (Entrega de ACK simulada y transición de estados en el navegador).
  - `tests/test_remaining_ack_audit.py` (Correlación y poda de eventos de entrega en backend).
