# Configuración LOCAL y administración REMOTA: contraste de protocolo

Fecha: 2026-10-03. Evidencia de código local, sin cambios de producción ni ejecución de firmware. Base bridge indicada por el principal: `81f4260`. Skills: `meshcore-source-inspector` y `project-reference-audit`. El helper de extracción parcial no identificó símbolos `TELEM_MODE`; se cotejaron constantes y serializadores directamente.

## Procedencia

Los tres directorios oficiales tienen `.git` propio y estado limpio; no se atribuyó a copias sin marcador el HEAD del bridge.

| Fuente | Origen Git | SHA |
|---|---|---|
| `reference/meshcore` | https://github.com/meshcore-dev/MeshCore | `d92964352441e53b93e8667b802e04f6e072b39e` |
| `reference/meshcore_py` | https://github.com/meshcore-dev/meshcore_py | `c487efbe187f4b000020afdfc0349c4cdf503c5a` |
| `reference/meshcore_cli` | https://github.com/meshcore-dev/meshcore-cli | `0856c723cdea3438811c62c190bbec3059e2dc48` |

SDK referencia e instalado: 2.3.8. Firmware Companion de esta copia: `FIRMWARE_VER_CODE=13`, versión por defecto `v1.17.1` (`reference/meshcore/examples/companion_radio/MyMesh.h:8,15`). La versión de una radio concreta no fue consultada. Un número de protocolo no es la versión semántica del firmware.

No hay checkout del frontend oficial de `app.meshcore.nz` ni de `config.meshcore.io` dentro de `reference/`. Firmware README enlaza ambos en líneas 67 y 77. `remote-terminal`, openHop, meshmonitor y otros clientes/bridges de la referencia son terceros; no acreditan controles oficiales de MeshCore. `remote-terminal` no tiene `.git` propio; su README declara RemoteTerm como interfaz propia. `meshmonitor` tiene origen `Yeraze/meshmonitor`, no `meshcore-dev`.

## Matriz LOCAL: Companion conectado

Todas las operaciones de esta tabla usan el enlace local Companion; sólo «Emitir advert» produce explícitamente RF. Cambiar parámetros no equivale a enviar un comando al repetidor remoto.

