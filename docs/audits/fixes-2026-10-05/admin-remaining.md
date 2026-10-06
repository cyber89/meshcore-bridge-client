# Correcciones de administración y correlación de ACK — 2026-10-05

Base de corrección: `776eed7` (primera entrega de la auditoría). Se conservan los informes/harness históricos de 2026-10-04: sus aserciones describen defectos antiguos, no son regresiones de comportamiento correcto.

## Alcance y verificación

Skills aplicadas: `meshcore-source-inspector`, `python-patterns-typing`, `bridge-test-runner` y `async-concurrency-engineering`. Referencias oficiales locales sólo leídas; no se actualizan SDK, firmware, radio, broker, datos operativos ni instaladores. Se usan SDK simulados, memoria, reloj sintético y directorios temporales de pytest.

Primera reproducción administrativa: **36 fallos y 3 controles aprobados**, 39 casos, en `tests/artifacts/admin-remaining-before.xml`. Tras los cambios iniciales: **39 aprobados**. Se amplían posteriormente con validación de batería, refresco completo/parcial, metadatos de voltaje histórico y fronteras de precisión. La suite focalizada ampliada de administración/privacidad/ACK/lifecycle/routers produjo **380 aprobados**, 42.60 segundos; evidencia `tests/artifacts/admin-remaining-final.xml`. RUNTIME-03 se reprodujo aparte: **7 fallos**, evidencia `tests/artifacts/ack-remaining-before.xml`; primera suite corregida ACK/core/routers: **101 aprobados**, 1.35 segundos, `tests/artifacts/ack-remaining-after2.xml`.

Mypy `--strict` en los diez archivos fuente de esta entrega: sin errores. Ruff sobre esos archivos y sus nuevas regresiones/fixtures: sin errores. Los informes globales finales del agente principal acreditan la integración posterior con otros cambios simultáneos; los conteos focalizados aquí corresponden a las ejecuciones citadas, sin atribuirse cobertura de hardware.

## Problemas corregidos, uno por uno

| ID | Réplica anterior | Corrección y resultado esperado |
|---|---|---|
| PI-01 | RTC remoto de 2026, tag del emisor de 2024: se mostraba 2024. | Leer los primeros cuatro bytes de `data`, no `tag`. Validar todo el hex y longitud mínima; datos ausentes/corruptos devuelven error y no modifican el registro. |
| PI-03 | `flags:true` se volvía 1; `mode:1.9` se volvía 1 antes de validar. | Preservar tipos originales en `AdminCommandHandler`; setters rechazan bool, fracciones y tipos no enteros antes del SDK. `max_hops` mantiene esa misma validación. |
| PI-04 | Lote `gps=0,bad,key=1`: escribía gps y devolvía error sin reconocerlo. | Prevalidar todas las variables antes de enviar. Si falla una confirmación posterior, responder `partial` y `applied.custom_vars` sólo con escrituras confirmadas, sin rollback por radio. |
| PI-05 | Despacho MSG_SENT sin respuestas: `status:ok`, 0/5. | Contar respuestas reales CLI y binarias por separado; `error` sin ninguna, `partial` con parte y `ok` sólo con todas las consultas disponibles confirmadas. Exponer `confirmed_count`, `requested_count` y `binary_responses`. |
| PI-06 | Refresco de CLIENT enviaba cinco comandos antes de la guarda de rol. | Rechazar el lote para roles conocidos distintos de REPEATER/ROUTER antes de contacto, login o envío. Quitar la asignación de rol REPEATER a partir de telemetría. Advert oficial conserva autoridad. |
| PI-09 | ERROR en get_time se presentaba como RTC del nodo usando reloj host. | Exigir respuesta confirmada y un timestamp entero del nodo; error/ausencia no muestra una hora inventada. Aceptar Event.payload y dict oficial, presentar UTC. |
| PI-10 | ACL local afirmaba PIN activo y ADMIN/OPERATOR sin evidencia. | Responder error explícito `unsupported:true`, código 422. Companion no ofrece ACL de repetidor; PIN BLE no acredita esos permisos. |
| PI-11 | `rx_delay=10` se etiquetaba como diez segundos. | Mostrar `Base RX: 10 (adimensional)`; escala wire /1000 y parámetro transmitido permanecen iguales. |
| PI-12 | Entrada `set tx abc` devolvía ok con advertencia textual. | Validación CLI devuelve status error y código 422. Incluye potencia/frecuencia/SF/BW/CR/PIN/coordenadas/radio/tuning, instrucciones incompletas y booleano de repeat inválido. No hay escritura ante entrada rechazada. |
| PI-13 | Frecuencia/BW con .0009: applied y cache contenían precisión no serializada. | SDK conserva su conversión oficial única `int(value*1000)`; tras confirmar se sincroniza/cachea su valor efectivo /1000. CLI muestra ese valor. Caso 512.002 demuestra que cuantizar el float y reenviarlo podría truncar dos veces; se evita esa doble conversión. |
| Batería remota | `get bat` se traducía a `get pwrmgt.bootmv`, voltaje al arrancar de ciertos firmwares. | Alias `bat`, `get_bat`, `get bat`, `battery` consultan `req_status_sync`; `bat` es mV actuales de RepeaterStats. Sin respuesta se devuelve error, nunca se sustituye por bootmv. |
| RUNTIME-03 | ACK de dos horas seguía entregando msg_id; 1000 entradas recientes superaban supuesto límite 200. | TTL acordado 3600s monotonic, máximo duro 200, consumo por `pop`, poda en cada registro/resolución y mantenimiento existente. Colisión y capacidad se notifican; no se reemplaza una correlación pendiente. |

