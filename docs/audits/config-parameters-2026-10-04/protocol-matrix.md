# Matriz de protocolo de configuración local y remota

Fecha: 2026-10-04. Inspección de código, sin radio física, servicios operativos ni actualización de referencias. Esta matriz acredita contratos del checkout; no certifica cada placa o versión instalada. El informe principal debe separar los resultados de simulación de una aceptación sobre hardware.

## Autoridad y procedencia

- Firmware oficial: `reference/meshcore`, Git propio, `d92964352441e53b93e8667b802e04f6e072b39e`, origen `https://github.com/meshcore-dev/MeshCore`.
- SDK oficial: `reference/meshcore_py`, Git propio, `c487efbe187f4b000020afdfc0349c4cdf503c5a`, origen `https://github.com/meshcore-dev/meshcore_py`. Los métodos de scope, autoadd y el parser de potencia también se cotejaron con `.venv/Lib/site-packages/meshcore`.
- `reference/remote-terminal` es una copia de tercero sin `.git` propio. Origen declarado `https://github.com/jkingsman/Remote-Terminal-for-MeshCore.git`; revisión no acreditada. Se usa para comparar manejo de UI/errores y consultas, nunca para contradecir firmware oficial.
- Skill utilizada: `.agents/skills/meshcore-source-inspector/SKILL.md`. Lectura dirigida con `rg` y fragmentos de serializadores/parsers; no se infiere layout wire sólo de structs C++.

## Estados que no deben confundirse

1. SDK `send_cmd()` devuelve `MSG_SENT`: el Companion aceptó/despachó el envío. No confirma que el remoto haya aceptado el parámetro.
2. Respuesta CLI remota de ese comando: acredita aceptación o rechazo del firmware. Los errores incluyen `Error`, `ERROR:`, `Err -`, `(ERR: ...)`, `unknown config: ...`, `Unknown command` y `??: ...`.
3. Getter remoto correlacionado: acredita el valor reportado por el firmware; puede incluir truncado/redondeo. No reemplazar esta lectura por el payload solicitado.
4. `set radio` remoto responde `OK - reboot to apply`: guarda preferencias, no cambia el RF activo. `get radio` lee esas preferencias, por tanto tampoco certifica RF activo antes del reinicio.
5. Sin respuesta, timeout o respuesta de otro origen: estado desconocido/no confirmado. Conservar el borrador y los cambios parciales confirmados, sin éxito global.

Evidencia: SDK `commands/messaging.py:63`; firmware `simple_repeater/MyMesh.cpp:666` y `:1196`; `simple_room_server/MyMesh.cpp:436` y `:899`; `CommonCLI.cpp:449` y `:805`.

## Campos del formulario remoto

La SPA se encuentra en `src/web/static/js/modules/repeater.js` y `src/web/static/index.html`. Los nombres de campo de esta tabla son los del formulario o sus aliases API.

