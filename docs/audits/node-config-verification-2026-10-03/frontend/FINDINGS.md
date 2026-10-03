# Verificación actual de frontend: configuración local/remota

Fecha: 2026-10-03. HEAD auditado: `9f561932d648470e8c8bd23fc789a66bdb378d0e`. Esta evidencia reemplaza conclusiones de frontend de `81f4260` cuando se evalúa el checkout actual. No se modificó producción ni referencias.

## Método y resultados generales

Skills utilizadas: `contract-openapi-sync`, `web-browser-inspection`, `html-css-modern-js`; leídos AGENTS.md y TESTING.md. Se inspeccionaron SettingsModule, RepeaterModule, index.html, CSS y contratos/controladores, contrastando restricciones y semántica con el firmware oficial local. La comparación del cliente oficial corresponde al dirigente: este ensayo usa exclusivamente la SPA del bridge.

Se revisó el harness histórico y `tests/conftest.py` antes de ejecutar. `reproduce_ui.py` crea una estación virtual propia mediante las fixtures mantenidas, VirtualMeshAdapter, MQTT simulado, datos temporales dentro de esta carpeta y puerto loopback asignado por el SO. La carga de .env se neutraliza antes de importar config; un audit hook rechaza abrir `.env`. Se cancelan las escenas periódicas del adaptador virtual. Los POST se interceptan en Chromium, nunca llegan a backend/radio; GET y WebSocket sí leen el servidor virtual. No se consulta localhost:8080, ningún broker operativo ni radio física. Se omiten CDN externos. Browser/context/servidor/tareas se cierran en finally.

Se enlazan instancias de los módulos reales a formularios DOM reales, clonados para retirar listeners originales. Los cambios de borrador emiten eventos input/change como el usuario. El desbloqueo remoto se invoca expresamente para explorar controles; la sesión visible en capturas es simulada y no prueba autenticación/capacidades del remoto. Algunas escrituras llaman directamente al método o dispatchEvent: ese camino permite inspeccionar payloads, pero evita validación nativa. El ensayo `native_numeric_validity` prueba separadamente checkValidity/stepMismatch reales.

Comando: `.venv/Scripts/python.exe docs/audits/node-config-verification-2026-10-03/frontend/reproduce_ui.py`. Entorno: Windows, Python 3.12.14, Playwright 1.62.0, Chromium 151.0.7922.34. Ejecución final exit 0; 19 observaciones dirigidas, 65 controles inventariados y 26 capturas/mediciones. **Exit 0 significa que la reproducción concluyó, no ausencia de defectos.** No se ejecutaron pytest general, cobertura, mypy ni ruff como aceptación de frontend. Error inicial spawn EPERM del sandbox preservado en `initial-environment-failure.txt`; lanzamiento autorizado escalado completó el ensayo. No reapareció el NameError histórico de AdvertHandler.

Archivos: [script](reproduce_ui.py), [JSON íntegro](reproduction-results.json), [salida](run-output.txt), [inventario completo](CONTROL_INVENTORY.md). El JSON conserva restricciones y opciones de todos los controles, requests ficticios y claves identificadoras de cada observación.

## Correcciones históricas que sí funcionan en este checkout

