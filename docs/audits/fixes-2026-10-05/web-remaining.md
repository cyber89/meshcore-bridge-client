# Correcciones WEB-03 a WEB-11 — 2026-10-05

Esta entrega convierte nueve defectos de la [auditoría web histórica](../layers-2026-10-04/web.md)
en regresiones del comportamiento esperado. El informe histórico y su harness
permanecen intactos. Skills aplicadas: `contract-openapi-sync`,
`html-css-modern-js` y `web-browser-inspection`.

Las pruebas arrancan `VirtualMeshAdapter`, MQTT simulado y un servidor propio en
loopback con puerto asignado por el sistema operativo. Chromium importa los
módulos reales de la SPA; los casos de carreras controlan las respuestas HTTP
o IndexedDB dentro de ese navegador. No usan `.env`, radios físicas, broker de
producción, canales operativos ni una estación existente en 8080.

## Reproducción y estado individual

Antes de modificar producción, `tests/test_remaining_web_regressions.py` produjo
**10 fallos esperados y 1 control positivo**: nueve IDs, dos lecturas de potencia
27/-9 y un control de exclusión de repetidores de contactos. Las expectativas
describen el resultado corregido, por lo que fallar sobre el código previo
acredita cada reproducción. Evidencia inicial: `tests/artifacts/remaining-web-before.xml`.
La primera ejecución después de integrar backend y frontend produjo
**11 aprobadas**, evidencia `tests/artifacts/remaining-web-after2.xml`.

| ID | Reproducción antes | Corrección aplicada | Regresión mantenida principal |
|---|---|---|---|
| WEB-03 | GET de recarga devuelve 200 y ejecuta `reload_mbtiles` sin clave, mientras POST sin clave recibe 401. | `/api/map/reload` y alias `/api/map/refresh` sólo permiten POST. GET/HEAD devuelven 405 sin trabajo. POST conserva la autenticación HTTP existente. | `test_map_reload_get_cannot_mutate`, `test_map_alias_only_authorized_post_reloads` |
| WEB-04 | POST a `/api/channels/does-not-exist` crea un canal y llama al SDK. | Rutas y métodos exactos de canales/contactos. Subrutas desconocidas reciben 404; método equivocado de recurso conocido recibe 405. La ruta individual de contacto sólo acepta DELETE con clave completa canónica. | `test_unknown_channel_route_cannot_perform_mutation`, `test_unknown_or_wrong_method_resources_never_write` |
| WEB-05 | HTTP 503 vacía el textarea, deja el mensaje queued y no muestra aviso. | HTTP, JSON inválido y fallo de red marcan failed, lo persisten y muestran error. El texto se recupera si el mismo feed sigue activo y no existe otro borrador; también hay botón explícito de recuperación, que no transmite. | `test_chat_rejected_http_marks_failed_and_restores_draft`, `test_failed_send_preserves_new_draft_and_supports_explicit_recovery` |
| WEB-06 | El historial lento del canal anterior aparece en el feed activo. | Generación de render, identidad del feed y generación por historial borrado. Las respuestas anteriores se pueden conservar en caché sin modificar el DOM activo; clear invalida cargas pendientes. La historia se concilia con mensajes recibidos durante su lectura. | `test_chat_old_history_cannot_overwrite_new_conversation`, `test_pending_chat_history_cannot_resurrect_clear`, `test_history_merges_messages_received_while_loading` |
| WEB-07 | El éxito actualiza memoria a sent pero IndexedDB conserva queued. | El registro inicial espera fin de transacción antes del envío; el resultado persiste sent. Un estado delivered recibido concurrentemente nunca se degrada a sent/failed. | `test_storage_successful_tx_saved_as_sent`, `test_ack_before_http_response_is_never_degraded_in_indexeddb` |
| WEB-08 | Una respuesta correcta con data [] deja tarjetas anteriores. | Un snapshot completo, incluso vacío, se renderiza. Una consulta fallida o incompleta conserva el directorio confirmado; generaciones descartan lecturas HTTP superadas. | `test_node_snapshot_empty_is_rendered`, `test_partial_node_query_failure_preserves_confirmed_directory` |
| WEB-09 | Valores observados 27/-9 dBm se convierten en 22/2 en el slider. | Edición numérica que representa exactamente la lectura, capacidad desconocida explícita y límites confirmados sólo desde datos del dispositivo. Se retiraron heurísticas de nombres PA/PLUS/V1/V2. | `test_remote_power_observation_preserved`, `test_unknown_power_capability_stays_blank_and_confirmed_values_remain_exact` |
| WEB-10 | Con 250 paquetes, la petición inicial muestra 0..199 y omite los últimos 50. | Contrato `order=asc|desc`, asc por defecto compatible. La SPA pide desc/200, recibe 249..50 y mantiene orden cronológico interno para su vista invertida. | `test_reload_sniffer_uses_latest_200`, `test_packet_order_contract_keeps_default_and_rejects_unknown` |
| WEB-11 | Un snapshot HTTP antiguo pisa un paquete que llegó por WS mientras esperaba. | Conciliación HTTP/stream, identidades de captura y generación de consultas/clear. UUID de sesión del backend evita reutilizar IDs después de reiniciar. Los logs concilian ocurrencias repetidas y preservan registros nuevos. | `test_sniffer_pending_snapshot_preserves_live_packet`, `test_pending_sniffer_snapshot_cannot_resurrect_clear`, `test_snapshot_merges_without_duplicate_packet_or_log_occurrences` |

