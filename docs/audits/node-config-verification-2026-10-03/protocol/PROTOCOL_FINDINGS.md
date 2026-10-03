# Verificación vigente de configuración: firmware, SDK y CLI

Fecha: 2026-10-03. Bridge observado: `9f561932d648470e8c8bd23fc789a66bdb378d0e`. Trabajo del agente especializado en protocolo; skills leídas: `meshcore-source-inspector` y `project-reference-audit`. No se modificó producción ni referencias. No se inicializó transporte, firmware, radio, broker o bridge.

## Procedencia y alcance

Los tres directorios oficiales contienen `.git` propio; `git -C ... rev-parse HEAD`, `remote get-url origin` y `status --short` dieron estas revisiones y estado limpio:

| Referencia | Origen | SHA |
|---|---|---|
| Firmware | `https://github.com/meshcore-dev/MeshCore` | `d92964352441e53b93e8667b802e04f6e072b39e` |
| SDK Python | `https://github.com/meshcore-dev/meshcore_py` | `c487efbe187f4b000020afdfc0349c4cdf503c5a` |
| CLI Python | `https://github.com/meshcore-dev/meshcore-cli` | `0856c723cdea3438811c62c190bbec3059e2dc48` |

SDK instalado: `meshcore 2.3.8`, ubicado en `.venv/Lib/site-packages/meshcore`. La igualdad de versión se complementó comparando el texto normalizado de `commands/device.py`, `commands/messaging.py` y `reader.py` con la referencia: los tres son idénticos. SHA256 normalizados respectivos: `ea3986288717c8a28f7f54ad2c5df502d30061092f6bf848edb5a77047e46773`, `34bbd1d469301d3e0d515dbdb75de7bb3d0389dcbbf626699171bb37d23776d5`, `395bf62fb40e14ee23560649750524982ed671382594b3dc45e145a5a0ca0a5d`. Esto no compara todos los módulos ni demuestra interoperabilidad física.

`reference/meshcore/examples/companion_radio/MyMesh.h:8,15` declara nivel de protocolo 13 y versión por defecto v1.17.1. El firmware real de una instalación no se consultó. El README enlaza `app.meshcore.nz` y `config.meshcore.io`, pero `reference/` no contiene su frontend oficial. Los demás clientes locales son comparaciones de terceros; la verificación externa de la app corresponde al dirigente.

El helper `inspect_meshcore_ast.py --symbol TELEM_MODE --format json` terminó con colecciones vacías. Por tanto, sus resultados no se utilizan como prueba de ausencia de capacidades; se inspeccionaron las ramas reales de serialización y lectura.

## Contrato local Companion por parámetro

Las referencias de esta tabla son relativas a la raíz del repositorio. La lectura/escritura indicada describe el protocolo de la referencia. La existencia del opcode no acredita que la WebUI actual lo exponga correctamente o que un setter real haya funcionado en hardware. La matriz histórica extensa permanece en [la evidencia anterior](../../node-config-2026-10-03/protocol/PROTOCOL_FINDINGS.md); los firmwares/SDK de referencia no cambiaron entre ambas auditorías.

