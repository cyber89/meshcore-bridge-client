# RUNTIME-01 — Restaurar el despacho de rutas pasivas

Fecha: 2026-10-05. Corrección de dispatch, consulta local SDK y observaciones RF.

## Reproducción y descubrimiento adicional

`SystemHandler` aceptaba PATH_UPDATE y `TelemetryHandler` los logs antes de
alcanzar los helpers de rutas del router. La regresión mantenida comienza en
`handle_event(Event(...))`, usa el registro real y la entrada serializada del
adaptador. Antes de corregir: **5 fallos y 4 controles aprobados** en nueve casos.
Los fallos muestran ausencia de GET_CONTACT_BY_KEY y de `last_rx_route`.

La lectura del helper reveló otra causa: llamaba `get_contact`, inexistente en
el SDK oficial. Además sólo aceptaba un dict, aunque el SDK entrega un `Event`.
La fuente `reference/meshcore_py/src/meshcore/commands/contact.py` define
`get_contact_by_key(bytes)` con opcode 30 y NEXT_CONTACT/ERROR. El parser entrega
una clave completa y preserva los hashes 00 del path.

## Solución

Cada estrategia propietaria invoca su helper específico. PATH_UPDATE conserva
su publicación como evento de sistema, y solicita el contacto local mediante
`run_sdk_command("get_contact_by_key", bytes.fromhex(key))`, con el mismo lock
Companion y timeout existente de cuatro segundos. Se conserva fallback al
helper de consultas para adaptadores legados sin esa entrada.

Una clave incompleta, inválida o local no dispara consulta. Sólo se actualiza
la ruta si la respuesta tiene el tipo NEXT_CONTACT, coincide con la clave
solicitada y contiene `out_path`. ERROR, respuesta ajena, desconexión o timeout
no sustituyen la ruta previa ni crean un vecino local. La tarea queda registrada
en el conjunto propio y la cancelación se propaga al cierre.

RX_LOG_DATA actualiza `last_rx_route` con su procedencia/trust originales y
publica `contact_updated`. Se conservan hashes 00 y el rol canónico. Estos eventos
usan el flujo específico, evitando la actualización genérica de presencia
que duplicaba publicaciones o inventaba una recepción/salto cero. PATH_UPDATE
se excluye también de capturas y contadores RF: es una notificación Companion.

## Verificación

```powershell
.venv/Scripts/python.exe -m pytest tests/test_passive_route_dispatch.py tests/test_rx_routers.py tests/test_self_info_power_normalization.py tests/test_capture_privacy.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/passive-route-after3-tmp --junitxml=tests/artifacts/passive-route-after.xml
.venv/Scripts/python.exe -m mypy --strict src/rx_router.py src/routers/system_handler.py src/routers/telemetry_handler.py
.venv/Scripts/python.exe -m ruff check src/rx_router.py src/routers/system_handler.py src/routers/telemetry_handler.py tests/test_passive_route_dispatch.py
```

**68 aprobadas**, incluidas nueve regresiones nuevas; mypy y Ruff correctos.
La expectativa de hashes usa una tupla, como el modelo inmutable del registro;
se corrigió una primera expectativa de lista. Una primera invocación con ruta
de prueba inexistente no ejecutó casos; no constituye un fallo de producción.

La integración completa descubrió tres fixtures numéricas que llamaban al
handler directamente con un `SimpleNamespace`, mientras `_dispatch_sdk_event`
siempre entrega `RxEventRouter`. Se actualizaron para construir ese router
sobre el mismo contexto; se conservan las aserciones que impiden contaminar
RSSI/SNR con NaN/inf. El grupo numérico+rutas+estrategias pasó **58 casos**.
No se añadió un guard opcional que omitiera silenciosamente el trabajo de rutas.

## Checklist de radio y límites

1. **Airtime:** cero paquetes RF adicionales. GET_CONTACT_BY_KEY consulta la
   libreta del transceptor por Companion, una vez por notificación recibida.
   El log RF consume datos pasivos ya recibidos.
2. **Feedback:** no hay notificaciones automáticas externas, reintentos ni
   nuevas publicaciones MQTT. El evento del sistema existente se conserva;
   WebSocket comunica el cambio real de ruta. Se excluye la clave propia.
3. **Timers:** no hay scheduler nuevo ni rearme al guardar; se reutiliza el
   timeout puntual existente. No se inventan intervalos/capacidades de radio.

La ráfaga de PATH_UPDATE puede aún acumular tareas esperando el lock: RUNTIME-02
sigue abierto y exige decidir la admisión acotada. Las pruebas no acreditan
rutas físicas ni autenticación del path observado; conservan su trust declarado.