| Control/dato | Lectura / escritura | Capacidad y límites de esta revisión | Evidencia |
|---|---|---|---|
| Nombre | APP_START 1 / SET_ADVERT_NAME 8 | `node_name[32]`; firmware limita a 31 bytes y no valida que el corte UTF-8 sea completo. No fuerza advert al guardar. | firmware `MyMesh.cpp:1052-1083,1212-1218`; SDK `commands/device.py:30-34` |
| Latitud/longitud | APP_START 1 / SET_ADVERT_LATLON 14 | i32 LE microgrados; lat [-90,90], lon [-180,180]; cero es válido. El tercer i32 es altitud reservada para futuro y no se aplica en esa rama. | firmware `MyMesh.cpp:1219-1233`; SDK `device.py:36-44` |
| Ubicación fija/altitud | Sin campo Companion equivalente acreditado aquí | No presentar `fixed`/altitud como un ajuste aplicado a hardware por opcode 14. GPS sensor/custom vars tiene capacidades separadas dependientes de build. | `MyMesh.cpp:1223-1229`; `NodePrefs.h:14-43` |
| Frecuencia/BW/SF/CR | APP_START 1 / SET_RADIO_PARAMS 11 | MHz ×1000 / kHz ×1000 -> u32 LE; SF/CR u8. Rango firmware: 150..2500 MHz, 7..500 kHz, SF5..12, CR5..8. Se aplica inmediatamente con `radio_driver.setParams`; no requiere reboot en esa rama. Los rangos de parser no acreditan soporte de cualquier placa, banda legal o cualquier BW arbitrario. | SDK `device.py:70-79`; firmware `MyMesh.cpp:1379-1414` |
| Repeat Companion | DEVICE_QUERY22 / byte opcional CMD11 | Disponible a partir de nivel protocolo9. Sólo permitido en rangos devueltos por CMD60; defecto build:433.000,869.495,918.000 MHz; override `ALLOWED_REPEAT_FREQ_RANGE`. No confundir con repeat remoto. | `reader.py:431-434`; `MyMesh.cpp:1000-1014,1391-1402,1987-1994` |
| TX power | APP_START1 / CMD12 | Firmware consume i8 de primer byte y acepta -9..`MAX_LORA_TX_POWER`; el máximo se anuncia en SELF_INFO. Depende de board/build. SDK2.3.8 serializa u32 sin signed y falla para negativos; ver reproducción. | `MyMesh.cpp:1054-1055,1415-1423`; SDK `device.py:64-68` |
| Tuning RX/AF | GET_TUNING43 / SET_TUNING21 | Ambos u32 LE representando valor ×1000. RX es base adimensional de fórmula dependiente de score/airtime, no microsegundos. SDK lectura entrega enteros de wire, no float ya escalado. Boot limita RX0..20 y AF0..9; setter actual no aplica esas comprobaciones. | `MyMesh.cpp:269-270,941-942,1425-1442`; `reader.py:1040-1053`; SDK `device.py:81-90` |
| Telemetría base/ubicación/entorno | APP_START1 / OTHER_PARAMS38 | Cada modo ocupa 2 bits:0 deny,1 flags de contacto,2 allow-all. Es permiso de respuesta a consultas, no intervalo de broadcast. Permisos de contacto usan `flags>>1`; bit favorito se conserva. | `NodePrefs.h:5-7`; `MyMesh.cpp:627-662,1068-1069,1443-1458`; SDK `device.py:117-130` |
| Advert GPS policy | APP_START1 / OTHER_PARAMS38 | 0 none,1 share en esta copia. No confundir flags de ubicación del ADVERT con flags de permisos del contacto. | `NodePrefs.h:9-10`; `MyMesh.cpp:1067,1451` |
| Multi ACKs | APP_START1 / OTHER_PARAMS38 | Campo u8 desde protocolo7; conservar demás campos al modificarlo. Cambia número de ACKs futuros, aunque el propio guardado no envía RF. | `MyMesh.cpp:282-284,1066,1453`; SDK `device.py:117-130,172-178` |
| Manual add | APP_START1 / OTHER_PARAMS38 | Campo compartido con otros permisos; preservar campos no editados. | `MyMesh.cpp:1070,1444`; SDK `device.py:156-162` |
| AutoAdd | GET59 / SET58 | Config bitmask y `max_hops`:0 ilimitado,1 sólo directos, N admite hasta N-1 intermediarios, máximo64. No etiquetar N directamente como distancia en saltos. | `NodePrefs.h:41`; `MyMesh.cpp:1974-1986`; `BaseChatMesh.cpp:163-168` |
| Path hash mode local | DEVICE_QUERY22 / SET61 | Mode0/1/2 =1/2/3 bytes. Protocolo10 añade campo DEVICE_INFO; es preferencia de envío local, no ancho de todas las rutas almacenadas. | `reader.py:435-437`; `MyMesh.cpp:1459-1465`; SDK `device.py:383-393` |
| PIN BLE | DEVICE_QUERY22 / SET37 |0 o100000..999999; u32 LE; propiedad BLE que puede configurarse usando USB/TCP. No es la contraseña admin de un repetidor. | `reader.py:427`; `MyMesh.cpp:1790-1802`; SDK `device.py:180-184` |
| Custom vars | GET40 / SET41 | `key:value` para SensorManager; conjunto dependiente de hardware/build. No asumir que admite claves arbitrarias de radio o host. GPS condicional guarda `gps` y `gps_interval`0..86400s. | `MyMesh.cpp:1804-1843`; SDK `device.py:191-199` |
| Hora | GET5 / SET6 | epoch u32 LE; altera reloj del transceptor local. | `MyMesh.cpp:1234-1242`; SDK `device.py:54-62` |
| Batería/estadísticas | GET_BATT20 / GET_STATS56 | Consultas locales sin paquetes RF. Separar estadísticas del bridge de las del transceptor. | opcodes `MyMesh.cpp:25,55`; SDK `device.py:50-52,361-377` |
| Emitir advert | SEND_SELF_ADVERT7 | zero-hop o flood; sí genera paquetes RF. No es un guardado de nombre/posición. | SDK `device.py:23-28`; `MyMesh.cpp:12` |
| Reboot / factory reset | CMD19 / CMD51 | Reboot cambia disponibilidad; factory reset requiere flujo/token específico. No tratarlos como lectura ni parte automática del guardado. | SDK `device.py:46-48,317-359`; firmware `MyMesh.cpp:1467` |
| Intervalo advert / telemetría | Sin comando Companion específico acreditado en esta revisión | `NodePrefs` no contiene timers `advert_interval`/`telemetry_interval`. Si la app ofrece intervalos son políticas host que deben documentarse aparte y persistir/rearmar de forma segura. No confundir con `gps_interval`, que es intervalo del sensor GPS. | `NodePrefs.h:14-43`; tabla de opcodes `MyMesh.cpp:6-64` |

