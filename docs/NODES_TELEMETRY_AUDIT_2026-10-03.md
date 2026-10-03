# Auditoría de telemetría y rutas de la vista Nodos

Fecha: 2026-10-03. Estado: auditoría de código y **propuesta de implementación**, sin cambios funcionales ni suites ejecutadas.

## Alcance y procedencia

Se audita la SPA Vanilla JS de este repositorio, no el cliente móvil oficial. La vista es `#tab-nodes`, con contenedor `#nodesUnifiedGridUi`: [index.html, línea 234](../src/web/static/index.html#L234). No existe un componente `NodeDetailView`; las tarjetas y su actualización están en `NodesModule`.

Base examinada: bridge `7bccf79b98d799fb9010abf1e3eb801c375d6879`. Referencias locales, sólo lectura:

| Fuente | Revisión Git propia | Uso |
|---|---|---|
| `reference/meshcore` — meshcore-dev/MeshCore | `d92964352441e53b93e8667b802e04f6e072b39e` | Firmware y serialización oficiales |
| `reference/meshcore_py` — meshcore-dev/meshcore_py | `c487efbe187f4b000020afdfc0349c4cdf503c5a` | Parsers y comandos Companion |
| `reference/meshcore_cli` — meshcore-dev/meshcore-cli | `0856c723cdea3438811c62c190bbec3059e2dc48` | Referencia CLI |

El SDK local y el instalado consultados declaran 2.3.8; las dependencias actuales requieren `meshcore>=2.3.8` ([requirements.txt, línea 4](../requirements.txt#L4)). Esto no determina la versión del firmware de una radio operativa ni la última versión publicada. El informe del 2026-09-29 menciona otra versión y se conserva como evidencia histórica.

Trabajo delegado: agente frontend, agente firmware/protocolo y agente backend/contratos; integración por el agente principal. Skills aplicadas: `meshcore-source-inspector`, `contract-openapi-sync`, `python-patterns-typing`, `project-reference-audit` y `domain-adr-keeper`. No se modificaron referencias, dependencias, datos operativos o configuración de radio. No se arrancaron servicios ni se realizaron capturas visuales; los estados de UI se acreditan mediante código.

## Fase 1 — Estado de las seis métricas

**Presente** exige dato, significado correcto y renderizado. **Parcial** indica infraestructura relacionada pero incompleta; no implica que la métrica exacta esté visible.

| Métrica | Estado | Modelo y adquisición | Interfaz actual y evidencia |
|---|---|---|---|
| **Distance away** | **Ausente** | Existen coordenadas, pero no distancia derivada. [contact_manager.py:556](../src/contact_manager.py#L556). | Sólo ubicación/GPS: [nodes.js:226](../src/web/static/js/modules/nodes.js#L226), [429](../src/web/static/js/modules/nodes.js#L429). No cálculo Haversine en esta vista. |
| **Last Advert Heard** | **Parcial** | Existe `last_advert`, timestamp del reloj **remoto**; falta `last_advert_heard_at` local. [contact_manager.py:80](../src/contact_manager.py#L80), [565](../src/contact_manager.py#L565). | Se muestra actividad `last_seen`, no tiempo desde el último advert recibido. [nodes.js:231](../src/web/static/js/modules/nodes.js#L231), [422](../src/web/static/js/modules/nodes.js#L422). |
| **Path: último paquete entrante** | **Ausente** | No se almacena una observación de ruta RX por nodo; se descarta `RX_LOG_DATA`. [sdk_adapter.py:913](../src/serial/sdk_adapter.py#L913). | `best_route` es texto resumido, no hashes: [nodes.js:396](../src/web/static/js/modules/nodes.js#L396). |
| **Hops Away** | **Parcial** | Existe `hops`, pero varios caminos convierten ausencia en cero e ignoran `path_len`. [contact_manager.py:63](../src/contact_manager.py#L63), [1126](../src/contact_manager.py#L1126), [rx_router.py:461](../src/rx_router.py#L461). | Se muestran saltos; cero se interpreta como directo, sin procedencia. [nodes.js:242](../src/web/static/js/modules/nodes.js#L242), [442](../src/web/static/js/modules/nodes.js#L442), [895](../src/web/static/js/modules/nodes.js#L895). |
| **Out Path** | **Parcial** | `out_path` y longitud existen en modelo/JSON/REST, pero sincronización y handlers pierden campos. [contact_manager.py:81](../src/contact_manager.py#L81), [566](../src/contact_manager.py#L566), [sdk_adapter.py:1510](../src/serial/sdk_adapter.py#L1510). | Nodos no renderiza la secuencia saliente. El botón Ruta abre traceroute; no sustituye esta métrica pasiva. [nodes.js:500](../src/web/static/js/modules/nodes.js#L500), [map.js:498](../src/web/static/js/modules/map.js#L498). |
| **Out Path Hash Size** | **Parcial** | Se conserva `out_path_hash_mode`, tipado como string, sin derivar ancho. [contact_manager.py:83](../src/contact_manager.py#L83), [568](../src/contact_manager.py#L568), [1746](../src/contact_manager.py#L1746). | No se muestra por nodo. El selector local configura la estación, no el ancho de cada ruta: [index.html:945](../src/web/static/index.html#L945). |

Resultado: ninguna está completa de extremo a extremo. La métrica exacta «Last Advert Heard» tampoco está implementada, aunque se clasifica parcial por sus campos relacionados.

### Errores concretos que debe resolver la implementación

1. **Presencia artificialmente reciente.** `discover_node` fuerza `last_seen=ahora` al importar/descubrir ([contact_manager.py:1214](../src/contact_manager.py#L1214), [1228](../src/contact_manager.py#L1228)). `AdvertHandler` también acepta snapshots `CONTACTS`/`NEXT_CONTACT` ([advert_handler.py:49](../src/routers/advert_handler.py#L49)) y establece ahora ([118](../src/routers/advert_handler.py#L118)). JS vuelve a usar el reloj del navegador ([nodes.js:133](../src/web/static/js/modules/nodes.js#L133), [658](../src/web/static/js/modules/nodes.js#L658)). Ninguno acredita por sí solo el último advert oído.
2. **Pérdida de rutas en la importación.** `sync_all_contacts` omite `flags`, `out_path`, longitud y modo. Bootstrap y sincronización REST copian `last_advert` a `last_seen` cuando lo consideran plausible, mezclando relojes: [bridge_core.py:697](../src/bridge_core.py#L697), [contacts_controller.py:123](../src/web/controllers/contacts_controller.py#L123). El handler de advert omite incluso el `last_advert` remoto actualizado ([advert_handler.py:117](../src/routers/advert_handler.py#L117)).
3. **WebSocket atrasado respecto a REST.** `rx_router` publica `contact_info` congelado devuelto por descubrimiento antes de fusionar GPS/batería y contadores. [rx_router.py:591](../src/rx_router.py#L591), [604](../src/rx_router.py#L604), [618](../src/rx_router.py#L618), [631](../src/rx_router.py#L631). Debe publicar el registro final.
4. **Contrato RF ambiguo.** WebSocket desempaqueta `.data` de `rf_packet` ([websocket.js:72](../src/web/static/js/core/websocket.js#L72)); `CapturedPacket` tiene `packet_type`, mientras Nodos decide por `type/event_type` ([packet_buffer.py:32](../src/packet_buffer.py#L32), [nodes.js:96](../src/web/static/js/modules/nodes.js#L96)). Añadir campos al buffer sin un evento de estado canónico no garantiza actualización de tarjetas.
5. **Directorio incompleto.** `/api/nodes` devuelve por defecto 100 elementos y metadatos de paginación ([nodes_controller.py:17](../src/web/controllers/nodes_controller.py#L17)); JS solicita sólo la primera página ([nodes.js:193](../src/web/static/js/modules/nodes.js#L193)). Puede faltar el nodo local usado como origen GPS.
6. **Coordenadas cero.** La inferencia `latitude != 0` para posición fija excluye el ecuador ([contact_manager.py:562](../src/contact_manager.py#L562)); compartir validación explícita de disponibilidad, rangos y procedencia, sin rechazar automáticamente latitud o longitud cero.

## Fase 2 — Verdad del protocolo y arquitectura

### Información disponible en firmware/SDK

| Información | Fuente efectiva | Cálculo o limitación |
|---|---|---|
| Coordenadas remotas | ADVERT opcional, flag GPS `0x10`; también telemetría LPP GPS tipo 136 cuando existe. [AdvertDataHelpers.h:29](../reference/meshcore/src/helpers/AdvertDataHelpers.h#L29), [meshcore_parser.py:173](../reference/meshcore_py/src/meshcore/meshcore_parser.py#L173), [reader.py:776](../reference/meshcore_py/src/meshcore/reader.py#L776). | ADVERT usa i32 LE en microgrados; LPP tiene su propio layout/endianness. No comparten un decoder genérico. |
| Coordenadas locales | `SELF_INFO`. [reader.py:165](../reference/meshcore_py/src/meshcore/reader.py#L165). | Distancia calculada por el cliente; el protocolo no entrega distancia geográfica. |
| Fecha anunciada | `ContactInfo.last_advert_timestamp`. [ContactInfo.h:16](../reference/meshcore/src/helpers/ContactInfo.h#L16). | Usa el reloj del **nodo remoto**; no es «heard». `lastmod` usa el reloj local, pero también cambia por rutas ([BaseChatMesh.cpp:331](../reference/meshcore/src/helpers/BaseChatMesh.cpp#L331)). |
| Fecha/ruta del último advert oído | Caché Companion `AdvertPath.recv_timestamp` y `GET_ADVERT_PATH` (42). [MyMesh.cpp:368](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L368), [1844](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L1844), [commands/contact.py:212](../reference/meshcore_py/src/meshcore/commands/contact.py#L212). | Caché limitada a 16 entradas y prefijo de 7 bytes ([MyMesh.h:79](../reference/meshcore/examples/companion_radio/MyMesh.h#L79), [257](../reference/meshcore/examples/companion_radio/MyMesh.h#L257)); miss, expulsión o ambigüedad no permiten inventar datos. Sólo último **advert**, no cualquier paquete. |
| Ruta RX | `RX_LOG_DATA` push `0x88` con paquete RF y parser `path/path_len`. [MyMesh.cpp:286](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L286), [reader.py:683](../reference/meshcore_py/src/meshcore/reader.py#L683), [meshcore_parser.py:69](../reference/meshcore_py/src/meshcore/meshcore_parser.py#L69). | Recepción pasiva, disponibilidad dependiente del dispositivo. La identidad del origen debe resolverse; un hash corto no basta. |
| Ruta saliente | Contacto Companion y aprendizaje de `PAYLOAD_PATH` autenticado. [BaseChatMesh.cpp:316](../reference/meshcore/src/helpers/BaseChatMesh.cpp#L316), [Mesh.cpp:130](../reference/meshcore/src/Mesh.cpp#L130). | No es automáticamente la inversión del último camino RX. |
| Cambios de ruta | Firmware `PUSH_CODE_PATH_UPDATED` `0x81`; SDK `EventType.PATH_UPDATE` (`path_update`), sólo public key. [MyMesh.cpp:406](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L406), [reader.py:579](../reference/meshcore_py/src/meshcore/reader.py#L579). | El SDK no refresca aquí su caché: usar `GET_CONTACT` (30) por enlace local, salvo refresco posterior al push acreditado. No confundir con descubrimiento por RF. |
| Descubrimiento bidireccional | `PATH_DISCOVERY_RESPONSE` `0x8D`, anchos separados de entrada/salida. [reader.py:926](../reference/meshcore_py/src/meshcore/reader.py#L926). | `sendPathDiscovery` (52) **transmite por radio** ([MyMesh.cpp:1602](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L1602)); fuera del flujo pasivo propuesto. |

ACK confirma entrega/correlación; no aporta por sí mismo una ruta completa o una clave pública de origen. No usarlo para asignar arbitrariamente caminos RX. Telemetría puede aportar ubicación, pero no sustituye el registro de anuncios ni garantiza un camino completo.

Los `flags` de la libreta Companion no son los flags del app data ADVERT: incluyen favorito y no acreditan GPS ([BaseChatMesh.cpp:91](../reference/meshcore/src/helpers/BaseChatMesh.cpp#L91)). La disponibilidad de posición debe proceder de ADVERT con GPS, telemetría o configuración local. Un snapshot con `(0,0)` no permite resolver disponibilidad mirando `contact.flags`.

La [documentación oficial de paquetes](https://docs.meshcore.io/packet_format/) y [payloads](https://docs.meshcore.io/payloads/) corrobora la codificación de caminos y el GPS opcional de ADVERT. Para detalles de Companion prima la serialización de la revisión examinada sobre una suposición de compatibilidad universal.

### Semántica de rutas y saltos

- **FLOOD:** cada repetidor agrega su hash; el camino recibido permite contar retransmisiones intermedias observadas ([Mesh.cpp:344](../reference/meshcore/src/Mesh.cpp#L344)).
- **DIRECT:** los hashes se consumen durante el recorrido ([Mesh.cpp:78](../reference/meshcore/src/Mesh.cpp#L78), [334](../reference/meshcore/src/Mesh.cpp#L334)). Un camino vacío al llegar **no demuestra cero saltos recorridos**. Conservar `remaining_only`; mostrar saltos recorridos desconocidos cuando no se pueda acreditarlos.
- **TRACE:** layout y ancho propios, incluyendo SNR; no aplicar el decoder de rutas ordinarias ([Mesh.cpp:41](../reference/meshcore/src/Mesh.cpp#L41), [693](../reference/meshcore/src/Mesh.cpp#L693)).
- Los hashes son prefijos de claves públicas, no IDs globalmente únicos ([Identity.h:19](../reference/meshcore/src/Identity.h#L19)). Con colisión, mostrar el hash y candidatos; no inventar nombres ni elegir el primer contacto.

Para un byte de longitud ordinario en el **wire**:

```text
count = encoded & 0x3f
mode  = encoded >> 6
bytes_per_hash = mode + 1
path_bytes = count * bytes_per_hash
```

Modos válidos 0/1/2: 1/2/3 bytes por hash, equivalentes a 8/16/24 bits. Modo 3 está reservado/no válido para este layout. El buffer admite 64 bytes; validar `count <= 63` y `count * width <= 64`, con máximos 63/32/21 hashes según ancho. [Packet.h:79](../reference/meshcore/src/Packet.h#L79), [Packet.cpp:13](../reference/meshcore/src/Packet.cpp#L13), [MeshCore.h:22](../reference/meshcore/src/MeshCore.h#L22).

**No aplicar de nuevo estas máscaras a `path_len` ya decodificado por el SDK.** En contactos, `0xff` significa ruta desconocida/flood y el SDK produce longitud/modo `-1` ([reader.py:108](../reference/meshcore_py/src/meshcore/reader.py#L108)). En respuestas de mensajes, `0xff` indica DIRECT ([reader.py:223](../reference/meshcore_py/src/meshcore/reader.py#L223)). Interpretar sentinels por tipo de paquete; nunca presentar 255 saltos.

### Dos límites críticos de adquisición

1. **Pérdida de bytes cero en `ADVERT_PATH`.** El parser de la referencia examinada y el instalado elimina todos los `00`: [reader.py:152](../reference/meshcore_py/src/meshcore/reader.py#L152). Un `00` puede formar parte legítima de un hash. El parser de contactos sí conserva exactamente `count * width` bytes ([reader.py:115](../reference/meshcore_py/src/meshcore/reader.py#L115)). Antes de usar esta caché, verificar una corrección concreta del SDK o crear un decoder de compatibilidad propio del bridge sobre datos originales. No se pueden reconstruir ceros ya eliminados. No modificar `reference/` ni `.venv`; no asumir que cualquier actualización resuelve este fallo.
2. **Raw RX no acredita autenticidad.** El log RF se genera antes de validar el paquete/firma ([Dispatcher.cpp:199](../reference/meshcore/src/Dispatcher.cpp#L199), [Mesh.cpp:271](../reference/meshcore/src/Mesh.cpp#L271)). Guardarlo como observación no confiable; sólo promover estado de un nodo mediante identidad comprobada y aceptación/correlación inequívoca. Si no puede acreditarse la correlación, queda anónimo o no verificado. No actualizar presencia con un ADVERT falsificado.

Además, la firma ADVERT cubre clave pública, timestamp y app data, **no cabecera ni path** ([Mesh.cpp:274](../reference/meshcore/src/Mesh.cpp#L274)). La aceptación acredita identidad/payload, pero la secuencia de repetidores sigue siendo una observación no autenticada criptográficamente.

Los pushes y la caché de advert reflejan anuncios aceptados por el firmware; éste descarta timestamps remotos repetidos/anteriores antes de actualizar el contacto ([BaseChatMesh.cpp:132](../reference/meshcore/src/helpers/BaseChatMesh.cpp#L132)). Con sólo esos pushes, la etiqueta exacta es «último anuncio aceptado observado», no todos los anuncios físicamente oídos. Para incluir otra recepción válida del mismo advert, el flujo raw necesitaría verificar identidad/firma con la semántica oficial y una política explícita de replay, manteniendo separado «oído» de actividad/presencia confiable. Si no se implementa esa verificación, declarar la cobertura parcial en UI y conservar la última observación acreditada.

### Layout y transporte

El contacto Companion se serializa campo a campo, no con `sizeof(ContactInfo)` ([MyMesh.cpp:166](../reference/meshcore/examples/companion_radio/MyMesh.cpp#L166)):

```text
opcode u8 | public_key[32] | type u8 | flags u8 | encoded_out_path_len u8
out_path[64] | name[32] | last_advert_remote u32 LE
latitude i32 LE | longitude i32 LE | lastmod_local u32 LE
```

148 bytes contando opcode. No trasladar padding/alineación del struct C++ al wire; el layout es explícito, sin CRC propio adicional de este registro. GPS en microgrados. La revisión usa `memcpy` para esos enteros y el SDK los interpreta como LE.

La app usa SDK por USB/UART o TCP ([sdk_adapter.py:261](../src/serial/sdk_adapter.py#L261), [280](../src/serial/sdk_adapter.py#L280)). Companion en Serial/TCP utiliza dirección `0x3c`/`0x3e`, longitud u16 LE y payload; [serial_cx.py:88](../reference/meshcore_py/src/meshcore/serial_cx.py#L88), [tcp_cx.py:74](../reference/meshcore_py/src/meshcore/tcp_cx.py#L74). El SDK soporta BLE Nordic UART/GATT ([ble_cx.py:26](../reference/meshcore_py/src/meshcore/ble_cx.py#L26)), pero este adapter no tiene rama BLE. BLE no usa el envoltorio Serial/TCP. No hay protobuf en este flujo: binario Companion en el dispositivo, diccionarios Python en SDK y JSON propio en REST/WebSocket. [Protocolo Companion oficial](https://docs.meshcore.io/companion_protocol/).

`RawSerialFramingAdapter` es un protocolo propio SOF/EOF/ESC/CRC en memoria, sin transporte UART físico ([raw_framing.py:23](../src/serial/raw_framing.py#L23)); no aplicarlo al tráfico Companion.

### Stores y flujo actual

```text
Firmware Companion → SDK Reader/Dispatcher → MeshcoreSDKAdapter
    → RxEventRouter / AdvertHandler → NodeRegistry
    → /api/nodes + eventos contact_updated/contact_discovered
    → App.knownNodes (Map compartido) → NodesModule → tarjeta

RX_LOG_DATA → _handle_log_data → descartado actualmente
```

`NodeRegistry` contiene `NodeContactInfo`, `NodeRfMetrics` y `NodeTelemetry`, junto con contadores y coordenadas; no hay una tabla separada de todos los caminos entrantes de cada vecino. La libreta del Companion conserva la ruta **saliente** por contacto. `PacketBuffer` mantiene capturas en RAM; no sustituye estado duradero de nodos. Frontend usa `knownNodes` ([app.js:26](../src/web/static/js/app.js#L26), [36](../src/web/static/js/app.js#L36)) y configuración local cacheada ([55](../src/web/static/js/app.js#L55)). La persistencia de nodos ya usa escritura temporal/reemplazo fuera del event loop ([contact_manager.py:1616](../src/contact_manager.py#L1616), [1649](../src/contact_manager.py#L1649)); reutilizarla.

## Fase 3 — Plan técnico de implementación

### 1. Modelo: preservar significado, disponibilidad y procedencia

Ampliar los modelos reales, sin crear una segunda entidad Node paralela:

| Campo propuesto | Tipo/semántica | Ubicación |
|---|---|---|
| `last_advert_heard_at` | `float | None`, recepción local de advert aceptado | `NodeRfMetrics` y update/JSON |
| `last_advert` existente | Timestamp remoto; etiqueta explícita | Conservar compatibilidad, no usar como heard |
| `last_rx_at` | `float | None`, recepción aceptada atribuible | Estado RF; separar importación de actividad |
| `last_rx_route` | `RouteObservation | None` | Estado RF/JSON/API |
| `out_path_hash_mode` | `int | None`; migración de strings heredados válidos | Estado RF/updates |
| `out_route_state` | `unknown / flood / known` | Distinguir ruta vacía conocida de ausencia |
| `out_path_hash_size_bytes` | Derivado 1/2/3 o `None` | DTO/API; no duplicar autoridad del modo |
| `position_valid`, fuente y fecha | Disponibilidad explícita, no inferida por valor cero | `NodeTelemetry`/DTO |
| `distance_m` | Derivado; sin persistir una distancia obsoleta | Helper JS o DTO calculado con posición local |
| `hops_source` y saltos observados | Fuente RX completa o ruta saliente conocida | DTO; mantener compatibilidad del campo legacy |

Proponer `@dataclass(frozen=True)` para `RouteObservation`: `hashes: tuple[str, ...]`, `count`, `hash_size_bytes`, `route_type`, `received_at`, `source`, `completeness` (`full_traversed / remaining_only / unknown`), `identity_trust`, `route_trust` y correlación de paquete cuando exista. Separar identidad aceptada de ruta observada/no autenticada. Identidad canónica por clave pública completa. Mantener Python 3.10.

`None` debe significar desconocido, no cero/directo. La fusión actual interpreta `None` como «no actualizar»: introducir explícitamente distinción entre campo omitido y campo a limpiar. Migración JSON aditiva: leer antiguos modos string; preservar datos válidos; registros heredados sin heard siguen desconocidos. No convertir timestamps remotos en recepción local.

### 2. Adquisición y procesamiento pasivos

1. **Normalizar al borde del adapter.** Separar `snapshot`, advert aceptado, path actualizado, mensaje y observación raw. Preservar flags, GPS, `last_advert` remoto, `out_path`, longitud y modo en `sync_all_contacts`, bootstrap, controller y handlers. Validar hashes/longitudes y sentinels según evento.
2. **Separar presencia de importación.** Corregir `discover_node`, `AdvertHandler`, bootstrap y controller para que un snapshot no avance `last_rx_at` ni `last_advert_heard_at`. Los pushes aceptados `ADVERTISEMENT/NEW_CONTACT` permiten registrar instante de llegada local; `NEW_CONTACT` debe distinguirse de `NEXT_CONTACT` de descarga. Mantener la procedencia si se recupera el reloj de recepción Companion, que puede estar desajustado respecto al host.
3. **Consumir `RX_LOG_DATA` sin inundar otras salidas.** Un handler específico procesa observaciones RF con las colas/límites existentes. Validar primero; correlacionar ADVERT con public key completa y aceptación de firmware. Para mensajes/ACK sin identidad inequívoca, no asignar al último contacto ni al primer hash coincidente. No reenviar automáticamente cada log a MQTT ni duplicar contadores de eventos ya procesados. Revisar además el filtrado de eventos internos de `RxEventRouter`.
4. **Guardar ruta RX observada.** Conservar ceros dentro de hashes, modo/ancho y orden. Para FLOOD guardar secuencia completa observada; para DIRECT guardar secuencia restante y saltos recorridos desconocidos. Si el último paquete no trae ruta recuperable, la métrica del último RX debe expresar ausencia; se puede mostrar aparte «última ruta conocida» con su fecha, sin presentarla como actual. La deduplicación de mensajes no debe borrar automáticamente la información de una recepción posterior por otra ruta.
5. **Actualizar ruta saliente independientemente.** En el evento SDK `PATH_UPDATE`, ejecutar `GET_CONTACT` por USB/TCP, salvo que se acredite que otro flujo refrescó ese contacto después del push; el evento sólo marca la caché SDK como dirty y `auto_update_contacts` es falso por defecto ([meshcore.py:71](../reference/meshcore_py/src/meshcore/meshcore.py#L71), [310](../reference/meshcore_py/src/meshcore/meshcore.py#L310)). Programar cualquier espera de respuesta fuera del callback del reader, mediante tareas gestionadas y serialización existentes, para evitar bloquear el mismo dispatcher que entrega la respuesta. Fusionar contactos antes de emitir UI. No invertir ciegamente el camino entrante.
6. **Caché advert opcional.** Sólo usar `GET_ADVERT_PATH` local cuando se haya resuelto el problema de bytes cero y pueda asociarse la respuesta con la petición y clave pública inequívoca. Es una lectura al Companion, sin paquete RF; no añadir sondeo periódico. Un miss conserva desconocido. No permite reconstruir el último camino de un paquete distinto del advert.
7. **Derivar métricas.** `hops` de un FLOOD completo = número de hashes observados; saltos de salida = longitud normalizada de ruta conocida, con etiqueta propia. No llamar «directo» al unknown ni interpretar el resto de DIRECT como total recorrido. El ancho mostrado pertenece a la ruta **saliente**, no al selector de la estación.

Haversine en un helper reutilizable: convertir grados a radianes, `a=sin²(Δlat/2)+cos(lat1)cos(lat2)sin²(Δlon/2)`, `d=2R atan2(sqrt(a),sqrt(1-a))`; acotar errores de redondeo de `a`. Usar radio medio terrestre documentado. Validar números finitos, latitud [-90,90], longitud [-180,180] y disponibilidad real. Aceptar ecuador y meridiano cero; no asumir que `(0,0)` de un snapshot sin flag GPS es una posición conocida. Origen: transceptor LOCAL, no centro del mapa o ubicación del navegador. Recalcular al cambiar GPS local o remoto; es distancia geográfica aproximada, no distancia recorrida por radio.

### 3. Persistencia y contratos REST/WebSocket

1. Serializar/deserializar campos nuevos mediante la persistencia atómica existente y conservar los timestamps de recepción al reiniciar.
2. Publicar un único snapshot final del nodo tras GPS, rutas y contadores; REST y WS deben devolver igual significado y tipos. Añadir versión/secuencia de actualización si hace falta impedir que un evento anterior reemplace estado más reciente; no ordenar recepción por el reloj remoto.
3. Mantener `/api/nodes` y eventos `contact_updated/contact_discovered` como fuente de tarjetas. Campos nuevos aditivos; normalización centralizada del tipo de evento. La conversión interna del modo de string a entero exige compatibilidad externa explícita: conservar temporalmente la representación legacy y exponer un campo numérico nuevo, o versionar/documentar el cambio tras revisar consumidores. No depender del envelope raw del sniffer para actualizar presencia.
4. Consumir paginación hasta completar `total_count`, sin cambiar unilateralmente límites del servidor. Acumular páginas antes del render/merge y conservar el `Map` compartido; coordinar con eventos concurrentes para no perder actualizaciones. Resolver GPS local desde estado canónico aunque no esté en la primera página.
5. No alterar roles: LOCAL no entra en contactos ni se duplica como vecino; REPEATER sólo en Nodos/analítica y administración, sin chat. SENSOR/ROOM mantienen su clasificación oficial. El diagnóstico de rutas no habilita DM a infraestructura.

### 4. UI y traducciones

Wireframe de detalle pasivo dentro de la tarjeta:

```text
Repeater Norte                              REPEATER
RSSI · SNR · batería                         Actividad RF: hace 20 s

Distancia                 2,4 km
Último anuncio recibido   hace 38 s          [fecha absoluta / fuente]
Ruta de entrada           a100 → b200 → c300  [2 bytes/hash]
Saltos                    3                 [último FLOOD completo]
Ruta de salida            8f → 12            [2 saltos de salida]
Hash de salida            1 byte/hash · 8 bits

[Detalles de rutas ▾]                        lectura pasiva
[Administrar] [Ping] [Traceroute RF]         acciones manuales existentes
```

El ejemplo es ilustrativo: todos los hashes de una misma ruta usan el mismo ancho, que puede diferir del ancho de la ruta saliente.

Implementación: bloque semántico `<dl>` con las seis métricas; dos columnas si hay espacio y una en móvil. «Detalles de rutas» muestra hashes completos, ancho, fecha, procedencia y estado de completitud, sin transmitir. Se puede abreviar sólo el resumen visual. Copiado y expansión accesibles por teclado, sin significado exclusivo por color; contraste y foco visibles en temas claro/oscuro. No sustituir rutas por batería/temperatura cuando lleguen esos datos.

Definir claves i18n para las seis etiquetas, fuentes y todos los estados: desconocido, sin GPS local/remoto, ruta restante, último FLOOD completo, flood/sin ruta conocida, hash ambiguo, no verificado y no aplicable a LOCAL. Usar `Intl.NumberFormat` y formatos de fecha/tiempo según idioma; texto de todos los estados, tooltips, botones y atributos accesibles traducido. Evitar concatenaciones que impidan pluralización. Reutilizar el ticker visual existente para edades; ningún timer de la UI debe consultar RF. El render inicial y el patch `updateNodeInDom` deben producir los mismos datos y traducciones.

### 5. Validación futura — propuesta, no ejecutada

| Escenario simulado | Resultado esperado |
|---|---|
| GPS conocido, ausente, ecuador, meridiano, antimeridiano y valores inválidos | Haversine correcto; disponibilidad explícita; invalidación y cambio GPS local recalculan todos los nodos |
| Contactos antiguos al iniciar/sincronizar; reloj remoto futuro o atrasado | Importación no rejuvenece presencia ni last advert heard |
| Advert aceptado, duplicado y falsificado | Sólo recepción aceptada y atribuible afecta estado confiable; conservar reloj remoto separado |
| Modos 0/1/2, `00` al principio/medio/final, buffer de 64 bytes | Hashes intactos, longitudes consistentes, ancho 8/16/24 bits |
| Truncación, modo 3, exceso de count×width y sentinels por contexto | Rechazo/unknown seguro; nunca 255 saltos ni corrupción silenciosa |
| FLOOD A→B→C; DIRECT por varios repetidores consumiendo camino; TRACE | FLOOD cuenta 3; DIRECT vacío no implica hop 0; TRACE usa decoder separado |
| Mismo origen por rutas A→B y D→E; hashes colisionados | Última observación según recepción local; no atribución por hash ambiguo; dedup de chat independiente |
| RX sin ruta después de RX con ruta; borrado explícito de ruta saliente | No mostrar ruta vieja como último RX; unknown, vacío conocido y flood diferenciados |
| SDK `PATH_UPDATE` con caché dirty/antigua; `GET_CONTACT`; `GET_ADVERT_PATH` miss/expulsión | Refresh acredita ruta nueva; actualiza sólo salida correspondiente; sin deadlock; miss no inventa heard/ruta |
| Persistencia JSON antiguo y nuevo; reinicio | Migración del modo string, round-trip y timestamps conservados sin inferir heard remoto |
| REST frente a WS tras GPS/ruta/contador | Snapshot final coherente y actualización de tarjeta sin recargar |
| Más de 100 nodos y eventos durante paginación | Directorio completo, LOCAL correcto y actualizaciones sin pérdida |
| ES/EN y demás idiomas configurados; móvil/desktop; temas | Todas las variantes traducidas, números/fechas locales, hashes legibles sin overflow, foco y contraste |
| LOCAL, REPEATER, CLIENT, ROOM y SENSOR | Invariantes de contactos/mensajería conservadas |
| Instrumentación de transmisiones, MQTT y tareas | Flujo pasivo no emite RF ni crea sondeo periódico o publicaciones nuevas |

Usar adaptador virtual, frames binarios de las revisiones identificadas, reloj controlable y fixtures temporales. Simular multiruta mediante entradas independientes y asincronía controlada; añadir capturas de hardware sólo en una tarea posterior autorizada. Las futuras suites de navegador deben levantar su propia estación virtual/puerto loopback, sin usar una instalación operativa. Ejecutar pytest, comprobaciones de tipos/lint y navegador sólo cuando se autorice esa fase; comunicar sus resultados por separado.

### 6. Orden de entrega y criterio de aceptación

1. **Modelo/codec:** tipos y migración compatibles, sentinels correctos y solución verificable a bytes cero; desconocido nunca convertido en directo.
2. **Pipeline/estado:** datos salientes conservados, recepción pasiva correlacionada, relojes separados, persistencia y snapshots REST/WS consistentes.
3. **UI/i18n:** seis métricas visibles o desconocido explícito, detalles pasivos, actualización incremental y paginación completa.
4. **Validación autorizada:** ejecutar escenarios anteriores en entorno aislado, corregir regresiones y registrar limitaciones de firmware/dispositivo. Un resultado sintético no acredita interoperabilidad con cualquier radio.

No introducir un nuevo historial ilimitado, TTL, intervalo de sondeo, umbral o limitador unilateral. Reutilizar límites existentes; cualquier política adicional debe acordarse antes de implementarla. No registrar esta propuesta como capacidad existente ni como ADR aceptado.

## Checklist de impacto LoRa del plan

1. **Airtime:** cero transmisiones RF nuevas en el flujo propuesto. Se reciben eventos existentes y, opcionalmente, se leen cachés locales Companion. Traceroute/ping/path discovery permanecen acciones manuales existentes, fuera de este cálculo.
2. **Spam/feedback:** no crear publicaciones MQTT, notificaciones o envíos a partir del log RX. Conservar guarda de origen propio, deduplicación y límites de colas existentes; separar el registro RF del evento de chat evita doble contabilización/feedback.
3. **Rearmado por guardar configuración:** no añadir scheduler RF ni timer periódico. Persistir recepción y observaciones con el mecanismo JSON existente; guardar configuración o reiniciar no convierte snapshots en nuevas recepciones ni dispara consultas por radio.

Si una futura ampliación requiere sondeo activo, RF automático, reintentos o nuevos intervalos, esta propuesta no los autoriza: evaluar airtime y acordar los parámetros siguiendo `AGENTS.md`.

## Límites de la evidencia

Auditoría estática del checkout y de fuentes oficiales locales, más contraste documental oficial. No demuestra interoperabilidad de una radio concreta, disponibilidad universal de pushes, precisión GPS, apariencia renderizada o resultados de pruebas. Los hallazgos y líneas pertenecen a la revisión indicada; las fases de implementación y validación siguen pendientes.