## Contratos y consecuencias

### Recarga y enrutado

POST autenticado continúa ejecutando una sola reindexación. La SPA de Ajustes ya
usaba POST con sus cabeceras API; la eliminación del GET no requiere nuevos
paquetes ni una nueva pantalla de autorización. Una excepción de reindexación
ahora devuelve 500 `map_reload_failed`, y Ajustes muestra error en lugar de un
toast de éxito. Es una corrección relacionada descubierta al revisar ese camino.

Se mantienen `/api/channels/sync` POST y `/api/channels/export` GET/POST;
`/api/channels` admite GET/POST/DELETE. Contactos mantiene colección,
sync/share/import POST, export GET/POST, discovered GET y accept POST.
Las guardas LOCAL/REPEATER se conservan. Las pruebas de rutas desconocidas y
métodos incorrectos acreditan cero llamadas de escritura SDK.

### Estados del chat y persistencia

Una llamada a `sendMessage` produce como máximo una petición `/api/tx`; recuperar
el borrador únicamente edita el textarea. Se conservan `request_id` y el canal
original aunque el usuario cambie de conversación mientras espera la escritura
IndexedDB. Los destinatarios LOCAL/REPEATER rechazados conservan el borrador.

El fallo de transporte muestra un error de la operación HTTP; no demuestra por
sí solo que el dispositivo nunca transmitiera antes de perderse la respuesta.
La interfaz no reintenta automáticamente ese mensaje ni promete entrega.

La creación y actualización de estado esperan el cierre de sus transacciones.
`updateMessageStatus` conserva delivered cuando ya existe en la base. La
regresión concurrente usa IndexedDB real, inyecta ACK antes de resolver HTTP y
comprueba memoria/almacenamiento delivered y cero entradas ACK pendientes.

Los resultados TX con `delivery_tracking=capacity_exceeded`, `collision` o
`invalid_ack` conservan sent y avisan que el seguimiento no está disponible.
No crean una entrada ACK ni reutilizan un expected_ack sin registro. La SPA
acepta el campo dentro de data o en el resultado raíz por compatibilidad.

La revisión final del diff reprodujo tres fallos adicionales cuando el adaptador
de almacenamiento rechaza una promesa: guardar antes de enviar impedía la petición,
actualizar después de un HTTP exitoso convertía sent en failed, y el rechazo
secundario al persistir failed interrumpía el aviso/recuperación del borrador.
Las escrituras de creación, estado y expected_ack se protegen ahora en un helper
separado del resultado HTTP. El fallo de historial muestra advertencia, conserva
el estado en memoria y nunca cambia una transmisión confirmada a failed. El
rechazo HTTP recupera siempre el borrador aunque la actualización de IndexedDB
también rechace; sigue existiendo una sola petición TX, sin reenvío automático.
Esto cubre rechazos observables del adaptador; no transforma una operación que
un proveedor silencie internamente en una garantía de durabilidad.

### Lectura de potencia

Se cambió el control de rango por un input number vacío cuando no hay lectura.
Los extremos -128..127 expresan la codificación int8 ya existente del protocolo,
no una capacidad física ni autorización para transmitir a esa potencia. El
backend y el dispositivo validan una escritura solicitada por el usuario.
No se introduce una nueva configuración de radio ni se transmite al renderizar.