`DEVICE_INFO` informa nivel de protocolo, capacidades de contactos/canales, pin, build, modelo, versión, repeat y hash mode según nivel (`reader.py:420-438`). Los campos ausentes no deben sustituirse por una falsa capacidad o un éxito inventado. SDK `get_path_hash_mode` retorna0 ante consulta ausente/fallida (`device.py:388-393`): fallback no demuestra que la consulta haya funcionado.

## Matriz REMOTA: CLI y solicitudes por RF

La configuración remota de repetidor/sala/sensor usa mensajes administrativos cifrados/MAC; no son los setters locales de Companion. `send_cmd` se codifica CMD2, tipo de texto1/CLI_DATA (`commands/messaging.py:63-80`); Companion envía `sendCommandData` y devuelve `MSG_SENT`, sin ACK esperado para CLI (`MyMesh.cpp:1102-1124`). `MSG_SENT` sólo demuestra despacho, no aplicación ni respuesta «OK» del remoto.

| Control/dato | Comando oficial de esta revisión | Alcance/limitación | Contraste con app |
|---|---|---|---|
| Radio completo | `get radio`; `set radio F,BW,SF,CR` | Mismas unidades humanas MHz/kHz, SF5..12,CR5..8. Guarda y responde «OK - reboot to apply», no aplica radio inmediatamente. `CommonCLI.cpp:588-604,859-863`. | Builder de `set_radio` correcto; aliases individuales `set freq/sf/bw/cr` no equivalentes remotos. `set freq` está restringido a serial (`:713`). |
| Potencia | `get tx`; `set tx n` | CommonCLI llama callback de potencia; no valida rango igual que Companion en esa rama. Capacidad/rango board deben validarse externamente. `CommonCLI.cpp:708-712,898-899`. | Clamp por modelo de la app no acredita hardware remoto desconocido. |
| Repetición | `get repeat`; `set repeat on/off` | Forwarding de ese remoto, no repeat mode del Companion. `CommonCLI.cpp:531-534,839-840`. | No aplicar la restricción de bandas Companion al servidor remoto por analogía. |
| Hop/flood límites | `get/set flood.max`, `.advert`, `.unscoped` |0..64 según rama. `CommonCLI.cpp:632-658,868-873`. | `set hop_limit` no existe. Semántica exacta debe seguir reglas de forwarding/scopes, no sustituir sin diseño. |
| Nombre/owner | `get/set name`; `get/set owner.info` | Owner texto literal; `|` representa salto de línea; no hay parser que elimine comillas. `CommonCLI.cpp:523-530,668-677,837-838,876-885`. | Builder agrega comillas a owner (`RepeaterManager:368`), que quedan almacenadas como parte del texto. |
| Posición | `get/set lat`; `get/set lon` | CommonCLI usa float; no aplica rango geográfico en estas ramas. `CommonCLI.cpp:606-613,841-844`. | `set pos ...`, `set pos.alt`, fixed no son controles comunes oficiales de esta revisión. |
| Tuning | `get/set rxdelay`, `af`, `txdelay`, `direct.txdelay`, `dutycycle` | RX0..20; txdelay/direct0..2; AF directo float sin rango en setter; dutycycle1..100%. `CommonCLI.cpp:450-465,614-667,810-815,864-875`. | RX no unidadµs ni umbral heurístico de magnitud. Leer/escribir unidad de dominio explícita. |
| Hashes | `get/set path.hash.mode` |0/1/2. `CommonCLI.cpp:678-687,886-887`. | Preferencia de salida del remoto; separar de ancho por ruta. |
| Advert zero-hop periódico | `get/set advert.interval MINUTOS` |0 off o60..240min en esta revisión; se guarda minutos/2, por tanto cuantización2min. Rearma timer remoto al aplicar. `CommonCLI.cpp:160,496-504,828-829`. | Builder restringe2..240 y `0→2`; `300s→5min` resulta inválido para este firmware. No arreglar imponiendo un intervalo nuevo sin acuerdo. |
| Advert flood periódico | `get/set flood.advert.interval HORAS` |0 off o3..168h; rearma timer remoto. `CommonCLI.cpp:486-495,826-827`. | No confundir horas con minutos/segundos del control local. |
| Emitir advert manual | `advert`, `advert.zerohop` | Además del request/reply RF genera advert; `CommonCLI.cpp:191-197`. | Presentarlo como operación RF, no simple consulta/configuración. |
| Contraseña admin | `password NUEVA` | No `set admin.password`. Firmware devuelve contraseña en texto de confirmación (`CommonCLI.cpp:256-261`): redacción necesaria antes de almacenar/renderizar logs. | Builder alternativo inválido `set_admin_password→set admin.password`. Nunca loguear credenciales reales al reproducir. |
| Guest/read-only | `set guest.password`, `set allow.read.only` | Propiedades de servidores remotos; no auth API key ni PIN BLE. `CommonCLI.cpp:482-485,506-509,824-831`. | Activar acceso de lectura no convierte sesión guest en admin. |
| ACL modificar | `setperm PUBLIC_KEY PERMS_U8` | Repeater/room/sensor. Rol en bits bajos:0 guest/delete,1 read-only,2 read-write,3 admin; bits adicionales se preservan según capacidades. Alta/cambio exige public key completa; borrado exige entrada existente. `ClientACL.h:7-11,33`; `ClientACL.cpp:121-142`; repeater `MyMesh.cpp:1240-1260`. | `acl add/remove/list` no existe; no reemplazar role string con número sin validar máscara. |
| ACL leer | Solicitud binaria ACL tipo5 mediante CMD50 | Sólo admin; SDK `binary.py:110-132`. `get acl` textual está reservado a consola serial (`MyMesh.cpp:1262`). Room enumera sólo admins en esa respuesta (`simple_room_server/MyMesh.cpp:202-209`). | Alias `get_acl→get allow.read.only` lee otra propiedad y `acl list` no sirve. |
| Estadísticas actuales | Solicitud binaria STATUS tipo1 / TELEMETRY tipo3 | STATUS/telemetry según rol/build/permisos; SDK `packets.py:9-13`, `binary.py`. | `stats-core/radio/packets` son **serial only** en CommonCLI (`:437-442`); alias remoto `status→stats-core` inválido. |
| Batería | STATUS/telemetría | `get pwrmgt.bootmv` es voltaje al arranque, únicamente build NRF52_POWER_MANAGEMENT (`CommonCLI.cpp:970-975`), no batería actual genérica. | `bat→get pwrmgt.bootmv` cambia significado y no funciona en todos los boards. |
| Vecinos/discovery | `neighbors` / `discover.neighbors` | `neighbors` consulta; `discover.neighbors` solicita discovery adicional (`simple_repeater/MyMesh.cpp:1273-1280`). | Builder mapea discovery a `neighbors`, operaciones distintas. |
| Versión/hora/reboot | `ver`, `clock`, `clock sync`, `time EPOCH`, `reboot` | Soportados por CommonCLI; reloj puede ajustar al timestamp recibido; reboot afecta conectividad remota. `CommonCLI.cpp:185-217,272-274`. | `get uptime`, `help`, `ping 0` no son CLI oficiales aquí; ping/traceroute tienen mecanismos de protocolo propios. |

