# WEB-01: privacidad de respuestas CLI en capturas públicas

Fecha: 2026-10-05. Estado: corregido en código y verificado con SDK simulado; sin pruebas de radio física.

## Problema y reproducción previa

`RxEventRouter.handle_event()` copiaba texto, payload completo y bytes de respuestas CLI en `PacketBuffer` antes de que `notify_command_response()` identificara la respuesta como sensible. El canal semántico podía ocultar el secreto, mientras `rf_packet`, `/api/packets`, JSON, CSV, hexadecimal y PCAP lo conservaban. Una respuesta escalar CLI sin correlación y sin etiqueta tampoco tenía contexto suficiente para decidir si era una contraseña.

Se agregó una regresión de comportamiento esperado antes de modificar producción:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_capture_privacy.py -k secret -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/capture-privacy-before-tmp
```

Resultado previo: **7 fallos, 3 casos no seleccionados**. Los fallos confirmaron exposición con `Event` SDK, diccionario normalizado, respuestas CLI sin waiter y las dos entradas de `PacketBuffer.record()`; los marcadores eran sintéticos. La reproducción no leyó credenciales ni archivos de una estación operativa.

## Solución y política de publicación

- El sniffer conserva metadatos de recepción, emisor, destino, calidad RF y tamaño para las respuestas de administración, pero sustituye el texto por una indicación de contenido protegido. No almacena los bytes originales ni el payload arbitrario, incluidos objetos anidados y copias hexadecimales. La política conservadora se aplica a `txt_type=1`/`text_type=1`, mensajes administrativos del repetidor y `CLI_REPLY`.
- `PacketBuffer` impone la protección tanto con parámetros individuales como con `PacketInput`, aunque una entrada alternativa no pase por el router. La marca `content_redacted` en el payload distingue esas capturas. No se sintetizan bytes del secreto al preparar una exportación.
- La captura no invoca ni consume waiters. El evento privado continúa al handler; `notify_command_response()` recibe una sola vez el texto original. La respuesta sensible correlacionada se oculta en MQTT/WebSocket y la respuesta no sensible correlacionada sigue visible como `repeater_response`.
- Una respuesta `txt_type=1` sin correlación se publica únicamente como “Respuesta de administración no asociada”. Tampoco se interpreta su escalar como telemetría de batería. Las respuestas locales `CLI_REPLY` no se publican desde el router; el evento original permanece disponible al dispatcher privado SDK.
- El chat normal de clientes, incluido texto firmado (`txt_type=2`) y texto que empieza con `af|`, conserva contenido y bytes. La política no considera que ese prefijo por sí solo convierta un chat de cliente en un secreto.

Archivos: `src/rx_router.py`, `src/packet_buffer.py`, `tests/test_capture_privacy.py`. No cambia comandos RF, intervalos, temporizadores, reintentos ni persistencia de configuración. Impacto de airtime: **ningún paquete adicional**, sin nuevos envíos MQTT ni bucles de feedback; sólo se restringe el contenido de publicaciones ya existentes.

## Verificación posterior

```powershell
.venv/Scripts/python.exe -m pytest tests/test_capture_privacy.py tests/test_domain_official_compatibility.py tests/test_packet_buffer.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/capture-privacy-final-tmp
.venv/Scripts/python.exe -m ruff check src/rx_router.py src/packet_buffer.py tests/test_capture_privacy.py
.venv/Scripts/python.exe -m mypy --strict src/rx_router.py src/packet_buffer.py
```

- Pytest: **61 casos aprobados**; la regresión propia contiene 12 casos.
- Ruff: sin incidencias en los tres archivos.
- Mypy estricto: sin incidencias en los dos módulos de producción.
- Casos: secretos etiquetados y sin etiqueta, valor numérico, payload anidado, raw/hex, JSON/CSV/PCAP, evento SDK y dict, waiter privado entregado una vez, control administrativo no sensible, chat normal/firmado, `PacketInput` y `CLI_REPLY` SDK/raw propio.

Durante el desarrollo se corrigió una expectativa del fixture que consultaba el inexistente atributo `battery_mv`; el control real usa `battery_pct`. Esa incidencia de prueba no es un defecto de producción ni se incluye en los siete fallos de reproducción inicial.

## Límites

Las capturas de administración ya no permiten inspeccionar su contenido arbitrario en el sniffer, incluso cuando una respuesta asociada es pública en `repeater_response`: es una decisión de confidencialidad para un canal sin contexto del comando. No se borran exportaciones previamente guardadas por un operador. La prueba cubre el recorrido real de `bridge.on_mesh_event()` con adaptadores/mocks aislados; no acredita interoperabilidad RF ni todos los posibles emisores externos de credenciales. El control de autenticación de endpoints y la sanitización de otras respuestas administrativas corresponden a sus correcciones independientes.