El DTO remoto ahora devuelve max_tx_power sólo cuando está observado;
min_tx_power/default_tx_power no se inventan. `tx_power_limits_source` distingue
observed/unknown. La SPA conserva también una lectura que no coincida con el
máximo recibido, en lugar de transformarla silenciosamente. Un borrador editado
por el usuario mantiene su valor y su etiqueta cuando llega una actualización.

### Capturas recientes y carreras

GET `/api/packets` añade `order`, que sólo acepta asc/desc: otro valor devuelve
400 `invalid_order`. Offset/limit se aplican después de ordenar el conjunto
filtrado. La respuesta incluye `order` y `session_id`; cada captura REST/WS
incluye su `session_id`. El contador y la sesión sobreviven a clear, y una nueva
instancia de búfer tiene otra sesión.

El cliente combina el snapshot con los eventos que recibió durante la petición,
no con todo el historial previo. Esto permite aceptar snapshots vacíos y evita
conservar indefinidamente datos que el servidor retiró. Consulta posterior,
clear o cambio de sesión invalidan respuestas anteriores. Se conservan los
límites de vista previos; no se añade retención, polling ni carga RF.

Los logs actuales no tienen un ID canónico. La conciliación usa su conjunto de
campos estables y cuenta ocurrencias para conservar dos registros idénticos
reales. Esa estrategia resuelve los escenarios probados, pero no convierte el
fingerprint en identidad universal para productores que alteren campos entre
HTTP y WS; un ID de log futuro sería otro cambio de contrato.

## Limpieza de duplicaciones y riesgos adicionales comprobados

| Elemento | Decisión y evidencia |
|---|---|
| `api_router._safe_int` | Retirado. Búsqueda en src/tests/scripts no encontró consumidores ni importaciones del helper privado; las rutas vigentes usan `_parse_bounded_int`. |
| `SystemController.get_logs` | Conservado como fachada de compatibilidad, delega al lector canónico de LogsController. Ya no mantiene un filtrado paralelo. |
| `LogsController._handle_diagnostics_report` | El router HTTP delega a LogsController para ambos aliases; se eliminó el renderer duplicado del router. Prueba confirma dos llamadas al camino canónico. |
| `SnifferModule.toggleSnifferPause` | API pública compatible conservada y delegada a `setSnifferCapture`; bindings internos siguen usando el setter. |
| `EventBus.once` y seis constantes sin consumidor actual | API pública reservada conservada, decisión explícita: RADIO_STATUS_CHANGE, NODE_DISCOVERED, CHAT_MESSAGE_RECV, FEED_CHANGED, SETTINGS_SAVED y SYSTEM_LOG_RECV. Ausencia de consumo interno no acredita que extensiones externas no la utilicen. No se eliminan para inflar una cifra de limpieza. |

La búsqueda REST de logs ahora usa URL decoding para espacios, tildes, Unicode
y `+` literal codificado. Al comprobarlo se reprodujo otro defecto: los eventos
manuales de WebAPIRouter se añadían sólo a un búfer espejo, mientras GET leía el
handler diagnóstico; sus contadores crecían sin el correspondiente registro.
Se sustituyó ese incremento manual por la entrega de un LogRecord al handler
canónico. El fallback del contexto se conserva cuando no hay diagnóstico.
Tres regresiones verifican búsqueda real y equivalencia de la fachada legacy.

El texto visible de Analítica distingue **totales de sesión** y **ventana
seleccionada con último intervalo parcial**, en coherencia con la corrección
backend Q-04 de esta entrega coordinada. Es etiquetado del período, no una
afirmación de rendimiento medido.

## Verificación

Regresiones nuevas mantenidas:

- [test_remaining_web_regressions.py](../../../tests/test_remaining_web_regressions.py)
- [test_remaining_web_races.py](../../../tests/test_remaining_web_races.py)

Primera ampliación: **37 aprobadas** en 28,73 s,
`tests/artifacts/remaining-web-expanded1.xml`. Una ejecución intermedia antes de
integrar `PacketBuffer(order)` mostró 500 por firma incompatible y fallos de
teardown; se corrigió el contrato antes de declarar éxito. Una ejecución
relacionada posterior detectó los tres fallos reales de registros manuales
descritos arriba (85 aprobadas, 3 fallidas); no se relajaron las expectativas.
La comprobación focalizada de logs/report/recarga tras el arreglo aprobó 5 casos.