| Parámetro | Leer / escribir | Unidad, rango y aplicación | Fuente |
|---|---|---|---|
| Nombre | APP_START 1 / SET_ADVERT_NAME 8 | Máximo 31 bytes del campo, corte UTF-8 debe validarse antes; no emite advert automáticamente | `reference/meshcore/examples/companion_radio/MyMesh.cpp:1052,1212`; SDK `commands/device.py:30` |
| Latitud / longitud | APP_START 1 / CMD14 | i32 LE microgrados, [-90,90]/[-180,180]; cero válido | Firmware `MyMesh.cpp:1219`; SDK `device.py:36` |
| Altitud / ubicación fija | Sin setter Companion general acreditado | El tercer i32 de CMD14 está reservado y no se aplica; una custom var GPS depende del build | Firmware `MyMesh.cpp:1223`; `NodePrefs.h:14` |
| Frecuencia/BW/SF/CR | APP_START 1 / CMD11 | MHz y kHz ×1000 en u32 LE, SF/CR u8; 150..2500MHz, 7..500kHz, SF5..12, CR5..8; radio aplica inmediatamente | Firmware `MyMesh.cpp:1379`; SDK `device.py:70` |
| Repeat local | DEVICE_QUERY22 / byte opcional CMD11 | Nivel9+, limitado a rangos CMD60 de esa placa/build; preservar al escribir otra propiedad de radio | Firmware `MyMesh.cpp:1000,1391,1987`; SDK `reader.py:431` |
| TX power | APP_START 1 / CMD12 | Firmware consume i8, -9..MAX_LORA_TX_POWER anunciado; SDK2.3.8 construye u32 unsigned y no serializa negativos | Firmware `MyMesh.cpp:1415`; SDK `device.py:64` |
| RX delay / AF | GET43 / SET21 | u32 LE ×1000. RX es factor adimensional, no µs. Al arrancar firmware limita RX0..20 y AF0..9, aunque setter no lo comprueba | Firmware `MyMesh.cpp:941,1425`; SDK `reader.py:1040`, `device.py:81` |
| Telemetría base/ubicación/entorno | APP_START1 / OTHER_PARAMS38 | 2bits por campo: 0 deny,1 permisos de contacto,2 todos. Son permisos de respuesta, no timers | `NodePrefs.h:5`; Firmware `MyMesh.cpp:627,1443`; SDK `device.py:117` |
| Política ubicación advert | APP_START1 / OTHER_PARAMS38 | 0 no compartir,1 compartir; no confundir con tipo de advert RF | Firmware `MyMesh.cpp:1067,1451` |
| Multi ACK / manual add | APP_START1 / OTHER_PARAMS38 | Mantener resto de campos; multi ACK disponible según versión. Cambia respuesta futura, guardado local no emite RF por sí mismo | Firmware `MyMesh.cpp:1066,1443`; SDK `device.py:117` |
| AutoAdd | GET59 / SET58 | Bitmask + max_hops; 0 ilimitado,1 directo,N admite N−1 intermediarios, máximo64 | Firmware `MyMesh.cpp:1974`; `BaseChatMesh.cpp:163` |
| Path hash mode | DEVICE_QUERY22 / SET61 | Mode0/1/2→1/2/3bytes; nivel10+ lectura; preferencia de salida local | Firmware `MyMesh.cpp:1459`; SDK `reader.py:435`, `device.py:383` |
| PIN BLE | DEVICE_QUERY22 / SET37 | u32 LE,0 o100000..999999. No es contraseña RF ni API key | Firmware `MyMesh.cpp:1790`; SDK `device.py:180` |
| Custom variables | GET40 / SET41 | `key:value`; claves disponibles por SensorManager/build, no parámetros arbitrarios del host | Firmware `MyMesh.cpp:1804`; SDK `device.py:191` |
| Default flood scope | GET64 / SET63 | Propiedad Companion distinta de regiones remotas, según protocolo/build | Firmware `MyMesh.cpp:1940,1957` |
| Flood scope key | SET54 | Variante según nivel de protocolo; no confundir selector host con soporte universal | Firmware `MyMesh.cpp:1929,1937` |
| Hora | GET5 / SET6 | Epoch u32 LE, reloj del transceptor | Firmware `MyMesh.cpp:1234`; SDK `device.py:54` |
| Batería / estadísticas | GET20 / GET56 | Consultas locales; estadísticas transceptor diferentes de contadores host | Firmware `MyMesh.cpp:1472,1865` |
| Advert / reboot | CMD7 / CMD19 | Advert sí transmite RF; reboot altera disponibilidad. No incorporar a un guardado genérico | SDK `device.py:23,46` |
| Owner, advert/telemetry interval, hop limit | Sin setter hardware Companion general acreditado | El almacenamiento host debe distinguirse del hardware; no existe garantía de timer por haber guardado una clave | `NodePrefs.h:14`; tabla opcodes `MyMesh.cpp:6` |

Rangos de parser son límites protocolarios, no prueba de soporte físico de todas las bandas/anchos, límites reguladores o capacidades de una placa. El SDK `get_path_hash_mode` puede retornar0 como fallback ante consulta fallida: la API debería conservar estado desconocido/error.

## Contrato remoto por campo y operación

Para repetir/sala/sensor, CLI administrativa usa `send_cmd` (CMD2, CLI_DATA) a través del Companion y de la malla. SDK devuelve MSG_SENT al despachar; la aplicación del remoto exige respuesta CLI correlacionada. Consulta binaria, login y cada CLI request/reply consumen RF.