| Defecto anterior | Resultado actual reproducido |
|---|---|
| Borrador local perdido por batería/self_info | Nombre `UNSAVED_DRAFT` y frecuencia916.5 sobreviven la actualización battery77 con input/change. Remoto dirty916.5 sobrevive populate de frecuencia915. |
| Altitud local altitude_m ignorada | altitude_m123 se muestra123. |
| AutoAdd cero convertido en default | config0/max_hops0 da chatfalse/hops0. No confirma preservación del borrador AutoAdd. |
| TX remoto cero | tx_power0, min0/max14 muestra0. La actualización parcial separada todavía pierde límites/valor. |
| Doble submit remoto | Botón disabledtrue tras primero; dos submits durante400ms producen un solo POST. |
| Error 422 sin detalle | Local y radio remoto muestran `AUDIT_EXACT_VALIDATION_DETAIL`. Otros endpoints aún tienen adaptadores distintos. |
| Respuesta aplicada local ignorada | POST ficticio data.config.frequency433.125 actualiza display/cache433.125. |
| Decimales truncados por parseInt | Payload contiene rx_delay0.5/airtime_factor1.5. Persiste restricción HTML step. |
| Seguridad remota sin cambios enviaba ACL public | Cero POST al submit sin editar; ACL sólo se añade dirty. |
| Radio A heredada por B | A867.5/SF9→B desconocido deja frecuencia vacía y SF11 predeterminado. Ya no hereda A, pero sigue inventando otros defaults. |
| Pestañas remotas recortadas | Texto wrap y overflowvisible; scrollWidth==clientWidth en móvil/escritorio. Inspección visual confirma texto completo. |
| Modal CLIENT accesible por método | Con CLIENT conocido, targetnull/modalhidden y aviso; comprobado sin desbloqueo. No sustituye controles backend. |

## Defectos actuales reproducidos y solución propuesta

| ID/prioridad y fuente | Pasos / evidencia actual | Solución y aceptación |
|---|---|---|
| **VUI01/P1: despachado se anuncia aplicado**. repeater.js:412–444; repeater_controller.py:98–127; repeater_executor.py:318,332 | Guardar radio con respuesta externa statusok y data.statusdispatched/pending_reboottrue; `remote_dispatched_presented_applied` da toast “applied and synchronized”, frecuencia916.5 en registro/resumen y dirtyfalse. Ese envelope reproduce el contrato actual, aunque respuesta concreta está simulada. | Consumir estado interno y resultados por campo; conservar observado, mostrar enviado/pendiente reboot y readback bajo demanda. Nunca mutar estado confirmado por mero dispatch; partial conserva errores y borrador. |
| **VUI02/P1: dirty no filtra lote; PIN desconocido se convierte en0**. settings.js:1788–1842; repeater.js:390–400,491–501 | Editar sólo frecuencia916.5 con PIN vacío; `local_one_field_full_payload` envía20 claves, pin0, todos flags, modos e intervalos. Dirty protege render, pero save serializa la sección completa. Efecto real de borrar PIN no se ejecutó. | Enviar sólo dirty admitidos; vacío PIN significa conservar y borrar debe ser una acción explícita. Para setters compuestos completar tuple desde baseline conocido, sin elegir defaults. Separar políticas host/schedulers de radio. |
| **VUI03/P1: lectura Owner pisa borrador y contamina otro destino**. repeater.js:1907–1930 | Consultar con `repOwnerName=UNSAVED_OWNER` dirty; respuesta OwnerA sustituye value porOBSERVED_A manteniendo dirtytrue. Iniciar consultaA con400ms y abrirB; al responderA, B recibe OBSERVED_A/INFO_A. `remote_owner_read_destroys_dirty`, `remote_owner_read_cross_target`. | Asociar petición/public key/version; actualizar cacheA y sólo renderizar si seleccionadoA; usar _setFieldIfNotDirty. Mismo control para regiones/ACL/neighbours y acciones tardías. |
| **VUI04/P1: SF admitido desaparece y potencia válida cambia**. index.html:834,843–851; settings.js:1444–1466,1790–1791; firmware MyMesh.cpp:1396–1397 | Poblar SF5/TX0 local: selectSFvaluevacío y rangeTX2 (min2/max22), cache conserva SF5/TX0. `sf5_roundtrip_fallback` guarda SF11/TX2. Firmware admite SF5–12 en parser; no acredita SF5/TX0 en toda placa. El select remoto también omiteSF5/6. | Opciones y límites según capacidad/build del nodo. Mostrar valores soportados por dispositivo sin clamping silencioso; desconocidos bloquear escritura. No fallback11 si select no representa baseline. |
| **VUI05/P1: edición durante POST se pierde; offline se reactiva**. settings.js:1852–1871,1393–1403; repeater.js:413–416,514–516 | Enviar frecuencia917 con demora400ms; editar918 antes de responder y recibir radio_connectedfalse. `local_edit_during_save_and_disconnect`: formulario433.125, dirtyfalse y SaveRadiodisabledfalse aunque cache.radio_connectedfalse. | Snapshot de versión de borrador enviada; limpiar sólo campos cuyo borrador sigue idéntico. En finally recomputar disabled con busy/conexión/capacidad. Deshabilitar edición durante envío es opción de UX si no se pierde el borrador previo. |
| **VUI06/P2: fracciones se serializan pero navegador las considera inválidas**. index.html:820,954,958 | `native_numeric_validity`: RX0.5/AF1.5 tienen checkValidityfalse/stepMismatchtrue porque step implícito1. Frecuencia915.123 también inválida por step0.025. | RX/AF step acorde a unidad/precisión oficial y label adimensional; frecuencia con resolución del protocolo/capacidad o stepany más validación canónica. No inventar umbral o frecuencia. Probar submit nativo, no sólo método. |
| **VUI07/P2: AutoAdd no participa en dirty**. settings.js:185–199,1659–1669,2146–2159 | Editar hops7/chattrue con eventos; actualización pasiva battery79 usa cache.autoadd_config0 y vuelve a hops0/chatfalse. `autoadd_draft_overwrite`. | Dirty/observado separado para todo formulario, incluidos endpoints dedicados. Readback no destruye cambio pendiente; deshabilitar guardar sin diferencias. |
| **VUI08/P2: telemetría Base/Ubicación invierte semántica1/2**. index.html:962–975; NodePrefs.h:6–7 | OpcionesDOM: Base/Loc1“Todos los Nodos”,2“Solo Contactos”. Firmware define1ALLOW_FLAGS/contact.flags y2ALLOW_ALL. Ambiental1Contactos/2Todos es coherente. Evidencia estática y options del inventario; no se transmitió cambio real. | Traducir1 según permiso por flags,2todos,0deshabilitado en las tres políticas. Mantener tipos canónicos y distinguir permiso de respuesta de broadcast periódico. Prueba de texto opción y payload para cada valor. |
| **VUI09/P2: snapshot remoto parcial usa defaults y altera TX observado**. repeater.js:1404–1440,1466–1480 | `remote_role_capabilities_and_zero_power`: populate conTX0/límites0..14 da0; populate sólo frecuencia/batería devuelveTX20/límites2..22. B desconocido sigue SF11/TX20/hops3/baliza300 y resumen915. | Fusionar snapshots por nodo con fuente/presencia; desconocido en vacío y guardar bloqueado. Muchos callbacks actuales fusionan Map antes de populate, mitigando esa ruta: la reproducción directa prueba fragilidad del renderer, no que todo eventoWS active el defecto. |