Comando final de suites relacionadas:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_remaining_web_regressions.py tests/test_remaining_web_races.py tests/test_rest_controllers.py tests/test_channels_and_contacts_controllers.py tests/test_web_security_and_maps.py tests/test_remote_config_browser.py tests/test_local_config_save_browser.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/remaining-web-related2-tmp --junitxml tests/artifacts/remaining-web-related2.xml
```

Resultado final relacionado: **89 aprobadas en 101,68 s**, evidencia
`tests/artifacts/remaining-web-related2.xml`. La validación completa del conjunto
se registra por separado en el ledger principal. Ruff de `src/web` y los dos archivos
nuevos: correcto. Mypy strict de router y cinco controladores implicados:
correcto. El verificador de paridad encontró 63/63 coincidencias léxicas; esa
salida no sustituye las pruebas de método, autorización y payload anteriores.

Después de ese pase se añadieron las tres regresiones de rechazo de
almacenamiento: **3 fallos antes**, evidencia `tests/artifacts/web-storage-before.xml`;
**7 casos relacionados aprobados en 8,30 s** después, evidencia
`tests/artifacts/web-storage-after.xml`. Los dos archivos nuevos reúnen ahora
**48 casos: 24 con navegador y 24 REST/otros contratos**. La suite global del
principal valida esta última integración.

La primera integración completa de esta segunda entrega detectó una regresión
real adicional de logs: **1363 aprobadas, 3 fallidas y 1 omitida**, 536,67 s.
No era un handler distinto en la fixture: `DELETE /api/system/logs` limpiaba el
mismo handler canónico que usa GET y después escribía en él su propia
confirmación. El resultado observable era un registro INFO inmediatamente
después de borrar. Se reprodujo sin hardware con el gestor diagnóstico real:
**1 fallo en 0,17 s**, `tests/artifacts/web-clear-before.xml`. La regresión
extendida volvió a fallar antes del parche (0,28 s,
`tests/artifacts/web-clear-regression-before.xml`).

Se retiró el registro de confirmación; HTTP 204 confirma el borrado sin
repoblar el buffer ni el espejo. La aserción original de buffer vacío se
conserva y ahora se comprueban también el espejo, GET vacío y los cuatro
contadores a cero. Los eventos reales posteriores siguen entrando en el
handler. Verificación: **12 aprobadas en 0,45 s** al ejecutar
`tests/test_diagnostics.py` y `tests/test_rest_controllers.py`, evidencia
`tests/artifacts/web-clear-after.xml`. Ruff de los dos archivos modificados:
correcto. Este pase focalizado no declara aprobada la integración global;
en ese punto quedaba pendiente repetirla tras corregir los otros dos fallos.

El principal completó después la segunda ronda integrada: **1369 aprobadas,
1 omitida, cero fallos/errores** en 474,23 s, evidencia
`tests/artifacts/remaining-fixes-2026-10-05/maintained-verified.json` y XML del
mismo nombre. Los 136 casos de navegador con Page aprobados incluyen los 24
nuevos de estos dos archivos; no se suman dos veces. La cobertura Python fue
74,32%; el skip es exclusivamente la creación de symlink no permitida por
Windows. El ledger conserva las dos rondas y la matriz final completa.

## Impacto en la malla y límites

1. **Airtime:** las correcciones de lectura, DOM, IndexedDB, logs y rutas no
   generan paquetes RF adicionales. Envío de chat conserva una petición por
   acción explícita y los controles administrativos mantienen sus operaciones.
2. **Spam/feedback:** ningún fallo o borrador recuperado provoca reenvío, ping,
   telemetría, MQTT ni tarea periódica nuevos. Las rutas rechazadas no llaman SDK.
3. **Timers:** no se crea ni rearma ningún scheduler. Se usan generaciones
   síncronas para invalidar respuestas obsoletas, no timers de consulta.

Las pruebas demuestran los contratos aislados descritos. No certifican
interoperabilidad radio real, rendimiento en SBC, accesibilidad WCAG completa
ni todas las hipótesis sin reproducción de la auditoría histórica.