| Campo/operación | Lectura / escritura oficial | Permisos, unidades y límites |
|---|---|---|
| Radio | `get radio` / `set radio F,BW,SF,CR` | Admin CLI; mismos rangos humanos del parser local, guarda prefs y requiere reboot. `CommonCLI.cpp:588,859` |
| TX power | `get tx` / `set tx` | Admin; callback de placa, sin validación equivalente al setter Companion; consultar límites hardware. `CommonCLI.cpp:708,898` |
| Repeat | `get repeat` / `set repeat on/off` | Forwarding remoto distinto de repeat Companion. `CommonCLI.cpp:531,839` |
| Nombre | `get name` / `set name` | Admin; valida caracteres propios del firmware. `CommonCLI.cpp:523,837` |
| Owner | `get owner.info` / `set owner.info TEXTO` | Sin comillas de sintaxis; `|` se transforma en salto de línea. `CommonCLI.cpp:668,876` |
| Latitud/longitud | `get lat` y `get lon` / `set lat` y `set lon` | Admin; setters oficiales de esta rama no validan rango geográfico. `CommonCLI.cpp:606,841` |
| RX/AF | `get rxdelay`, `get af` / `set rxdelay`, `set af` | RX0..20; AF float, setter no acota; unidad factor. `CommonCLI.cpp:450,614,810,864` |
| TX delays | `get/set txdelay`, `direct.txdelay` | Factor0..2. `CommonCLI.cpp:624,660` |
| Duty cycle | `get/set dutycycle` | Porcentaje1..100, convertido a AF; no µs. `CommonCLI.cpp:450` |
| Hop/flood limits | `get/set flood.max`, `.advert`, `.unscoped` | Máximo64, semántica específica de forwarding. No existe `set hop_limit`. `CommonCLI.cpp:632,868` |
| Hash mode | `get/set path.hash.mode` | Mode0/1/2. `CommonCLI.cpp:678,886` |
| Advert local periódico | `get/set advert.interval` | Minutos:0 off o60..240; cuantización a2min; rearma timer. `CommonCLI.cpp:160,496,828` |
| Advert flood periódico | `get/set flood.advert.interval` | Horas:0 off o3..168; rearma timer. `CommonCLI.cpp:486,826` |
| Advert manual | `advert`, `advert.zerohop` | RF adicional al comando de administración. `CommonCLI.cpp:191` |
| Password admin | `password NUEVA` | Cambia contraseña; respuesta firmware incluye texto sensible y debe redactarse. `CommonCLI.cpp:256` |
| Guest/access policy | `get/set guest.password`, `get/set allow.read.only` | Secretos RF distintos de PIN/API key; lectura no acredita admin. `CommonCLI.cpp:482,506,824,830` |
| ACL alta/cambio/baja | `setperm PK BYTE` | Role bits bajos: GUEST0,READ_ONLY1,READ_WRITE2,ADMIN3.0 borra existente; alta/cambio exige clave completa. `ClientACL.h:7`, `ClientACL.cpp:121` |
| ACL leer | Solicitud binaria tipo5 / SDK `req_acl_sync` | Sólo admin; `get acl` textual serial-only. Room responde sólo admins. `binary.py:110`, repeater `MyMesh.cpp:1262`, room `MyMesh.cpp:202` |
| Status/telemetría | Solicitud binaria STATUS1/TELEMETRY3 | Según rol/build/permisos. `stats-core/radio/packets` de CommonCLI son serial-only (`:437`) |
| Batería | STATUS/TELEMETRY | `pwrmgt.bootmv` es voltaje al boot, build condicional, no voltaje actual genérico. `CommonCLI.cpp:970` |
| Vecinos/discovery | `neighbors` / `discover.neighbors` | Consultar y provocar descubrimiento son operaciones diferentes. Repeater `MyMesh.cpp:1273` |
| Versión/hora/reboot | `ver`, `clock`, `clock sync`, `time EPOCH`, `reboot` | Admin CLI; reloj/reboot no son queries. `CommonCLI.cpp:185` |

Opciones como RX gain/FEM, CAD, interferencia, AGC, bridge serial/ESP-NOW, energía y logging tienen ramas dependientes de build/hardware en CommonCLI. No están acreditadas como controles genéricos del formulario actual: desarrollar un perfil de capacidades, nunca habilitar todos esos setters sólo porque una copia del parser los contiene.

## Roles y privilegios

Tipos canónicos: NONE0/CHAT1→CLIENT; REPEATER2,ROOM3,SENSOR4, según `src/protocol_types.py:114` y `AdvertDataHelpers.h`. LOCAL se identifica mediante la clave propia, no sólo el tipo advert.