## Capacidad, conexión, permisos y dominio

Gating local mejoró: SaveRadio se deshabilita con radio_connectedfalse. Pero controles Repeat/PIN/PathHash y acciones Advert/Reboot permanecen habilitados; finally de save lo revierte (VUI05). No existe una matriz capabilities pública completa verificada en este flujo. La inyección capabilitiesfalse sólo es una simulación prospectiva para evidenciar falta de gating; no se presenta como incumplimiento de un campo contractual existente. Una sesión RF autenticada no acredita permiso admin: deben distinguirse guest/read-only/admin por respuesta real.

El modal público ahora rechaza CLIENT conocido. La navegación Nodos todavía reserva Administrar a REPEATER/ROUTER; ROOM/SENSOR pueden necesitar capacidades separadas con evidencia oficial. LOCAL no debe ser destino administrativo remoto; roles desconocidos/alias requieren validación canónica backend. La administración nunca debe introducir REPEATER/LOCAL en chat/contactos. No se encontró autorización para transmitir o verificar malla real en esta auditoría.

La lectura completa de un remoto no proviene de un GET de snapshot hardware equivalente al local. Hay caché/adverts/CLI/consultas binarias y permisos diferentes. `openRepeaterAdminModal` llama refresh_telemetry si hay sesión/contraseña almacenada (repeater.js:1287–1291), y login lo hace tras éxito(:1081); requiere contabilizar coste RF/cooldown. No añadir polling/readback masivo automático como arreglo UI.

