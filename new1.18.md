# MeshCore 1.18.0 — investigación contrastada y actualización por capas

Investigación: 2026-10-15. Implementación ampliada: 2026-10-17, capacidades de capa2, diagnóstico manual de capa3, guarda de repetición ROOM y pausa manual0 de capa4. La compatibilidad integral sigue pendiente de los criterios de aceptación del [plan](docs/MESHCORE_1_18_UPGRADE_PLAN.md); este documento no es una certificación de interoperabilidad ni sustituye CONTEXT.md o la pila oficial.

Esta revisión reemplaza las conclusiones inexactas del borrador inicial. El equipo separó firmware/protocolo, backend y web/seguridad, y contrastó las afirmaciones con los tags oficiales y los consumidores reales de la aplicación. Los informes detallados están en [protocolo](docs/audits/2026-10-15-meshcore-1.18-protocol.md), [backend](docs/audits/2026-10-15-meshcore-1.18-backend.md) y [web](docs/audits/2026-10-15-meshcore-1.18-web.md). La [entrega conjunta](docs/audits/2026-10-15-meshcore-1.18-integration.md) registra cambios, QA y límites.

## 1. Versiones y autoridad de las fuentes

En este informe, «protocolo13/14» significa nivel de API Companion (`FIRMWARE_VER_CODE`), distinto de la versión del protocolo de paquetes RF.

| Componente | Estado comprobado | Consecuencia |
| --- | --- | --- |
| Firmware 1.17.1 | `d92964352441e53b93e8667b802e04f6e072b39e`; protocolo 13 | Checkout local de `reference/meshcore/`; no confundirlo con 1.18. |
| Firmware 1.18.0 | `81dbae592ffad40b4212bc0b37e82b38da08f4bc`; protocolo 14; tags companion/repeater/room-server | Objetos Git disponibles localmente, consultados sin cambiar `reference/`. |
| SDK de referencia | Checkout `v2.3.8`, `c487efbe187f4b000020afdfc0349c4cdf503c5a` | No representa el SDK instalado. |
| SDK fijado e instalado | `meshcore==2.3.15` | Ya contiene CLI local, respuesta29 y factory con recuperación DTR. |
| SDK 2.3.16 | `3ef9dfc06fe4646b87a451ac3458fd650b1a2901` | Añade `path_hash_mode` a `send_channel_data`; no es requisito universal de firmware1.18. |