## Roles y autenticación

- REPEATER: login admite contraseña admin, guest o clave ya autorizada con contraseña vacía; replay check. CLI remoto exige `client->isAdmin()` (`simple_repeater/MyMesh.cpp:90-144,702-756`). Una respuesta de login puede ser exitosa y NO admin.
- ROOM: login puede dar admin, read-write o guest/read-only según contraseña y configuración (`simple_room_server/MyMesh.cpp:326-397`); CLI sólo admin (`:466-471`). No equiparar permisos para chatear en sala con permiso de configuración.
- SENSOR oficial de esta copia tiene CommonCLI y comandos propios: admin/password/ACL; CLI exige admin (`simple_sensor/SensorMesh.cpp:335-360,382-432,558-606`). Tiene capacidades distintas de repeater/room; el rol SENSOR no demuestra que cualquier implementación tenga todas ellas.
- CLIENT/Companion de esta copia **no ejecuta CommonCLI como servidor administrativo remoto**. `BaseChatMesh.cpp:256-263` trata CLI_DATA como dato/respuesta para la UI. Una capacidad anunciada por firmware futuro1.18+ no puede darse por implementada en la referencia1.17.1.
- Flags de login `permissions/is_admin` son distintos de `acl_permissions`: firmware Companion traduce `data[6]` al primer flag y `data[7]` al byte ACL (`MyMesh.cpp:680-702`); SDK `reader.py:616-637`. Para ACL admin: `(acl_permissions & 3)==3`. El flag is_admin usa bit1 conceptual/valor1, no máscara3. Si faltan campos de firmware antiguo, no elevar privilegios.
- Login Companion CMD26 produce RF (`messaging.py:27-49`, `MyMesh.cpp:1528-1548`). Una contraseña no vacía no prueba que esté verificada. SDK sólo esperar `MSG_SENT` tampoco acredita autenticación; esperar respuesta correlacionada al destino, revisar `is_admin` y distinguir timeout/guest.

