# Verificación de parámetros de configuración locales y remotos

Fecha: 2026-10-04. Base: `0e1c6f6`. Solicitud: comprobar recepción,
establecimiento, aplicación y recarga de todos los parámetros ofrecidos por la
configuración del nodo local y administración de nodos remotos.

## Plan de trabajo

1. Inventariar los controles y acciones de cada vista; relacionarlos con rutas,
   parámetros canónicos, SDK/CLI oficial y capacidades por rol de dispositivo.
2. Contrastar setters, getters, unidades, validación, persistencia y respuestas
   de firmware. Distinguir despacho, respuesta recibida y cambio aplicado.
3. Reproducir discrepancias usando estado de firmware simulado independiente,
   respuestas SDK/CLI y servidores propios de loopback, sin datos operativos.
4. Corregir backend, parsers/registro y formularios; mantener contratos entre
   REST/WebSocket, informes de cambios parciales y conservación de borradores.
5. Verificar la matriz de parámetros y regresiones mantenidas, mypy strict,
   Ruff y documentación. Registrar fallos iniciales, resultados finales y
   limitaciones de la simulación.
6. Revisar diffs, publicar sólo archivos propios y entregar pasos de aceptación
   para el operador.

Principal: integración, configuración local, QA transversal y documento.
Especialista protocolo: referencias y matriz de capacidades.
Especialista backend: executor remoto, manager, controlador y regresiones.
Especialista frontend: administración remota, textos y pruebas de navegador.
La propiedad de archivos se acuerda antes de las ediciones para evitar conflictos.

Skills: `meshcore-source-inspector`, `contract-openapi-sync`,
`python-patterns-typing`, `web-browser-inspection`, `bridge-test-runner`.

## Checklist LoRa previo a implementación

1. **Airtime:** la tarea corrige operaciones de configuración iniciadas por el
   usuario. No añadirá sondeos, verificaciones RF automáticas, reintentos ni
   timers. Conservará los cooldowns y la cola TX existentes; las pruebas sólo
   usarán radio virtual y mocks. Los comandos de configuración remota actuales
   consumen tráfico por comando y saltos, por lo que el formulario debe evitar
   enviar campos sin cambios y no repetir solicitudes para todos los nodos.
2. **Spam/feedback:** no se añaden notificaciones ni flujos MQTT automáticos;
   ninguna recepción debe disparar una nueva escritura de configuración.
   Un fallo o timeout no debe convertirse en reenvíos indefinidos.
3. **Timers:** no se modifica la programación de seguridad del bridge. Los
   intervalos de anuncios del repetidor pertenecen al firmware y sólo se cambian
   por edición explícita del usuario; guardar otros parámetros no debe
   reconfigurarlos. No se escogerán límites, umbrales o intervalos nuevos.

Si un hallazgo requiere tráfico adicional o un intervalo nuevo, se documentará
como funcionalidad separada y se acordará con el usuario antes de implementarlo.

## Resultado y alcance

Se revisaron las vistas de configuración **local Companion** y administración
**remota de repetidores**, sus setters, getters, validación, respuestas y recarga.
Se corrigieron los defectos descritos abajo y se incorporaron regresiones de
API, serialización, recepción y navegador. La revisión del protocolo cubre
también Room/Sensor para detectar diferencias; no habilita administración de
CLIENT ni convierte esos roles en repetidores.

La aplicación no puede prometer que todo campo histórico sea escribible:
algunos no existen en el firmware y otros dependen de versión o placa. Ahora
se rechazan o deshabilitan, en lugar de simular un guardado en memoria.
**No se conectó ni transmitió a dispositivos físicos.** ACK/lectura simulados
acreditan el contrato del bridge, no el funcionamiento de una placa instalada.

Inventarios completos y evidencia por fuente:

- [Matriz oficial de protocolo](audits/config-parameters-2026-10-04/protocol-matrix.md): comandos, unidades, tamaños, revisiones y capacidades por rol.
- [Inventario remoto de UI](audits/config-parameters-2026-10-04/frontend-remote.md): todos los controles, lecturas, botones y consola.
- [Corrección previa de guardado local](LOCAL_CONFIGURATION_SAVE_FIX_2026-10-04.md): modos de telemetría, baselines y confirmación por campo.
- [Resultados reproducibles](audits/config-parameters-2026-10-04/verification.json): ejecuciones, conteos y límites de esta entrega.