PIN BLE local, passwords RF, API key HTTP y ACL son dominios separados. Contraseñas/identity_key son sólo escritura; “leer cada parámetro” debe exceptuar secretos y mostrar estado redactado. `radioRegion` es preset/frecuencia; no prueba cambio de regulación/hardware. Hop/owner/alt/fixed/intervalos/ACL genérica necesitan resultado backend/capability: la UI visible no acredita setter físico. Telemetría periódica local promete broadcast en el texto HTML, mientras los modos Companion son permisos de respuesta; separar esas capacidades en diseño y documentación.

## Vista, idiomas y accesibilidad

26 capturas: 24 móvil390×844 (2temas×2idiomas×6paneles) más2desktop1920×1080 español/claro. En las26 root.scrollWidth==clientWidth, sin overflow horizontal de página. Modal con overflowauto; contenido bajo fold es alcanzable por scroll. Pestañas remotas legibles con wrap en ambos tamaños; defecto histórico resuelto. Se inspeccionaron imágenes light-es-rep-radio-390 y light-es-local-radio-1920; apariencia principal legible. El dirigente inspeccionó otras dos capturas. No se acredita contraste WCAG completo ni teclado/lector de pantalla por geometría.

372 clavesDOM únicas por idioma ES/EN en estas vistas, missing[] ambos. No cubre textos dinámicos; quedan literales Duty Cycle y prefijos, timestamps usan locale navegador. Subtabs siguen sin contrato completo tablist/tab/tabpanel/aria-selected/teclado; incorporar navegación de flechas y foco y mensajes por campo aria-describedby/aria-live. No sustituir todo el tema para corregir lógica de edición.

## Pasos de aceptación para finalizar el trabajo

1. Catálogo canónico de campos por LOCAL/REPEATER/ROOM/SENSOR, permiso, secreto, unidad, rango por capability, opcode/CLI, efecto y necesidad de reboot; conciliar con matriz de protocolo/backend.
2. DTO de snapshot con public key/fuente/fecha/disponibilidad; observado separado de draft, revision por campo y dirty en todos los formularios.
3. Serializar únicamente cambios; completar setters compuestos desde baseline vigente, omitir secretos intactos/desconocidos y rechazar campos no soportados antes del primer efecto.
4. Adaptador de resultados/error compartido para todos endpoints; enviado/aceptado/aplicado/verificado/pending reboot distintos, partial conservado. Evitar éxito optimista remoto.
5. Peticiones vinculadas al destino y revisión de borrador; respuestaOwnerA nunca alteraB. Busy/conexión/capacidad/permiso derivados en un único punto y restaurados coherentemente.
6. Corregir opcionesSF/límitesTX/precisión/etiquetas y semántica telemetría contra fuentes oficiales; desconocido no usa915/20/SF11.
7. Separar host/API/maps/sonido de configuración del dispositivo, y permisos de telemetría de timers/broadcast. Cambios RF bajo demanda; cualquier nuevo intervalo/límite requiere decisión del usuario.
8. Convertir reproducciones a regresiones de comportamiento corregido: normal/partial/dispatched/error/timeout, edición durante envío, cero/fracciones, A→B, desconexión, draftAutoAdd, modo1/2, readback y secretos.
9. Verificar navegador con submit nativo, ES/EN, claro/oscuro, desktop/móvil, teclado/foco/errores, y backend/protocolo con virtual/mocks. Registrar resultados separados; validar RF físico sólo con estación y alcance autorizados.

La matriz [CONTROL_INVENTORY.md](CONTROL_INVENTORY.md) identifica cada control actual y su serialización. Esta auditoría confirma correcciones y defectos del host bajo entradas simuladas. No certifica lectura/escritura sin error de cada dispositivo, interoperabilidad física ni aplicación efectiva del firmware; esos requisitos siguen pendientes donde la evidencia indica fallos o capacidades desconocidas.
