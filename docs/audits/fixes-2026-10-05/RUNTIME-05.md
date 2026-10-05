# RUNTIME-05 — Confirmación raw según el opcode Companion

Fecha: 2026-10-05. Base: auditoría `6717e87`. Referencia de lectura:
`reference/meshcore/examples/companion_radio/MyMesh.cpp` y SDK oficial bajo
`reference/meshcore_py/src/meshcore/`.

## Error reproducido

La espera raw aceptaba cualquier respuesta de primer byte menor que 0x80,
excepto el stream de contactos. Un `SET_ADVERT_NAME` (8) terminaba con éxito
al recibir `BATTERY` (12), que corresponde a `GET_BATT_AND_STORAGE` (20).

Antes del cambio, el nuevo caso
`test_setter_ignores_battery_before_its_ok` falló: la trama BATTERY se reenviaba
al propietario del setter y resolvía su future. El transporte era un mock;
no se abrió UART, TCP operativo ni se transmitió radio.

## Solución

`_RAW_REPLY_TYPES` declara las respuestas terminales admitidas por comando
en `sdk_adapter.py`. El observador sólo atribuye a la transacción pendiente
una respuesta de ese conjunto, ERROR (1) o DISABLED (15). Los dos últimos
completan la operación con `False`. Una respuesta síncrona de otro tipo no
se entrega al cliente raw como respuesta de su comando y no confirma el future.
Los pushes >=0x80 conservan el canal asíncrono.

`GET_CONTACTS` admite START (2) y CONTACT (3) sin completar la espera,
y finaliza con END (4). El lock de comandos, timeout configurado y limpieza
en cancelación/desconexión se mantienen. Reboot conserva su contrato
fire-and-forget. No se añade retransmisión automática.

La fixture de `test_tcp_official_compatibility.py` respondía artificialmente
OK a SEND_TXT_MSG y GET_BATT; se corrigió para producir SENT (6) y BATTERY (12),
como el firmware. Se conservan las expectativas de los consumidores TCP.

## Verificación

```powershell
.venv/Scripts/python.exe -m pytest tests/test_raw_response_contract.py tests/test_serial_integration_regressions.py tests/test_tcp_official_compatibility.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/raw-response-after-tmp
.venv/Scripts/python.exe -m mypy --strict src/serial/sdk_adapter.py
.venv/Scripts/python.exe -m ruff check src/serial/sdk_adapter.py tests/test_raw_response_contract.py tests/test_tcp_official_compatibility.py
```

**36 aprobadas**, incluidas 17 regresiones nuevas; mypy y Ruff correctos.
Escenarios: BATTERY ajena antes del OK del setter, doce getters que rechazan
OK genérico, ERROR/DISABLED, timeout sin reintento, stream y pushes intercalados.
La desconexión ya posee control de limpieza en la suite mantenida.

## Límites e impacto

El protocolo no lleva un identificador de petición en OK/SENT. Una respuesta
atrasada **del mismo tipo** sigue siendo ambigua; la tabla evita el defecto
reproducido entre tipos, sin certificar correlación perfecta. No valida todos
los campos de una trama ni mide interoperabilidad física. Un opcode desconocido
no obtiene éxito por una respuesta genérica; requiere soporte explícito.
La telemetría local del comando 39 llega como push, no como confirmación terminal
del pedido raw; se conserva su comportamiento asíncrono/timeout.

Cero comandos adicionales, sin nuevos intervalos, límites de airtime,
reintentos ni timers. El framing continúa siendo Companion oficial; no se
introduce AA55/CRC propio en este transporte.
