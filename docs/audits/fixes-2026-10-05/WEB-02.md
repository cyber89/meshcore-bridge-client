# WEB-02: autenticación equivalente en REST y WebSocket

Fecha: 2026-10-05. Estado: corregido. Skills aplicadas: `contract-openapi-sync`
y `security-code-auditor`; se conserva el frontend Vanilla JS vigente.

## Reproducción antes del cambio

La SPA añade a la URL WebSocket la clave mediante `encodeURIComponent`.
REST utilizaba `parse_qs`, pero el handshake WS dividía la query por `&` y
comparaba todavía el texto codificado. Una clave sintética con `+`, `%` y `&`
obtenía 200 por REST y 401 por WS. Además, `hmac.compare_digest` entre strings
con caracteres no ASCII lanzaba `TypeError`, incluso para una clave correcta;
la conexión HTTP terminaba sin respuesta válida. Las claves repetidas se
interpretaron de forma distinta: REST seleccionaba la primera, WS la última.

Se añadieron pruebas de HTTP y upgrade WebSocket reales contra un servidor
propio en loopback, puerto del SO y estado temporal, sin radio, MQTT operativo
ni lectura de `.env`. El cliente finaliza la conexión después del handshake.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_ws_key_encoding.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/ws-key-before --junitxml tests/artifacts/layers-2026-10-05/ws-key-before.xml
```

Resultado antes de corregir: **15 fallos y 25 controles aprobados**. Las
expectativas son las del comportamiento requerido. El rechazo WS de una clave
URLencoded queda demostrado por 401 frente al 101 esperado del upgrade;
el éxito de una lectura REST continúa siendo 200, no 101.

## Corrección y contrato

`MeshCoreWebServer._extract_api_key` extrae la misma credencial para REST y WS.
Utiliza `parse_qs` con decodificación UTF-8 estricta y conserva valores vacíos.
`_has_valid_api_key` compara bytes UTF-8 mediante `hmac.compare_digest`, lo que
admite claves Unicode sin la excepción del comparador de strings.

- La cabecera no vacía `X-Api-Key` tiene prioridad sobre la query. Una cabecera
  incorrecta no queda autorizada por una query correcta.
- En ausencia de una cabecera no vacía, la query debe contener exactamente un
  valor de `api_key`. La codificación URL se deshace una sola vez; los símbolos
  literales siguen perteneciendo a la clave y no se normaliza su contenido.
- Se rechazan con 401 claves ausentes, vacías, incorrectas, UTF-8 inválido y
  parámetros `api_key` repetidos. Esto elimina la selección contradictoria de
  primer/último valor. Los clientes con duplicados deben enviar una única clave;
  la SPA vigente ya lo hace. Una cabecera válida conserva prioridad aunque haya
  valores duplicados en la query que no se usa como fuente de credenciales.
- Se conserva la política existente cuando `BRIDGE_API_KEY` no está configurada.
- Los logs de rechazo de autenticación y del límite de conexiones WS registran
  la ruta sin query; no dependen de reconocer el nombre literal `api_key` para
  evitar publicar la credencial. Se comprueba también `api%5Fkey` codificado.

Se mantienen los cambios de WEB-01 sobre lecturas de capturas y HEAD. No se
modificaron límites, intervalos, reintentos, origen permitido ni transporte RF.
La SPA no requiere cambios: su codificación existente ahora coincide con el
parser del servidor. Esta corrección no sustituye TLS cuando sea necesario
cifrar el transporte HTTP/WS de la instalación.

## Validación posterior

Tras agregar dos casos adicionales del nombre de parámetro codificado, el
archivo nuevo contiene **42 regresiones aprobadas**. Incluye cabecera/query,
claves con símbolos, barra/punto, Unicode, duplicados en ambos órdenes, fallo
seguro de valores UTF-8 inválidos, logs y modo de desarrollo.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_ws_key_encoding.py tests/test_packet_read_authorization.py tests/test_web_official_compatibility.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/ws-key-final-20261005 --junitxml tests/artifacts/layers-2026-10-05/ws-key-final.xml
.venv/Scripts/python.exe -m ruff check src/web/http_server.py tests/test_ws_key_encoding.py
.venv/Scripts/python.exe -m mypy --strict src/web/http_server.py
```

Resultado: **117 aprobadas, 1 omitida**, Ruff y mypy correctos. La omisión es el
control de symlink existente por permisos de Windows. Un intento intermedio de
reutilizar `basetemp` falló al borrar ese directorio con WinError 5; se conservó
la evidencia y se ejecutó con un directorio nuevo. Ese fallo del entorno no
corresponde a una regresión de autenticación. No se necesitó navegador para
acreditar la respuesta HTTP ni el upgrade WS; tampoco se probó hardware real.