## Reproducciones mínimas

[reproduce_protocol.py](reproduce_protocol.py) observa constructores reales con `send` falso, sin conexión, callbacks, sockets, broker ni radio. El tuning compila únicamente el AST del método real para evitar importar `config` o leer `.env`; no construye el bridge. [reproduction.json](reproduction.json) contiene valores ficticios, no credenciales operativas.

Ejecutado: `.venv/Scripts/python.exe docs/audits/node-config-2026-10-03/protocol/reproduce_protocol.py`. No es una suite y no simula ejecución completa de firmware. La compatibilidad/rechazo se contrasta estáticamente con ramas oficiales.

| Observación | Resultado real aislado |
|---|---|
| SDK TX -9/-1 | `OverflowError: can't convert negative int to unsigned`;0 frames construidos |
| SDK TX0/20 | Frames `0c00000000` / `0c14000000` capturados, nunca enviados |
| Método tuning con input10/11/20 | Wire10000/11/20; firmware dividiría1000 ->10.0/0.011/0.02; discontinuidad de unidades |
| Intervalo remoto0/300s/3600s | Builder produce2/5/60min; los primeros dos no expresan intención válida según firmware actual |
| Frecuencia/SF/BW/CR individuales, posición, admin password, ACL | Constructor produce strings no soportados por CLI remoto de esta revisión; evidencia en JSON y ramas citadas |
| Owner `REPRO_DUMMY` | Constructor produce `set owner.info "REPRO_DUMMY"`; firmware copia comillas literal |
| `discover.neighbors` | Constructor produce `neighbors`, pierde operación de discovery |
| Alias `radio` con parámetros | Constructor produce `get radio` por precedencia del mapa de consultas; no aplica esos parámetros |

## Airtime y riesgos al corregir

Lecturas/escrituras locales Companion y GET_CONTACT no emiten RF por sí solas. Alteran parámetros y permisos futuros; emitir advert sí transmite. Lecturas REMOTAS CLI/binary status/telemetry/ACL/login son requests y respuestas RF, con coste multiplicado por ruta/retransmisión. Cada campo consultado por separado puede implicar otro request/reply; no afirmar duración exacta sin parámetros LoRa/payload/ruta medidos. Remote discovery y adverts agregan tráfico adicional. Una confirmación «despachado» no acredita aplicación: esperar respuesta puede duplicar tráfico si se añade read-back por campo; debe diseñarse sin polling automático nuevo.

Cambiar `advert.interval`/`flood.advert.interval` rearma timers de firmware. Además `CommonCLI::savePrefs` desactiva advert zero-hop que esté por debajo de60min (`:162-166`), incluso al guardar otra propiedad; es comportamiento oficial de esta revisión, no algo medido sobre una radio. No introducir unilateralmente nuevos intervals/reintentos/notificaciones durante corrección. Mantener reglas propias de roles, deduplicación, guarda de origen propio y limitadores existentes.

Layout de comandos descritos: bytes explícitos y campos escalares, sin padding del struct C++ ni CRC propio Companion. SDK serializa LE y firmware extrae enteros mediante `memcpy` nativo de plataformas examinadas; no atribuir un empaquetado C++ no verificado. Las unidades wire y de dominio se documentan por campo. La evidencia no acredita compatibilidad de todos los builds/hardware ni interop real.