- REPEATER, ROOM y SENSOR de esta copia aceptan CLI sólo para admin: repeater `MyMesh.cpp:702`, room `MyMesh.cpp:466`, sensor `SensorMesh.cpp:558`. El sensor contiene CLI propia, pero no se infiere soporte de todos los controles del repetidor en cualquier firmware sensor.
- CLIENT/Companion de esta referencia recibe CLI_DATA como respuesta a entregar a la UI (`BaseChatMesh.cpp:256`), no como servidor CommonCLI remoto. Firmware futuro requiere evidencia de su versión concreta.
- `reader.py:622` interpreta `is_admin` desde flag de login valor1; `acl_permissions` es otro byte (`:635`). Para ACL admin se usa `(byte & 3)==3`. No aplicar la máscara de uno al otro.
- Login exitoso puede ser guest/read-only. Contraseña escrita en formulario no acredita autenticación; esperar respuesta correlacionada, revisar permisos y mantener LOCAL/REPEATER fuera de chat/contactos del bridge.

## Reproducciones vigentes y estado de correcciones

Comando ejecutado desde raíz:

```powershell
.venv/Scripts/python.exe docs/audits/node-config-verification-2026-10-03/protocol/reproduce_protocol.py
```

Salida exitosa:4 casos SDK,3 tuning,60 builders. [Script](reproduce_protocol.py) y [datos completos](reproduction.json). Datos y password ficticios `REPRO_DUMMY`. `send` falso sólo captura bytes. El método de tuning real se compila desde AST sin importar bridge/config/dotenv; no ejecuta prevalidadores ni integra endpoints. Los casos son observaciones, no tests que conviertan bugs en contrato. Firmware fue contrastado por código, no ejecutado.

Incidencia de aislamiento detectada al revisar el harness inicial: una importación ordinaria de `src.repeater_manager` ejecutaba `src/__init__.py`, que importa `bridge_core` y `config`; este último tiene carga de dotenv a nivel de módulo. No se imprimió ni guardó contenido operativo, no se construyeron servicios y el proceso terminó, pero esa primera ejecución no acredita ausencia de intento de lectura de `.env`. Se corrigió el harness instalando un namespace `src` sin ejecutar su inicializador y bloqueando aperturas de `.env` por `builtins.open/io.open`. Se repitió el diagnóstico: la evidencia final registra `bridge_or_config_imported=false` y cero intentos `.env`. Los resultados actuales proceden de esa ejecución aislada; la limitación inicial se conserva aquí y no se atribuye como fallo adicional de configuración de la UI.

| ID / prioridad | Observación reproducida actual | Fuente/causa | Posible solución |
|---|---|---|---|
| P01 P1 | `acl_add permission=admin`→`setperm PK 1`; guest/read→2 | `src/repeater_manager.py:394` mapea roles contra firmware `ClientACL.h:7` | Enum ACL único: admin3/read_write2/read_only1/guest0; preservar flags altos y validar0..255 |
| P02 P1 | `acl_remove PK`→`setperm PK 1`, no borra | `src/repeater_manager.py:396` usa default1 incluso remove | Baja debe construir0 explícito, requerir entrada destino y respuesta; no deducir borrar de un rol distinto |
| P03 P1 | Advert0→0 corregido, pero1200→60,120→120,241→60,−1/INVALID→0; flood1→3,−1→3,INVALID→0 | `src/repeater_manager.py:355` adivina unidad por magnitud y clampa | Contrato unidades explícitas minutos/horas o conversión única desde segundos; rechazar inválido sin alterar; mostrar cuantización efectiva. Intervalos/umbrales nuevos requieren acuerdo del usuario |
| P04 P2 | `get_acl`→`get allow.read.only`; `acl_list`→None | `src/repeater_manager.py:269` consulta política distinta; CLI get acl serial-only | Leer ACL vía SDK req_acl_sync tipo5 y conservar permisos/capacidad/error |
| P05 P2 | `status`→`stats-core`, uptime→`get uptime`, help→`help` | `src/repeater_manager.py:216` aliases no equivalentes al CLI remoto de referencia | STATUS binario para métricas; retirar aliases no soportados o condicionarlos por firmware. `battery`→bootmv no es lectura actual |
| P06 P2 | `discover.neighbors`→`neighbors` | `src/repeater_manager.py:255` colapsa operación de discovery a consulta | Conservar intención/coste RF; usar descubrimiento sólo por petición específica |
| P07 P1 | `set_radio CR=INVALID`→CR5; `99/7`→7 | `src/repeater_manager.py:307`; batch también inicializa CR5 `repeater_executor.py:283` | Validar enum5..8 o formato exacto4/5..4/8; rechazar cadena incompatible antes de despachar |
| P08 P2 | `radio` con parámetros→`get radio`; `lat/lon` con valores→queries | `src/repeater_manager.py:184` ejecuta mapa queries antes de setters | Distinguir lectura/escritura en acción explícita; eliminar alias ambiguo o exigir ausencia de payload |
| P09 P1 | `set_latitude`, `set_longitude`, `set_repeat_enabled`, `set_guest_password`, `set_region`→None | Keys admitidas en lote `repeater_executor.py:233`; bucle construye `set_{key}` `:325` | Normalización canónica del lote y plan completo antes del primer envío. No omitir claves admitidas silenciosamente. Builder isolated no demuestra por sí solo respuesta final HTTP; agente backend verifica integración |
| P10 P2 | `set_lat 100`, `set_lon nan`, `setperm xx 999` producen texto | Builders sin validación; firmware lat/lon tampoco valida rango | Validar tipo finito/rango geográfico/clave64hex y máscara u8 antes del envío; límites hardware no inferidos |
| P11 P2 | SDK TX−9/−1→OverflowError,0 frames; TX0/20 captura frame correctamente | SDK unsigned `device.py:64`; firmware acepta i8 −9 | Resolver transporte signed con compatibilidad SDK explícita o declarar capacidad limitada. Bridge actualmente clampa mínimos a0/2/10, por lo que este caso es limitación SDK aislada, no prueba de fallo directo del POST actual |