Los tres [releases oficiales](https://github.com/meshcore-dev/MeshCore/releases/tag/companion-v1.18.0) comparten el commit1.18. [Repeater](https://github.com/meshcore-dev/MeshCore/releases/tag/repeater-v1.18.0) y [Room](https://github.com/meshcore-dev/MeshCore/releases/tag/room-server-v1.18.0) tienen publicaciones separadas. [PyPI2.3.16](https://pypi.org/project/meshcore/2.3.16/) acredita la disponibilidad del paquete. Las notas enlazan al blog oficial, que no pudo recuperarse durante la investigación del agente de protocolo; no se atribuye contenido no leído al anuncio. Se priorizaron serializadores y handlers del tag sobre prosa desactualizada.

## 2. Qué cambia realmente

| Afirmación del borrador | Rectificación contrastada | Impacto real |
| --- | --- | --- |
| CLI local66 y respuesta29 | Novedad confirmada en firmware1.18. | Registrar `66 -> 29`, nunca aceptar un OK genérico como respuesta CLI. |
| CLI idéntica a la de repetidores | Comparte preferencias, pero tiene dispatcher propio. | Mantener consola del bridge y separar comandos del firmware. |
| `CommonRadioPrefs` y configuración dinámica | Refactorización confirmada; muchos comandos ya existían en CommonCLI. | No asumir que cada parámetro es nuevo ni configurable en caliente. |
| Rango150–2500MHz nuevo | Ya admitido sintácticamente en1.17.1. Hay cambios de soporte LR1121/PA en1.18. | Identificar hardware/banda; el rango del parser no acredita capacidad física. |
| WiFi/TCP companion nuevo | Ya existía.1.18 reorganiza la interfaz, añade RP2040 y configuración persistente. | Reutilizar transporte `tcp://host:port` existente. |
| Puerto4000 predeterminado | El firmware oficial usa5000 salvo override del build; el adapter del bridge conserva fallback4000 si se omite. | Usar puerto explícito; no cambiar una conexión operativa automáticamente. |
| Comandos62/65 nuevos | Ya presentes en1.17.1. | No habilitar inyección raw ni túneles sólo por existir opcodes. |
| Validación de nombres nueva y universal | Los siete caracteres ya se prohibían en CommonCLI;1.18 centraliza el helper y lo usa en CLI companion. Opcode8 binario sigue copiando/truncando. | Separar reglas de nombres de nodo, canal y comandos; no endurecer el helper compartido de canales indiscriminadamente. |
| Binario espontáneo0x8C nuevo | Opcode previo;1.18 reenvía más respuestas no correlacionadas. | SDK y bridge ya conservan evento genérico; falta modelo tipado/correlación para ciertas aplicaciones. |
|0x8C incluye emisor | No incluye pubkey. | Nunca atribuirlo a un sensor por conjetura ni interpretar cualquier binario como LPP. |
| Scope0 wildcard | Confirmado en RegionMap. | Mejora interna del firmware; sin parche de retransmisión host. |
| ROOM `set repeat on` deprecado | Confirmado en dispatcher1.18. | El ejecutor ya lo bloquea en todos los ROOM por decisión del usuario, también con prefijos/lotes antes de efectos. No existe builder ROOM separado en la app. |
| ACK/multipart con delay directo | Confirmado en firmware. | No demuestra reducción de colisiones medida ni requiere reintentos host nuevos. |
| LPPReader sustituido totalmente | Se comparten helpers LPPData; lector y escritor permanecen. | No asumir mayor precisión del parser Python sin comparación de fixtures. |
| DTR/RTS invertidos en2.3.16 | Ya en2.3.15: un reintento con DTR invertido; RTS se conserva. | Bridge usa constructor directo, no hereda automáticamente ese camino de factory. |

Fuentes de implementación: [Companion1.18](https://github.com/meshcore-dev/MeshCore/blob/81dbae592ffad40b4212bc0b37e82b38da08f4bc/examples/companion_radio/MyMesh.cpp), [CommonRadioPrefs](https://github.com/meshcore-dev/MeshCore/blob/81dbae592ffad40b4212bc0b37e82b38da08f4bc/src/helpers/CommonRadioPrefs.cpp), [CommonCLI1.17.1](https://github.com/meshcore-dev/MeshCore/blob/d92964352441e53b93e8667b802e04f6e072b39e/src/helpers/CommonCLI.cpp), [diferencia SDK2.3.15–2.3.16](https://github.com/meshcore-dev/meshcore_py/compare/v2.3.15...v2.3.16). El informe de protocolo contiene enlaces adicionales fijados por SHA.

## 3. Contratos y riesgos que el borrador no resolvía

### CLI local

Comando: `0x42 | texto`, longitud total mínima3. Respuesta: `0x1D | texto` sin NUL transmitido. No hay endian multibyte en ese payload; la longitud externa Companion es uint16 LE. Son buffers serializados, no structs de memoria con padding ni CRC propios nuevos.

El buffer `cli_command[80]` es de rescue USB, no del comando66. `cmd_frame` admite el frame Companion de176 bytes más terminador; eso no significa que cualquier comando de175 bytes sea seguro. `reply_buf[166]` incluye NUL, por lo que166 no es un máximo demostrado de texto útil. La cadena160 del borrador no procede de un límite uniforme del handler.

Existe un riesgo estático concreto en `set radio`: `strcpy` del sufijo a `tmp[132]`. Se requiere gramática y longitud por comando, no un terminal arbitrario limitado genéricamente a160. La primera pantalla debe permitir sólo lecturas conocidas, con `fw ver >=14`, método SDK disponible y lock de comandos. Un CLI_REPLY puede contener `Error` o `Unknown command`: recibir opcode29 no equivale a que la operación semántica haya tenido éxito.

El prefijo opcional `AA|` se refleja al detectar longitud>4 y barra en posición2 después de espacios iniciales. No reemplaza la serialización de transacciones ni debe aceptarse como forma de saltarse validación o redacción.

### Nombres y secretos

`AdvertDataParser::isValidName` rechaza `[ ] \ : , ? *`, pero no valida por sí mismo31bytes UTF-8 ni controles. El límite de31 procede de buffers de32 incluyendo terminador. El helper de la aplicación también sirve a canales: aplicar la blacklist CLI de nodo a todos sus consumidores rompería usos binarios válidos.

`wifi.pwd` es una clave real del firmware. Debe ocultarse junto a `wifi.password` en comandos, mappings y terminal/historial. `get wifi.pwd` devuelve texto sin etiqueta; sólo una redacción regex sobre ese texto no protege la respuesta. Además, SDK `run_cli_command` registra el comando en DEBUG. Antes de habilitar configuración WiFi desde web hay que clasificar sensibilidad desde la petición, devolver respuesta privada/sin secreto y cubrir logging SDK/transporte. No consultar contraseñas en la UI.

### Binarios y sensores

`0x8C | reservado_u8 | tag_4bytes | data...`; no hay clave de emisor. Mantener origen desconocido si no existe una asociación verificable. No generar consultas RF para deducirlo automáticamente.

1.18 añade suscripciones sensor0x08/0x09: tag, timeout, deltas LPP y permisos ACL. El push agrega timestamp antes de LPP. Exige persistir asociación tag/pública/tipo/expiración y definir renovación. La emisión depende de muestreo, deltas y suscriptores: no es coste RF cero aunque el bridge sólo reciba pushes. Umbrales, intervalos y límites siguen sujetos a decisión explícita del usuario.

### Datagramas y CLI remota

Salida binaria canal: `0x3E | canal | packed_path_len | ruta | tipo_u16_LE | datos`. El SDK2.3.16 limita datos a163 bytes; firmware1.18 valida165. La documentación Companion del mismo tag conserva una explicación anterior de167/165: no copiarla sin verificar el handler. El SDK divide la ruta truncando: el bridge deberá exigir modo0/1/2, longitud divisible entre modo+1, hops y frame total válidos. Es trabajo posterior, sin envío por defecto.

CLI remota explícita usa texto tipo3 y permiso de contacto0x10. Es distinto de CLI_DATA1 usada por administración existente. No activar permisos de contactos ni convertir chat en administración automáticamente.

### Mensajes largos: comprobación adicional (2026-10-17)

El firmware oficial1.18 y el SDK instalado2.3.15 no fragmentan automáticamente
un texto de chat largo. El SDK codifica el texto completo en UTF-8 y emite un
comando por envío. En firmware, `MAX_TEXT_LEN` es160 **bytes**, no160 caracteres
([definición](https://github.com/meshcore-dev/MeshCore/blob/81dbae592ffad40b4212bc0b37e82b38da08f4bc/src/helpers/BaseChatMesh.h#L8)).
`composeMsgPacket` rechaza el exceso en DM; los intentos extendidos reservan
otros2 bytes. `sendGroupMessage` descuenta el prefijo `nombre: ` y recorta el
texto que no cabe, pudiendo responder éxito después del recorte
([implementación](https://github.com/meshcore-dev/MeshCore/blob/81dbae592ffad40b4212bc0b37e82b38da08f4bc/src/helpers/BaseChatMesh.cpp#L451)).

Por ello se conserva la validación por bytes y el margen de prefijo del bridge.
Quitarla sin segmentación explícita puede perder texto. El soporte de mensajes
largos observado en otro cliente podría proceder de ese cliente; eso requiere
verificar su implementación concreta. Una futura segmentación en nuestra web
debe conservar UTF-8, orden, ACK e historial por fragmento y pasar por la cola y
airtime existentes. Multiplica los paquetes y necesita decisiones de tráfico
antes de habilitarla; no se incorpora en esta entrega.

## 4. Cambios de la entrega inicial (2026-10-15)

- `CommandType.RUN_CLI_COMMAND=66` y respuesta terminal raw `66->{29}`; conserva la propiedad de respuesta, pushes, errores y timeout sin reintento.
- Parser administrativo de radio admite frecuencias de tres y cuatro dígitos. No cambia parámetros RF ni bandas configuradas.
- Redacción de `wifi.pwd`/`wifi.password`, incluidos prefijos CLI y exclusión del historial web; se conserva el bloqueo de otras credenciales.
- Regresiones contra métodos reales en `tests/test_meshcore_1_18_companion.py`, `tests/test_meshcore_1_18_radio.py` y `tests/test_meshcore_1_18_redaction.py`. Los ejemplos originales usaban `db=None` y builders inexistentes: fueron retirados.
- QA detectó una carrera real en los repositorios SQLite de autenticación y estación: archivos WAL/SHM podían desaparecer entre comprobar existencia y ajustar permisos. Se tolera sólo esa desaparición efímera; se conservan errores de DB principal, permisos y enlaces simbólicos. Las pruebas y las fixtures antiguas corregidas se detallan en el ledger.
- La auditoría móvil encontró el menú por debajo de su fondo oscuro y un panel remoto más alto que la pantalla horizontal. Se corrigieron con el token de superposición de Bootstrap y un límite de altura del panel, con pruebas sobre el menú real. El estado offline conserva contraste y añade borde discontinuo. No se rediseñó la interfaz.

La reparación de respuesta raw no añade una nueva API web CLI: el proxy ya transmitía el comando. No se añadió polling, suscripción, setter, automatización MQTT ni cambio de datos persistidos. Se mantienen los pins SDK de producción y el checkout de referencias. Los resultados de QA y las reparaciones adicionales justificadas se registran en el informe de integración.

### 4.1 Capacidades y diagnóstico manual (2026-10-16)

La siguiente entrega incorpora capacidades por sesión observadas desde DEVICE_INFO
y lecturas locales exactas `get radio`/`get freq`. El ámbito `firmware` del endpoint
administrativo existente conserva la consola del bridge y no publica MQTT. El
panel web muestra protocolo, versiones, modelo y transporte; permite lectura
manual con soporte confirmado. Invalida sesiones/resultados obsoletos y bloquea
CLI tras timeout, cancelación o transporte incierto hasta reconexión.

Ambos getters leen preferencias de firmware, que pueden estar pendientes de
reinicio. No se añaden setters, tráfico RF, timers ni consultas de secretos.
La selección TCP en web y las capas avanzadas siguen pendientes. Evidencia,
contratos y límites: [ledger de capas2/3](docs/audits/2026-10-16-meshcore-1.18-layers-2-3.md).

### 4.2 Administración manual (2026-10-17)

El usuario eligió cero pausa mínima entre órdenes de administración manual.
Se aplica a infraestructura REPEATER/ROOM inequívoca desde HTTP autenticado;
los handlers MQTT/internos conservan su default y la persistencia de timestamps.
No se añaden comandos automáticos, fragmentación de chat ni límites de trama
nuevos. El [gate dirigido](docs/audits/2026-10-17-meshcore-1.18-manual-admin.md)
registra273 pruebas aprobadas sobre el cambio posterior a las capas2/3.

## 5. Uso desde la web y orden de actualización

El [plan por capas](docs/MESHCORE_1_18_UPGRADE_PLAN.md) especifica archivos, contratos, dependencias, aceptación y reversión. Prioridad: capacidades visibles y diagnóstico local manual; después preferencias avanzadas y WiFi con seguridad y reinicio observado; más adelante sensores y datagramas con decisiones de airtime.

Una versión1.18 no hace compatibles todas las placas con WiFi,2.4GHz o todos los parámetros. El objetivo verificable será la matriz de funciones acordadas para companion1.18/protocolo14 con SDK elegido, manteniendo las rutas existentes de1.17.1. No prometer compatibilidad del100% antes de pasar QA y una comprobación de interoperabilidad física autorizada por separado.