| Campo | Setter oficial | Getter / respuesta | Unidad, rango y observaciones |
|---|---|---|---|
| `freq` / `frequency`, `bw` / `bandwidth`, `sf` / `spreading_factor`, `cr` / `coding_rate` | `set radio f,bw,sf,cr` | `get radio` → `> f,bw,sf,cr`; setter `OK - reboot to apply` | MHz 150..2500; kHz 7..500; SF5..12; CR5..8 (UI4/5..4/8). Una escritura agrupada. Preferencias persistidas; reinicio requerido. Capacidades reales dependen de placa. |
| `region` | No existe parámetro global de región RF | No existe getter global equivalente | Preset de UI: selecciona valores RF. No enviar `region` dentro de configuración. El mapa CommonCLI `region` es ámbito de flood y tiene otra semántica. |
| `tx_power` | `set tx n` | `get tx` → `> n`; setter `OK` | dBm int8 en preferencias; callback aplica inmediatamente. Respetar límites de placa ya existentes y reportar clamp confirmado, no valor pedido. |
| `repeat` / `repeat_enabled` | `set repeat on` / `off` | `get repeat` → `> on` / `off`; setter `OK - repeat is now ...` | Booleano de forwarding. Persiste y aplica sin reinicio global. |
| `hop_limit` | No existe `set hop_limit` global | No existe getter global equivalente | `flood.max` controla límites de flood, no sustituye silenciosamente este campo. Deshabilitar el campo no soportado. |
| `advert_interval` / `beacon_interval` | `set advert.interval n` | `get advert.interval` → `> n`; setter `OK` | **Minutos**, no segundos. 0 desactiva; 60..240 en esta revisión (`MIN_LOCAL_ADVERT_INTERVAL=60`). Guarda `uint8_t(mins/2)` y getter multiplica por 2: 61 termina en 60. Mostrar el valor normalizado confirmado o exigir pares; no anunciar 61 aplicado. Rearma el timer del dispositivo bajo acción explícita del usuario. |
| `flood_advert_interval` | `set flood.advert.interval n` | `get flood.advert.interval` → `> n`; setter `OK` | **Horas**. 0 desactiva;3..168. No convertir a segundos. Persiste y rearma timer del dispositivo bajo petición del usuario. |
| `owner_name` / `name` | `set name texto` | `get name` → `> texto`; setter `OK` o `Error, bad chars` | Buffer de 32 bytes incluido NUL: máximo 31 bytes UTF-8. CommonCLI prohíbe `[]\\:,?*`. No asumir que cualquier string enviado se aceptó. |
| `owner_info` | `set owner.info texto` | `get owner.info` → `> texto`; setter `OK` | Buffer de 120 bytes incluido NUL: máximo 119 bytes. CLI convierte `|` en salto de línea y el getter vuelve a `|`. Normalizar y respetar capacidad; no guardar más que firmware sin avisar/truncar explícitamente. |
| `lat` / `latitude` | `set lat n` | `get lat` → `> n`; setter `OK` | Grados. Bridge debe validar finito y -90..90; firmware usa `atof` sin validación geográfica. Persistencia inmediata. |
| `lon` / `longitude` | `set lon n` | `get lon` → `> n`; setter `OK` | Grados. Bridge debe validar finito y -180..180. Persistencia inmediata. Getter formatea float, comparar tolerancia/representación del protocolo. |
| `alt` / `altitude` | No existe setter de altitud de posición general | No getter de posición equivalente | Deshabilitar en este formulario. Telemetría de altitud recibida de sensores es una medición, no confirmación de escritura. |
| `fixed` / `fixed_position` | No existe setter general posición fija/GPS | No getter general equivalente | Deshabilitar. `sensor set gps` depende del hardware y no representa un modo universal de ubicación del remoto. |
| `new_password` / `admin_password` | `password nuevo` (**sin** `set`) | Respuesta `password now: nuevo` | Buffer de 16 bytes incluido NUL: máximo 15 bytes. Persiste inmediatamente. Confirmación explícita especial; redactar respuesta, registros y MQTT. Actualizar credenciales de UI sólo cuando se confirme, no al despachar. No hay getter de contraseña de admin. |
| `guest_password` | `set guest.password nuevo` | `get guest.password`; setter `OK` | Buffer de 16 bytes incluido NUL. Getter sólo admin vía CLI. No exponer ni registrar secretos al consultar owner. |
| `acl_mode` | No existe modo global open/password/whitelist | No getter equivalente | Deshabilitar esta abstracción. `allow.read.only` es otro booleano y no equivale a esos modos. |
| `identity_key` | API UI actual no compila comando | No getter equivalente | Deshabilitar el campo actual. CommonCLI `set prv.key <privada>` sí existe, pero es cambio de identidad con reinicio y nueva pubkey; no sustituirlo silenciosamente por ACL. Exportar `get prv.key` sólo serial. |
| `public_key` + `permission` | `setperm <pubkey> <u8>` | `OK` o `Err - ...`; lectura RF `req_acl_sync()` | ACL por clave; rol en los dos bits bajos: 0 guest/remove, 1 read-only, 2 read-write, 3 admin. Bits restantes son flags. Alta/modificación exige 32 bytes/64 hex completos; borrado admite prefijo existente. Persistencia diferida de ACL. No reenviar identity_key como public_key. |

