# Frontend de configuración remota: inventario y correcciones

Fecha: 2026-10-04. Agente especializado frontend, coordinado con los agentes de protocolo y backend. Skills: `contract-openapi-sync`, `html-css-modern-js` y `web-browser-inspection`. Las referencias oficiales y la matriz de unidades/comandos están en [protocol-matrix.md](protocol-matrix.md); el plan y el checklist RF pertenecen al [informe principal](../../CONFIGURATION_PARAMETERS_AUDIT_2026-10-04.md).

## Inventario de parámetros

Todos los formularios remotos consumen `POST /api/repeater/remote/config`, con autorización HTTP del bridge y credenciales de la sesión del nodo. Los valores siguientes son los nombres canónicos enviados por la SPA, sin enviar presets de región o campos ajenos al formulario editado.

| Control DOM | Parámetro | Lectura / significado | Corrección y estado |
|---|---|---|---|
| `radioFreq`, `radioBw`, `radioSf`, `radioCr` | `frequency`, `bandwidth`, `spreading_factor`, `coding_rate` | `get radio` lee preferencias guardadas, no RF activo | Grupo completo únicamente cuando se modifica algún componente. MHz/kHz/SF/CR; campos vacíos si falta observación, sin defaults implícitos. Validación pide lectura manual o cuatro valores explícitos. |
| `radioRegion` | Preset de frecuencia, sin parámetro de firmware | Selector de región local a la UI | Marca la frecuencia como modificada. Nunca envía `region`, que el backend rechazaba. |
| `radioPower` | `tx_power` | `get tx` contextual | Se actualiza desde valores confirmados del remoto, incluidos límites aplicados; no desde el valor solicitado. |
| `radioRepeatMode` | `repeat` | `get repeat` contextual | Guarda sólo si se modifica. El rol REPEATER no demuestra que esté habilitado el reenvío. |
| `radioBeaconInterval` | `advert_interval` | `get advert.interval` | La etiqueta anterior decía segundos y el default era 300. Ahora son minutos, 0 o valores pares 60..240. Sin default inventado. |
| `radioHopLimit` | No hay setter global equivalente | No confundir con límites de otra operación | Deshabilitado con descripción del soporte. |
| `repOwnerName` | `name` | `get name`, `req_owner` | No reenvía todo el formulario. Un alias de presentación no sustituye el nombre del firmware. |
| `repOwnerInfo` | `owner_info` | `get owner.info`, `req_owner` | Conserva la cadena y permite vaciarla con confirmación explícita. |
| `repPosLat`, `repPosLon` | `latitude`, `longitude` | `get lat`, `get lon` contextuales | Cero es válido. No interpreta una respuesta numérica de otro comando como coordenada. |
| `repPosAlt`, `repPosFixed` | No hay setters oficiales correspondientes | Pueden existir datos pasivos, sin capacidad de escritura | Deshabilitados; no se emiten valores ficticios en cada guardado. |
| `secNewAdminPwd`, `secNewGuestPwd` | `new_password`, `guest_password` | Contraseñas sin getter | Vacío conserva la contraseña. La credencial de sesión sólo cambia tras ACK explícito del parámetro correspondiente; sin respuesta conserva el borrador y la credencial anterior. Login, rotación y sesión preservan espacios literales admitidos por firmware, sin trim unilateral. |
| `secAclMode`, `secIdentityKey` | No corresponden al setter ACL por clave y permiso | ACL se consulta mediante `req_acl` | Deshabilitados; ni el modo global ni identity_key constituyen una entrada `setperm`. |

## Inventario de consultas y acciones