## Batería remota y contrato del refresco

Firmware `reference/meshcore/examples/simple_repeater/MyMesh.cpp` asigna `stats.batt_milli_volts = board.getBattMilliVolts()`. El reader SDK entrega `bat` desde esa respuesta de estado. El voltaje actual se convierte por su unidad explícita: `voltage_v = bat / 1000`, incluyendo 0 y 100 mV, sin heurística por magnitud. Sólo se acepta un entero uint16, sin bool/string/negativos/sobredimensión. La estimación de porcentaje conserva el normalizador existente y se identifica como `battery_pct_source:voltage_estimate`; no es una medición del estado de carga electroquímico.

La respuesta añade `battery_source:repeater_status`, `battery_mv`, `voltage_v` y el porcentaje estimado; actualiza la observación de batería del registro. Un SDK sin esa consulta, un rechazo o un timeout produce error explícito y conserva observaciones anteriores. Puede requerirse login válido conforme al firmware; no se omite autenticación pedida por el usuario.

`CommonCLI.cpp` devuelve `getBootVoltage()` para `get pwrmgt.bootmv` sólo bajo `NRF52_POWER_MANAGEMENT`; otros builds responden unsupported. El comando explícito sigue pudiendo consultarse, pero su parser produce `boot_voltage_mv`, nunca voltaje actual ni porcentaje. El refresco consolidado elimina ese CLI redundante: ya utiliza `req_status_sync` para batería actual. Mantiene cuatro CLI (`ver`, `clock`, `get radio`, `get dutycycle`) más las consultas binarias existentes cuando el SDK las ofrece. No agrega una nueva solicitud ni reintenta tras fallo.

El conteo distingue respuestas observadas de una confirmación de despacho. Un MSG_SENT no aumenta `confirmed_count`. Las respuestas CLI que el parser reconoce como error tampoco lo aumentan. El contrato `ok` significa completitud de consultas disponibles del lote; no certifica exactitud física de sensores ni soporte que el SDK/firmware no ofrezca. Una respuesta de radio sigue representando preferencias guardadas, no una medición RF efectiva.

## RTC remoto: layout contrastado

El firmware BASIC escribe tag del solicitante y RTC remoto como dos campos uint32 little-endian consecutivos. El reader SDK extrae los cuatro bytes del tag, y entrega el resto en `data`. Se interpreta `data[0:4]`, no la representación C de un struct. No se añade packing, padding ni CRC propios: el transporte y framing Companion pertenecen al SDK oficial. Se acepta el RTC reportado sin imponer un rango arbitrario de fechas.

## ACK: estado, capacidad y entrega observable

El usuario acordó explícitamente capacidad **200** y TTL **3600 segundos** durante esta continuación. `register_pending_ack` devuelve una razón: `registered`, `invalid_ack`, `collision` o `capacity_exceeded`. Capacidad llena rechaza tracking del nuevo envío y conserva los pendientes existentes. La transmisión ya confirmada sigue `status:sent`; el resultado y publicación TX incluyen `delivery_tracking`, sin afirmar entrega ni provocar reenvío. Hay un warning observable cuando se rechaza capacidad o una colisión de identificador con otro request/target.

Una segunda inscripción del mismo ACK/request/target no extiende la vigencia. Registro y resolución podan siempre, incluso por debajo de 200. Resolución consume la entrada una sola vez. El TTL usa monotonic; el timestamp civil sigue disponible como metadato. El loop de mantenimiento existente (60s) elimina entradas sin tráfico, por lo que el almacenamiento puede conservarlas hasta su siguiente iteración pero la resolución siempre rechaza una entrada vencida. Stop vacía el estado pendiente.