Evidencia principal: `reference/meshcore/src/helpers/CommonCLI.cpp:160`, `:255`, `:487`, `:596`, `:668`, `:713`, `:805`; tamaños en `CommonCLI.h:27` y `:65`; `ClientACL.cpp:121`.

## Lecturas remotas auxiliares y alcance por rol

| Vista / dato | Operación correcta y límites |
|---|---|
| ACL | `req_acl_sync` → petición binaria 0x05, respuesta `ACL_RESPONSE` correlacionada por tag. `get acl` es **serial-only** en Repeater/Room/Sensor. `get allow.read.only` no devuelve la lista ACL. |
| Estado, batería, ruido, uptime, métricas | `req_status_sync` → petición binaria 0x01 / `STATUS_RESPONSE` con tag. `stats-core`, `stats-radio`, `stats-packets` son serial-only en CommonCLI actual; el despacho de esas cadenas no es lectura RF válida. `get uptime` no está implementado en esta revisión. |
| Telemetría LPP | `req_telemetry_sync`, petición 0x03 y evento `TELEMETRY_RESPONSE` con tag. Mediciones opcionales por hardware/permisos. Ausencia no significa cero ni dato actualizado. |
| Vecinos | `req_neighbours_sync` binario 0x06, paginación count/offset/order/prefix. Respuesta correlacionada. `neighbors` CLI es textual; no confundir número de vecinos con hops. |
| Owner | SDK `req_owner_sync` anónimo devuelve nombre/owner (direct-only en firmware). Petición autenticada owner 0x07 incluye versión/nombre/owner en Repeater. Puede haber diferencias de capacidad con Room/Sensor. Para admin también existen getters CLI. |
| Reloj | `clock` lectura CLI. `clock sync` usa timestamp del comando y sólo avanza reloj; `time epoch` rechaza retroceder con `(ERR: clock cannot go backwards)`. No tratar cualquier respuesta como sincronización aplicada. |
| Regiones | SDK `req_regions_sync` anónimo es direct-only; CommonCLI `region` tiene variantes y guardado. No es preset RF del formulario. |

Repeater y Room implementan CommonCLI para CLI_DATA de un cliente autenticado con rol ADMIN; Sensor también implementa CommonCLI y exige `from->isAdmin()`. El Sensor usa tabla ACL propia: no suponer que todos los binarios o la sesión de login del Repeater se comportan igual. Companion/CLIENT remoto no ofrece el servidor de administración de Repeater: conservar la restricción de UI y backend. El nodo LOCAL se maneja por comandos Companion, nunca como destino RF de sí mismo.

Evidencia: `commands/binary.py:110`,`:163`,`:293`; `simple_repeater/MyMesh.cpp:262`,`:372`,`:584`,`:1262`; `simple_room_server/MyMesh.cpp:436`; `simple_sensor/SensorMesh.cpp:382`,`:520`.

## Todos los grupos de configuración local Companion