No se modificaron referencias, SDK instalado, dependencias ni datos operativos.
Los contrastes con clientes se limitan a código disponible: SDK/CLI oficiales y
Remote Terminal de tercero con procedencia declarada. No se presenta este
último como la app móvil oficial ni se atribuye una revisión Git no acreditada.

## Matriz local de lectura y escritura

`GET /api/config` es una vista consolidada que puede incluir caché. Para
aceptación sobre hardware se usa refresco explícito; la ausencia de respuesta
no acredita un valor nuevo. Los POST de configuración exigen ACK del SDK,
reportan `applied` por campo y conservan las aplicaciones parciales.

| Parámetro de la vista | Escritura / lectura | Resultado y condición |
|---|---|---|
| Nombre | `set_name` / SELF_INFO | Máximo 31 bytes UTF-8; sincronización de snapshots confirmados. |
| Latitud, longitud | `set_coords` / SELF_INFO | Coordenadas finitas y acotadas; caché coincide con precisión de microgrados del wire. |
| Frecuencia, BW, SF, CR | `set_radio` / SELF_INFO | Grupo completo observado para preservar campos no editados; aliases contradictorios rechazados. |
| TX | `set_tx_power` / SELF_INFO | Límites de hardware existentes; interpretar potencia recibida como int8 firmado. |
| Repeat | `set_radio` / DEVICE_INFO | Dependiente de firmware/banda permitida; no deducir valor del rol del nodo. |
| RX delay, airtime factor | `set_tuning` / `get_tuning` | Factores 0..20 y 0..9 según carga de preferencias del firmware; conservar baseline y precisión wire de milésimas. |
| Telemetría base, ubicación, entorno | `set_other_params_from_infos` / SELF_INFO | Modos 0..2 de permiso para responder solicitudes; no programación periódica. |
| Manual add, política de ubicación, multi-ACK | Mismo paquete Other Params / SELF_INFO | Mantener bits no editados; rechazar lote si falta baseline. |
| BLE PIN | `set_devicepin` / DEVICE_INFO | 0 o 100000..999999; merge de lectura real, API redactada y `has_pin`. |
| Path hash | `set_path_hash_mode` / DEVICE_INFO | 0..2; ausencia/error de getter devuelve 503, no cero fabricado. |
| Autoadd CHAT/overwrite y demás bits | SET 0x3A / GET 0x3B | Mantener bitmask observado; no copiar sólo los dos bits visibles. |
| Autoadd max hops | Byte opcional de SET/GET | 0..64; edición sólo cuando el GET acredita soporte. Firmware antiguo deja el control vacío/deshabilitado. |
| Flood scope | SET 0x3F / GET 0x40 | Nombre canónico `#`, UTF-8 hasta 30 bytes; padding por bytes y SHA256 truncado. Reset envía sólo opcode. |
| Variables de sensor | `set_custom_var` / `get_custom_vars` | Sólo claves implementadas por el firmware. Validar separadores; respuesta vacía elimina caché antigua. Borrado arbitrario no soportado. |
| Reloj | `set_time` / `get_time` | Acción explícita con ACK; lectura/proyección RTC y reloj del host son datos distintos. |
| Métricas, batería, versión, placa, clave pública, límites repeat | Consultas de información/estadísticas | Lecturas, no parámetros editables; ausencia de sensor no equivale a cero confirmado. |
| Intervalo de telemetría, anuncio local, hops, propietario, altitud, posición fija | Sin setter Companion de esos campos | Deshabilitados/rechazados; ninguna escritura RAM se presenta como aplicada. |

La telemetría periódica y su intervalo reportados originalmente por el usuario
no eran comandos del Companion. Habilitarlos exigiría una funcionalidad y un
análisis de tráfico independientes; esta corrección no inventa ese scheduler.
Las políticas de airtime y pre-send del **host** expuestas por la API pertenecen
al bridge, no a la EEPROM del transceptor; no son controles de esta vista. No
se cambia su persistencia ni se afirma haber probado su reinicio físico.