| Control / mecanismo | Ruta / acción | Alcance |
|---|---|---|
| Gate `repeaterGatePassword`, `btnRepeaterGateSubmit` | `/remote/login` | Autenticación explícita; requiere `authenticated:true` y HTTP correcto. Una respuesta tardía no desbloquea otro modal. |
| `btnRepeaterLogout` | `/remote/logout` | Cierre de sesión y limpieza de credenciales de la UI. |
| `btnRefreshRepeaterTelem` | `/remote/action`, `refresh_telemetry` | Consulta manual existente; el login y reapertura autenticada conservan su consulta existente, sin añadir polling ni solicitudes. No muestra recepción satisfactoria tras un fallo HTTP. |
| `btnModalActionRadioStats` | `/remote/action`, `get radio` | Preferencias guardadas, separadas del registro de parámetros RF activos. |
| `btnSyncRepeaterClock` | `/remote/action`, `sync_clock` | Acción explícita existente. |
| `btnModalActionAdvert` | `/remote/action`, `advert` | Acción explícita existente; no se arma ningún scheduler. |
| `btnModalActionClearStats` | `/remote/action`, `clear stats` | Acción explícita existente. |
| `btnModalActionReboot` | `/remote/action`, `reboot` | Conserva el diálogo de confirmación y la acción manual. Reiniciar no acredita por sí mismo el RF activo. |
| `btnModalActionPing`, botones ping de vecinos | `/api/repeater/ping_zero` | Conserva los límites y el cooldown existentes. No se modifican intervalos ni reintentos. |
| `btnModalActionNeighbors`, `btnDiscoverNeighbors` | `/remote/neighbours` | Tabla de vecinos; exige HTTP correcto y array realmente recibido. |
| `btnFetchRepOwner` | `/remote/owner` | Conserva borradores y permite observaciones vacías explícitas; no convierte ausencia de respuesta en “OK”. |
| `btnFetchRepRegions` | `/remote/regions` | Consulta en la pestaña Propietario y Posición; no aplica un preset de región al firmware. |
| `btnFetchRepAcl` | `/remote/acl` | Consulta binaria ACL existente; no sustituye `req_acl` por un `get acl` RF inexistente. |
| `repQuickCmdForm`, `repeaterTerminalForm`, `.rep-quick-cmd` | `/remote/action` | Consola y acciones manuales existentes. Historial/eco ocultan comandos de credenciales; los comandos secretos no se almacenan para su repetición. |
| `btnClearRepeaterTerminal`, cambio de subpestañas y cierre del modal | Operaciones de presentación | No se transmiten paquetes por limpiar la consola o presentar datos. |

## Errores reproducidos y soluciones

1. Radio y posición enviaban cada campo de sus formularios, con defaults, `region`, saltos, altitud y posición fija no soportados. Un cambio sencillo podía abortar por otro parámetro. Se sustituyeron por snapshots de campos modificados; el grupo RF requiere sus cuatro componentes completos y explícitos.
2. Los tres formularios aceptaban `status:ok` sin comprobar HTTP ni el estado interno. Radio y posición actualizaban el registro con el payload solicitado, y seguridad reemplazaba credenciales sin ACK remoto. Ahora únicamente `applied` confirma campos; `saved` de radio y `dispatched` tienen mensajes distintos y conservan pendientes.
3. Un resultado parcial borraba todos los borradores. Ahora sólo limpia campos reconocidos como aplicados cuya versión y valor siguen correspondiendo a lo enviado. No pierde ediciones nuevas mientras hay una petición pendiente.
4. `appendTerminalLine()` interpretaba ecos TX, respuestas y errores como telemetría del nodo seleccionado. Otro emisor podía contaminar ese nodo mediante `repeater_response`. La consola quedó limitada a presentación; los cambios requieren datos estructurados y una clave canónica de emisor coincidente. Se retiró el parser heurístico duplicado del frontend.
5. Los getters convertían ausencia en arrays u objetos vacíos y podían mostrar éxito con HTTP 403. Exigen datos recibidos, HTTP correcto y estado interno confirmado, conservando el detalle de error como texto escapado.
6. Respuestas tardías de un modal cerrado/reabierto, otra selección o una lectura anterior a una escritura podían sobrescribir la UI. Se añadieron generaciones de modal/observación, sin timers, RF adicional ni reintentos.
7. Los comandos de contraseña podían aparecer en eco e historial de consola. Se enmascaran en presentación y se excluyen del historial; el cuerpo de transmisión autorizado conserva el comando original.

## Verificación y límites

- `node --check` de `repeater.js` y auditoría léxica i18n: correctas. Ruff del nuevo módulo de pruebas: correcto.
- Primer ensayo de navegador: 13 aprobadas y un error del fixture, que intentaba pulsar Regiones en una pestaña equivocada. Se corrigió al panel real y se reforzó la espera del error HTTP.
- Segundo ensayo: 14 aprobadas. Suplemento tras completar la correlación de emisores y preferencias RF: 2 aprobadas, 14 no seleccionadas. Ensayo conjunto estable: 16 aprobadas en 38.35 segundos. Tras la última corrección de login literal, suplemento de credenciales: 1 aprobada, 16 no seleccionadas. Son 17 casos únicos mantenidos; el principal integra el alcance exacto de la colección global, sin sumar como nuevos los casos repetidos.
- Capturas inspeccionadas en Chromium: tema claro 390×844 y oscuro 1920×1080, ES/EN. Evidencia local: `tests/artifacts/config-parameters-2026-10-04/remote-browser-*.json`, XML y `remote-radio-*.png`.
- Las pruebas usan la fixture mantenida de estación virtual, puertos de loopback asignados por el SO y respuestas RF sintéticas en el límite `window.fetch`. No acreditan interoperabilidad real, identidad de todos los firmware instalados, RF activo tras reiniciar ni WCAG completo.