| Campo / grupo | Contrato SDK / wire / lectura real |
|---|---|
| Nombre | `set_name` opcode 0x08, ACK OK/ERROR; `send_appstart` SELF_INFO.name. Buffer de 32 bytes, persiste inmediatamente. |
| Latitud/longitud | `set_coords` opcode 0x0E, int32 LE por coordenada × 1e6 (8 bytes); campo reservado del SDK no es altitud editable; SELF_INFO.adv_lat/adv_lon. |
| Frecuencia/BW/SF/CR/repeat | `set_radio` opcode 0x0B, frecuencia uint32 LE MHz × 1000, BW uint32 LE kHz × 1000, SF/CR u8, repeat opcional. Companion guarda y llama `radio_driver.setParams()` inmediatamente. SELF_INFO.radio_* y DEVICE_INFO.repeat (firmware >= 9). Repeat sólo es válido en rangos Companion autorizados: consultar `get_allowed_repeat_freq`. |
| TX | `set_tx_power` opcode 0x0C, primer byte int8; firmware -9..MAX_LORA_TX_POWER. El parser SELF_INFO del SDK usa unsigned read[0]: negativos aparecen 247..255. Normalizar int8 en el borde del bridge; no modificar reference. |
| RX delay / airtime_factor | `set_tuning` opcode 0x15, dos uint32 LE en milésimas del factor, no duración en ms. `get_tuning` opcode 0x2B → TUNING_PARAMS (23), mismos uint32 LE. Firmware al cargar constriñe RX a 0..20 y AF a 0..9. |
| Telemetry mode base/location/environment | `set_other_params_from_infos` opcode 0x26: tres campos de 2 bits empaquetados. Modos 0 deny, 1 allow flags, 2 allow all. Lectura de bits en SELF_INFO. Son permisos de solicitudes recibidas, **no un timer de telemetría periódica**. |
| manual_add_contacts / adv_loc_policy / multi_acks | Mismo paquete 0x26. Baseline completo para preservar campos no editados; ACK OK/ERROR y SELF_INFO. Location policy 0 none / 1 share. Persisten inmediatamente. |
| BLE PIN | `set_devicepin` opcode 0x25, uint32 LE. Firmware acepta 0 ó 100000..999999. DEVICE_INFO.ble_pin (firmware >= 3); indicador has_pin en API redactada. No confundir contraseña remota de admin con PIN BLE local. |
| path_hash_mode | `set_path_hash_mode` opcode 0x3D, reservado 0 + modo 0..2; `send_device_query` DEVICE_INFO.path_hash_mode (firmware >= 10). El getter SDK devuelve 0 incluso ante error/ausencia: usar respuesta query con campo real para acreditar 0. |
| autoadd flags | SDK `set_autoadd_config(flag)` opcode 0x3A + u8; getter 0x3B AUTOADD_CONFIG.config. Preservar bitmask observado; no derivarlo de manual_add_contacts. |
| autoadd max hops | Firmware actual admite byte opcional en SET 0x3A y GET 0x3B (v1.14.0+). El setter SDK instalado sólo soporta flag. Semántica: 0 sin límite, 1 directo (0 hops), N <= 64 hasta N-1 hops. No enviar siempre 3 por default de UI ni presentar cambios en RAM como escritos. |
| default_flood_scope | Setter 0x3F, nombre UTF-8 de 1..30 bytes + padding NUL hasta 31 bytes + clave de 16 bytes en offset 32. SHA256 del nombre canónico con `#`, truncado a 16 bytes. Getter 0x40 DEFAULT_FLOOD_SCOPE. Reset correcto: **sólo opcode 0x3F**; nombre vacío de 48 bytes da ERROR. |
| Custom vars | `set_custom_var` 0x29 key UTF-8 + `:` + value UTF-8; getter 0x28 CUSTOM_VARS mapa. Settings de sensores soportados (p.ej. GPS); clave desconocida produce ERROR. No existe operación general de borrado. El parser SDK usa `,` entre pares y `:` entre clave/valor; delimitadores internos y NUL no son valores opacos seguros. GET {} acredita mapa vacío y debe limpiar la caché previa. |
| Owner info / altitud / fixed_position / hop_limit / telemetry_interval / beacon_interval | Sin setter/getter Companion general correspondiente. La UI debe indicar no soportado. `NodePrefs.h` tiene intervalos advert comentados y permisos telem distintos; no atribuir los intervalos al dispositivo. |
| Predelay / airtime persist / host features | Configuración del bridge: documentar persistencia y efecto del host separados de ACK Companion. No asegurar que se escribió a firmware. |

