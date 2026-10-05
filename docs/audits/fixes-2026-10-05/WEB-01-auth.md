# WEB-01: autorización de lecturas y exportaciones de capturas

Fecha: 2026-10-05. Estado: corregida la omisión de autorización HTTP de WEB-01.
La redacción de respuestas sensibles antes del búfer y del evento `rf_packet`
se trata en la corrección de captura asociada; esta parte no pretende sustituirla.

## Reproducción y causa

Con `BRIDGE_API_KEY` configurada, una conexión HTTP nueva podía consultar
`GET /api/packets` y `GET /api/packets/export?format=json|csv|pcap` sin clave o
con una clave incorrecta. El servidor devolvía 200 y el contenido de capturas.
La lista `sensitive_read_paths` de `MeshCoreWebServer._is_api_auth_valid`
protegía otros documentos sensibles, pero omitía estas rutas.

Se creó un servidor real en loopback con puerto asignado por el SO, búfer real,
una captura sintética y configuración/directorios temporales mediante las
fixtures mantenidas. No se abrió una estación operativa, un broker ni radio física.
Se verificó el fallo antes de modificar producción:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_packet_read_authorization.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/capture-auth-before --junitxml tests/artifacts/layers-2026-10-05/capture-auth-before.xml
```

Resultado inicial: **16 fallos y 11 controles aprobados**. Los fallos incluyen
las respuestas 200 indebidas de listado/exportación y la falta de autorización
previa al rechazo 405 de HEAD. Son regresiones que esperan el comportamiento
corregido, no pruebas documentales que esperan el defecto.

## Cambio y contrato

`src/web/http_server.py` añade exactamente `/api/packets` y
`/api/packets/export` a las lecturas protegidas. La normalización existente
conserva query y barra final admitidas por el router. Se evitó proteger mediante
un prefijo indiscriminado: `/api/packets/debug` y `/api/packetsExtra` continúan
respondiendo 404, sin convertirse en recursos protegidos existentes.

Cuando hay clave configurada:

- GET sin credenciales o con credenciales incorrectas devuelve 401 sin capturas.
- GET con `X-Api-Key` válida o `api_key` codificada en query devuelve el contrato
  previo: listado JSON y exportación JSON, CSV o PCAP dentro de la respuesta JSON.
- Una cabecera incorrecta tiene prioridad sobre una query válida, como en la API
  existente; no se incorpora una segunda política de autenticación.
- HEAD también exige autorización. La respuesta 401 no contiene cuerpo. Una
  HEAD autorizada conserva 405: el controlador no implementa ese método.
- Otras lecturas públicas, como `/api/channels`, conservan su política previa.

Sin `BRIDGE_API_KEY`, se mantiene el modo de desarrollo existente y su aviso de
autenticación omitida. Esta corrección no fuerza una clave ni cambia despliegues.

## Consumidores web y credenciales

La inspección de `src/web/static/js/modules/sniffer.js` y del contexto de la SPA
confirma que el listado, DELETE y exportación ya pasan `getAuthHeaders()`.
La descarga usa `fetch` autorizado y un `Blob` local; no abre una nueva pestaña
ni añade la clave a una URL de descarga. Por tanto, no fue necesario modificar JS.
No existe una ruta de detalle individual de captura en el router vigente.

La comparación constante y el parser de credenciales REST existentes se conservan.
Las regresiones comprueban una clave con `+`, `%` y `&`, su codificación en query,
y que el registro de un rechazo no publique la credencial incorrecta. Los campos
de log sospechoso ya pasan por la redacción de `SecurityTrafficInspector`.
La discrepancia de autenticación WebSocket (WEB-02) queda fuera de este cambio.

## Validación

```powershell
.venv/Scripts/python.exe -m pytest tests/test_packet_read_authorization.py tests/test_web_official_compatibility.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/capture-auth-after --junitxml tests/artifacts/layers-2026-10-05/capture-auth-after.xml
.venv/Scripts/python.exe -m ruff check src/web/http_server.py tests/test_packet_read_authorization.py
```

Resultado: **75 aprobadas y 1 omitida**, Ruff correcto. La omisión pertenece al
control de symlink de la suite existente cuando Windows no concede el permiso
necesario; las **27 regresiones nuevas** de autorización están aprobadas.
Las pruebas atraviesan sockets HTTP, router, controlador y exportadores reales.
No se ejecutó navegador ni se acredita mediante ellas confidencialidad RF o
redacción contextual del contenido, cubierta por la otra parte de WEB-01.