## Matriz remota y confirmación

Todos los controles remotos y sus aliases aparecen en el anexo de protocolo.
El frontend guarda sólo cambios explícitos y completa el grupo RF con cuatro
valores conocidos. Una lectura pendiente o de otro nodo no pisa el borrador.

| Grupo | Parámetros soportados | Lectura / condición de aplicación |
|---|---|---|
| Radio | frecuencia, BW, SF, CR | `set radio` acepta preferencias con reinicio pendiente. `get radio` lee preferencias; no valida RF activo. |
| Potencia y forwarding | TX, repeat | `get tx`, `get repeat`; ACK CLI del comando correcto. Límite TX sólo si placa/máximo observado lo acredita. |
| Anuncios | advert interval; flood advert interval por API/consola | Minutos pares 60..240 o 0; flood en horas 3..168 o 0. Rangos del firmware de referencia, no nuevos timers del bridge. |
| Identidad y propietario | nombre, owner.info | `get name`, `get owner.info`, owner binario. UTF-8 limitado; propietario vacío limpia dato anterior. |
| Posición | latitud, longitud | `get lat`, `get lon` contextuales. Validación geográfica; no inferir coordenadas de cualquier número recibido. |
| Credenciales | contraseña admin, guest password | Respuesta específica/ACK; secretos redactados. Mantener credencial anterior hasta confirmación. No hay getter admin. |
| ACL | clave pública y permission | `setperm` y tabla binaria `req_acl_sync`; `get acl` CLI remoto no es equivalente. |
| Estado, telemetría, owner, vecinos, regiones | Peticiones binarias oficiales disponibles | Payload SDK correlacionado y campos observados; no convertir timeout en tabla vacía ni valores cero. |
| Región preset, hop limit, altitud, posición fija, modo ACL global, identity key de formulario | Sin setter equivalente en el contrato UI | Preset región sólo cambia el grupo RF; los cinco controles restantes quedan deshabilitados y las API rechazan campos no soportados. |

Para compatibilidad, las rutas remotas conservan HTTP 200 con envoltorio
`status: ok` cuando se despacha correctamente. **Se debe comprobar también
`data.status`**, nunca usar HTTP 200 como confirmación del dispositivo:

- `ok` con `applied`: campos aceptados por respuesta CLI; no prueba metrológica de potencia física.
- `saved` y `pending_reboot`: preferencias guardadas; esperar reinicio operativo acordado para validar RF activo.
- `dispatched` con `unconfirmed`: transporte aceptado, aplicación desconocida; conservar borrador.
- `partial`/`error`: HTTP de error del controlador con detalles seguros en `data`; conservar campos pendientes y aplicaciones ya confirmadas.

Las respuestas CLI se asocian al comando por tag `hh|` y al emisor. El lock por
nodo evita que dos escrituras usen la misma espera simultáneamente. La
recepción no aplica heurísticas de batería/SF/coordenadas a textos escalares:
`SF12` puede ser un nombre. La consola muestra texto, sin inventar estado del
dispositivo a partir de ecos TX o líneas de error.

## Problemas reproducidos y soluciones