Evidencia: `commands/device.py:30`,`:70`,`:81`,`:117`,`:180`,`:305`,`:388`; `commands/contact.py:186`; `commands/messaging.py:378`; `reader.py:166`,`:440`,`:539`,`:1042`; `companion_radio/MyMesh.cpp:1379`,`:1425`,`:1443`,`:1790`,`:1818`,`:1940`,`:1974`; `NodePrefs.h:5`,`:40`,`:127`.

## Problemas replicables detectados y medidas de corrección

1. **Correlación y antireplay**: Repeater/Room consideran un segundo comando con igual timestamp como retry y no lo ejecutan; Sensor exige timestamp estrictamente mayor. Sin embargo, Companion actual **sobrescribe el timestamp CLI del SDK mediante `getCurrentTimeUnique()`** (`MyMesh.cpp:1102`), por lo que no se acredita un fallo del stack actual a partir de `int(time.time())` del SDK. Modelar el timestamp wire real y correlacionar cada comando; no introducir un arreglo de timestamps basado sólo en la inspección SDK.
2. **Éxito UI de despacho**: el formulario trataba `data.status=ok` como aplicado y rellenaba NodeRegistry con payload. El executor devolvía `dispatched` sin esperar OK remoto. Mostrar despachado/no confirmado y conservar borrador; sólo retirar campos confirmados.
3. **Formulario RF inválido aun sin tocar**: enviaba `region`, `hop_limit` y beacon 300 seg. Backend rechazaba region/hop y 300 no está en 60..240 min. Enviar campos editados soportados, presets sólo UI, unidades correctas y no inferir baseline de valores HTML por defecto.
4. **Owner inválido**: formulario mandaba alt/fixed aunque no soportados. Deshabilitar y omitir; no bloquear actualización de nombre por campos noeditados.
5. **ACL ficticia**: selector modo global/identitykey no representa `setperm`; lecturaallow.read.only no eslistaACL. Deshabilitar controlesglobales y usar binarioACL para listas.
6. **Truncado de textos y secretos**: los buffers CommonCLI se miden en bytes; la longitud Python en caracteres no garantiza capacidad UTF-8. Validar nombre/password/owner en bytes y tipos; redactar la respuesta password now.
7. **Scope SDK**: reset None provoca TypeError por len(scope); reset '*' da 47 bytes y sólo funciona porque el firmware considera ese payload corto como reset. Unicode desfasa el offset de clave. Corregir serialización según el contrato anterior y comprobar bytes exactos sin RF.
8. **Lecturas locales falsas**: el getter SDK de path hash retorna 0 por error; CUSTOM_VARS {} debe limpiar caché antigua; TX negativo se recibe sin signo. Corregir el borde del bridge y distinguir campo desconocido de 0.

## Comparación con Remote Terminal

`app/routers/repeaters.py` utiliza req_acl_sync binario para ACL; consultas CLI separadas get radio/get tx/get repeat/get flood.max; intervalos advert en minutos/horas; owner binario y guest password sólo admin. Filtra `??:` y errores para mostrar unsupported en dutycycle de versiones antiguas. `app/services/radio_commands.py` verifica EventType.ERROR en modos telemetry y luego consulta estado de radio. Los timers de tracking de telemetría y advert del host son funciones del cliente, no parámetros de firmware Companion. Copiar un control sin scheduler persistente en el host no implementa esa capacidad.

## Aceptación real pendiente

Usar un nodo de pruebas por tipo/firmware/placa y anotar capacidades y baseline. Para cada setter soportado editar un campo, recibir respuesta correlacionada, consultar getter y recargar UI; registrar valor normalizado y persistencia tras reinicio controlado. Para RF remoto separar preferencias guardadas de RF activo, reiniciar bajo acción explícita y reconectar con parámetros nuevos. Para secretos verificar login posterior sin registrar el secreto. Probar ERROR, timeout, respuesta de otro origen, baseline ausente, parcial y edición mientras se guarda. No ejecutar este plan sobre una estación operativa ni inferir éxito de hardware a partir de mocks.