Correcciones observadas frente al informe anterior: setters remotos unitarios freq/sf/bw/cr/hop/position/alt retornanNone; owner ya no agrega comillas; admin password usa`password`; advert0 conserva desactivación; tuning10/11/20→wire10000/11000/20000 y firmware10/11/20. AF20 continúa fuera del rango persistente de boot0..9: no presentar la desaparición de la discontinuidad de unidades como aceptación de todos los valores.

No se valida positivamente cada campo por haber pasado estos67 escenarios. Falta respuesta real del dispositivo por campo, lectura posterior, persistencia/reinicio y perfil concreto. Algunos parámetros sólo admiten lectura (estado), otros deben ser write-only (secretos en producto), otros carecen de setter hardware. La UI debe hacer visible esa distinción.

## Secuencia propuesta de aceptación

1. Construir registro de parámetros con acción, unidad, rango, rol, versión/build, permiso, read-only/write-only, persistencia y reboot. Resolver clave canónica y LOCAL antes de operar.
2. Leer baseline local con APP_START/DEVICE_QUERY y consultas específicas; mantener `unknown/error` si falla. Para remoto usar consultas individuales autorizadas con respuesta correlacionada; sin polling añadido.
3. Validar y normalizar un plan completo sin RF: rechazo de desconocidos, sin defaults inventados, enum CR y ACL correctos, unidad fija y parámetros compuestos preservados.
4. Ejecutar campos editados, conservar estado por campo: no enviado/enviado/rechazado/aceptado/aplicado/no verificado/pending reboot. MSG_SENT no significa aplicado; no prometer rollback hardware.
5. Readback explícito bajo demanda comparando dominio y wire/quantización. Secretos no se devuelven a REST/WS/MQTT/terminal para verificarlos; autenticar con nuevo secreto ficticio sólo en entorno de prueba autorizado.
6. En fixture aislada, comprobar valores extremos, cero, UTF-8, NaN, claves parciales/ambiguas, falta baseline, guest/admin y errores/timeout de respuesta. En hardware autorizado posterior, corroborar persistencia tras reboot y reconexión/radio.
7. Revisar RF antes de implementación: cada lectura/escritura remota implica request/reply; adverts/discovery añaden tráfico; no estimar airtime exacto sin LoRa/payload/ruta. Fijar límites, retries/intervals sólo con el usuario y usar rate limiter existente, deduplicación y guarda origen propio.
8. Al modificar advert.interval/flood.advert.interval, reconocer que firmware rearma timers. `CommonCLI::savePrefs:162` desactiva zero-hop por debajo60min incluso al guardar otra propiedad. Host debe persistir último disparo si se añade scheduler y comprobar reinicio/config save; no crear ese timer en esta auditoría.

Layouts indicados son secuencias de bytes con escalares LE serializados; no structs C++ enviados íntegros, sin padding wire ni CRC raw propio. El packing/padding de estructuras de memoria no se infiere de esta inspección. Framing Companion SDK y framing raw propio del bridge son distintos.