| Problema anterior y reproducción | Corrección | Evidencia mantenida |
|---|---|---|
| Autoadd max hops se reflejaba en RAM sin enviarse; flag SDK carece de tercer byte | Paquete oficial opcional, soporte observado y readback; conservar bits ajenos | `test_local_advanced_parameters`, `test_local_advanced_browser` |
| Scope sin `#`, caracteres multibyte o reset compilaban mal/duplicaban estado antiguo | Frame 48 bytes exacto; reset de un byte; limpiar scope vacío y render traducción correcta | Mismos tests, casos `#región`, nombre y reset |
| Getter path hash producía 0 ante error o campo ausente | DEVICE_INFO real y 503 para lectura no confirmada | Getter confirmado/ERROR/ausencia |
| PIN consultado no llegaba a configuración; potencia negativa se veía como 247 | Merge del campo BLE; normalización int8; redacción pública | Lectura PIN/TX firmada |
| Diccionario vacío custom vars preservaba datos antiguos; borrar clave simulaba eliminación | Vacío confirmado limpia caché; borrado devuelve 422; validar todo lote | Lectura directa/refresco, invalid batch/delete |
| Fracciones, booleanos indebidos y aliases incompatibles se aceptaban o truncaban | Prevalidación completa antes de SDK; normalización de coordenadas wire | Integer/alias/boolean/precision cases |
| Tuning aceptaba factores que cambian al reiniciar y mostraba más decimales que el wire | Respetar `loadPrefs` RX 0..20/AF 0..9, aliases coherentes, controles HTML acordes y snapshots de milésimas | Ocho casos de límites/rechazo/recarga; fuente `companion_radio/MyMesh.cpp:941` |
| Remoto daba éxito tras `MSG_SENT`, sin respuesta; lote actualizaba registro prematuramente | Espera CLI correlacionada; `applied/saved/unconfirmed`; stop ante rechazo con parciales | 72 regresiones de backend remoto |
| Respuesta tardía/otro emisor podía confirmar otro comando | Tag y origen asociados a la espera; lock por objetivo | Correlation y navegador sender-scoped |
| Radio remota pendiente de reboot aparecía como RF activa | Separación de preferencias `saved` y registro observado | Backend y navegador radio saved/read |
| Getter escalar se confundía con nombre/batería/TX; owner/status/ACL binarios no propagaban | Parser por comando; mapear payload oficial y rutas binarias correctas | Scalar/readback/registry JSON/binary cases |
| Formularios enviaban campos ajenos/no soportados y anuncios en segundos | Dirty-only, unidades oficiales y controles deshabilitados | 17 casos únicos de navegador remoto |
| Error HTTP o respuesta vacía borraba tablas/borradores; cambios de nodo y lecturas tardías pisaban edición | Validar todas las envolturas y generaciones; retener edición hasta confirmación | Browser HTTP/partial/race tests |
| Contraseñas cambiaban antes del ACK; `.trim()` alteraba contraseña permitida; secretos llegaban a consola/MQTT | Preservar cadena literal y credencial anterior; redacción pública separada de respuesta privada | Password browser y cuatro regresiones de publicación |

Para demostrar la diferencia se ejecutó una **selección de 114 regresiones de
backend local/remoto y privacidad** sobre una copia aislada de `src` en la base
`0e1c6f6`: **104 fallaron y 10 pasaron**. Es un conjunto de casos parametrizados,
no 104 defectos independientes. Se conservaron XML y log en
`tests/artifacts/config-baseline-reproductions.*`. La copia usa las fixtures
actuales de tests, sin hardware ni modificación del checkout de trabajo.
La selección adicional de ocho casos de tuning sobre esa misma base obtuvo
**7 fallidas y 1 aprobada**; la configuración corregida aprobó los ocho casos.

La primera suite transversal produjo 927 aprobadas, seis fallidas y un skip.
TX remoto 22 dBm sin máximo observado era un rechazo incorrecto y se corrigió.
Las otras expectativas/fixtures se actualizaron con evidencia: tags nuevos,
MQTT con tópico real del cliente (MagicMock inventaba uno), `ok/pong` de chat
sin contexto CLI y watchdog que había pedido 20 ms pese al mínimo de seguridad
del constructor. El watchdog sólo se acelera en el fixture, conserva su mínimo
de producción y exige dos fallos de vivacidad. No se relajan invariantes RF.

La hipótesis de colisión del timestamp del SDK se descartó: el Companion de
referencia genera `RTC.getCurrentTimeUnique()`. No se aplicó parche ni espera
extra para un problema que el firmware disponible no demuestra.

## Verificación y evidencia