El handler consulta la correlación local incluso si el payload trae un msg_id; ese dato no puede saltarse TTL o consumo. Una repetición no vuelve a emitir una entrega WebSocket asociada al request antiguo. ACKs no correlacionados conservan observabilidad MQTT de la recepción, con msg_id nulo, y no confirman mensajes de UI. Fuera de un bridge con tracker, se conserva la compatibilidad del handler independiente con IDs explícitos.

Como parte del límite de RX del agente principal, los broadcasts de ACK/presencia/traceroute ahora se esperan dentro del handler asíncrono; ya no crean tareas desacopladas que escapaban al pool de recepción. Esto mantiene el trabajo dentro del ownership y backpressure del ingreso RX.

La correlación sigue dependiendo de un ACK de cuatro bytes y de una respuesta SDK posterior al envío. Esta entrega no demuestra interoperabilidad en radio real, ni introduce almacenamiento de ACKs huérfanos para una posible llegada anterior al retorno de `send_message`. No equivale a autenticación criptográfica del emisor.

## Pasos para reproducir y comprobar

1. Revisar los casos de `tests/test_remaining_admin_audit.py`: RTC con tag distinto, ingreso inválido, lote custom inválido/parcial, refresco sin respuesta/parcial/completo, guarda CLIENT/ROOM/SENSOR, errores de CLI, precisión y batería.
2. Ejecutar sólo las regresiones nuevas con estado temporal: `.venv/Scripts/python.exe -m pytest tests/test_remaining_admin_audit.py tests/test_remaining_ack_audit.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/admin-ack-review-tmp`.
3. Revisar que los mocks no hayan sido invocados en los rechazos de validación/rol; comparar applied/cache con la conversión wire simulada del SDK en los casos válidos.
4. Ejecutar compatibilidad de administración/configuración y lifecycle/routers; confirmar que configuraciones privadas siguen redactadas en salidas MQTT públicas.
5. Ejecutar mypy strict y Ruff de fuentes/regresiones modificadas. La suite global integrada y navegador corresponden al informe de la entrega principal.

Se corrigieron expectativas históricas que perpetuaban el bug (`bat -> bootmv` y tuning en segundos), conservando comprobaciones de escritura, consulta SDK y compatibilidad. La prueba aislada del handler ACK ahora declara explícitamente que no hay bridge/tracker, en vez de inventarlo automáticamente mediante MagicMock. Un ensayo ampliado de precisión usó inicialmente 145 MHz, fuera del rango validado por el proyecto; se sustituyó por 512.002 MHz. Esos fallos de fixture se conservan en resultados intermedios y no se atribuyen a producción.

## Checklist de impacto LoRa

El normalizador de porcentaje presupone una celda con curva aproximada de voltaje; no acredita estado de carga de una fuente de 12V, baterías de otra química ni alimentación externa. La lectura fiable para esos dispositivos es `battery_mv`/`voltage_v` de la respuesta binaria. La estimación se etiqueta por separado; 0 y 100mV se conservan como voltaje explícito y no se interpretan como porcentaje crudo. No se cambió esa curva ni se configuró un límite de alimentación nuevo.

El argumento legado `RepeaterManager.transmit_callback` se conserva en la firma y como atributo inerte. Al suministrarlo emite `DeprecationWarning` que explica que no se invoca y que el envío corresponde al executor administrativo; una regresión comprueba que no dispara el callback. La documentación explícita y la advertencia evitan prometer una función inexistente sin romper consumidores existentes. No afecta al callback real de `TxRateLimiter`, que sigue operativo.

1. **Airtime:** batería usa una solicitud de estado existente bajo demanda; el refresco reduce de cinco a cuatro CLI adicionales. No hay aumento por número de nodos ni consulta periódica nueva. Precisión de set_radio conserva una escritura local Companion; no se modificó hardware durante QA.
2. **Spam/feedback:** no hay reintentos, login adicional, rollback remoto ni publicación que vuelva a transmitir. Persisten cooldown y waiters existentes. Capacidad ACK rechaza tracking con resultado observable, no reenvía el mensaje. El lote de rol inválido transmite cero paquetes.
3. **Timers:** no se arma ningún timer nuevo al guardar. Poda ACK reutiliza el mantenimiento existente; es estado de correlación, no un scheduler RF. TTL/capacidad usan valores acordados con el usuario. Ningún umbral RF se eligió unilateralmente.