La suite final terminó con **963 aprobadas, 0 fallidas y 1 omitida**, en 336,15 s.
El skip corresponde a la creación de symlink para aislamiento cartográfico:
Windows no concedió ese permiso. Cobertura de líneas Python: **70,16%**
(10229/14579); no implica cobertura completa de comportamiento.
`mypy --strict src`: 60 archivos sin errores. Ruff: sin errores.
Sintaxis JS de los tres módulos modificados: aprobada.
Resultados finales y versión de herramientas: [verification.json](audits/config-parameters-2026-10-04/verification.json).
Regresiones locales avanzadas + navegador iniciales: **41 aprobadas**. Tras el
ajuste final de tuning, la selección local avanzada + guardado/recarga previo +
navegador obtuvo **81 aprobadas**. Navegador remoto:
**17 casos únicos aprobados**. La suite completa incluye estas pruebas y las
regresiones locales previas, roles/contactos, ACK, API, recepción, colas y cierre.
No sumar estos conteos de selecciones a los de la suite completa.

Comandos, usando `.venv/Scripts/python.exe` en Windows:

```text
python -m pytest tests --cov=src --cov-report=xml:tests/artifacts/config-parameters-release-coverage.xml --junitxml=tests/artifacts/config-parameters-release.xml -q -p no:cacheprovider --basetemp tests/artifacts/config-parameters-release-tmp
python -m mypy --strict src
python -m ruff check src tests scripts
python scripts/validate_project_docs.py
```

Se usa `basetemp` propio porque el directorio temporal compartido de Windows y
la caché de pytest tuvieron errores de permisos. Esos errores de entorno no se
reportan como defectos del firmware. Cobertura Python no mide cobertura JS ni
interoperabilidad física. Chromium usa servidor virtual propio y se cierra con
las fixtures; no se usa `localhost:8080` operativo.

## Pasos de aceptación sobre dispositivos

1. Registrar versión del firmware/SDK, rol, placa, clave del objetivo y valores
   actuales. Abrir Configuración para LOCAL y Administrar para REPEATER; no
   mezclar destinos ni añadirlos a contactos de chat.
2. Leer explícitamente desde el dispositivo y guardar la respuesta. Si falta
   soporte o dato, no sustituirlo por cero ni por un default de HTML.
3. Cambiar **un parámetro soportado** a un valor permitido acordado por el
   operador. Guardar y revisar resultado por campo; ante timeout/error,
   mantener el borrador y comprobar manualmente antes de repetir.
4. Consultar el getter de ese parámetro, comparar el valor normalizado y
   recargar la página. Comprobar que no se altera el resto del grupo empaquetado.
   Para autoadd legacy, no esperar max hops; para scope, repetir con UTF-8 y
   reset. No exportar PIN ni credenciales en capturas o logs.
5. En remoto, repetir nombre, owner vacío, TX, repeat, posición y anuncios con
   sus unidades. Comparar GET contextual y estado tras recarga; repetir para
   cada nodo administrado porque versión, permisos y placa pueden variar.
6. Probar el grupo RF sólo dentro de una ventana de mantenimiento acordada:
   observar `saved/pending_reboot`, comprobar preferencias, reiniciar mediante
   acción explícita y verificar conectividad/RF activo. Un cambio incompatible
   con la estación puede perder acceso remoto; preparar recuperación local.
7. En credenciales, guardar con sesión existente, exigir confirmación y probar
   nuevo login. Para ACL, leer tabla binaria después de la operación; verificar
   permiso sin retirar el último acceso admin de la instalación.
8. Comprobar control inválido, rechazo del firmware, ausencia de respuesta y
   fallo parcial. No debe aparecer éxito global, revelarse secretos ni
   repetirse el lote automáticamente. Cambiar de nodo mientras llega una
   respuesta no debe aplicar esa respuesta al nodo nuevo.
9. Tras reinicio operativo **acordado**, volver a leer parámetros persistentes
   y registrar resultado por versión/nodo. Las pruebas virtuales de esta tarea
   no ejecutan este reinicio sobre la estación real.

Criterio de cierre operativo: para cada parámetro soportado, ACK correspondiente,
getter compatible y recarga coherente; para los no soportados, control
deshabilitado/rechazo explícito sin transmisión. No confundir mediciones
opcionales de telemetría con parámetros configurados o RF activo.
