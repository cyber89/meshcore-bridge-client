# Auditoría por capas: protocolo, administración, sensores, MQTT y despliegue

Fecha de trabajo: 2026-10-04. Base auditada: `c9b2d3ce4c1776f2d0603f57481df2395d84ea2e`. La auditoría no modifica producción ni referencias. Se reproducen **13 casos defectuosos actuales** mediante un harness aislado; estos casos no forman parte de la colección automática de pytest.

## Evidencia y reproducción

Ejecutar desde la raíz del proyecto:

```powershell
.venv/Scripts/python.exe tests/audit_layer_protocol_2026_10_04.py
.venv/Scripts/python.exe -m ruff check tests/audit_layer_protocol_2026_10_04.py
```

Resultado observado: `reproduced: 13`, exit 0; Ruff: `All checks passed!`. Exit 0 significa que el harness reprodujo los defectos esperados, **no que el código productivo haya pasado estas expectativas funcionales**. El harness falla si un defecto deja de reproducirse. La evidencia completa de entradas, salidas, inventario y métricas está en [protocol-integration.json](protocol-integration.json); el ejecutable es [audit_layer_protocol_2026_10_04.py](../../../tests/audit_layer_protocol_2026_10_04.py).

Se usan claves y PIN sintéticos, SDK/MQTT simulados, directorio temporal y memoria. Se inhibe la carga `.env` antes de importar el proyecto. No se abre radio, broker, HTTP, servicio, configuración operativa ni instalador. Los tiempos de espera/transporte del lote remoto se sustituyen por mocks; el despacho, validación y construcción del resultado son reales. Las réplicas administrativas usan el `AdminCommandHandler` real que consume MQTT, pero no acreditan transporte MQTT extremo a extremo.

Referencias Git propias verificadas con `Get-Item -Force .../.git`, para evitar atribuir el HEAD padre:

| Fuente de autoridad | Revisión local contrastada | Evidencia relevante |
|---|---|---|
| Firmware `reference/meshcore` | `d92964352441e53b93e8667b802e04f6e072b39e` | Companion serializa tuning y parámetros RF; MyMesh repetidor responde reloj; sensores oficiales emiten corriente, potencia y altitud. |
| SDK `reference/meshcore_py` | `c487efbe187f4b000020afdfc0349c4cdf503c5a` | `reader.py` separa tag de datos binarios; `commands/binary.py::req_basic_sync` devuelve ese payload; `commands/device.py::set_radio` trunca a enteros. |
| CLI `reference/meshcore_cli` | `0856c723cdea3438811c62c190bbec3059e2dc48` | Contexto de comandos oficiales; no se trata como autoridad de firmware distinta. |

No se consultó upstream ni se actualizaron paquetes. Las revisiones acreditan la comparación con las copias locales, no su actualidad global.

## Hallazgos reproducidos

P1: exposición de credenciales que requiere atención prioritaria. P2: funcionamiento incorrecto, falsos éxitos o incoherencia de contrato. P3: deuda de diseño o presentación sin fallo crítico demostrado.

### PI-01 · P2 · El reloj remoto lee el tag del solicitante

- Código: [repeater_executor.py:1080](../../../src/admin/repeater_executor.py#L1080).
- Réplica: `req_clock` recibe tag LE del emisor `1704067200` (2024-01-01) y `data` empezando por RTC remoto `1791072000` (2026-10-04).
- Esperado: `00:00 - 04/10/2026 UTC`. Observado: `00:00 - 01/01/2024 UTC`, tanto en la respuesta como en `NodeRegistry.clock`.
- Causa: se prefiere `data['tag']` a `data['data'][:8]`. El firmware `examples/simple_repeater/MyMesh.cpp:184` copia timestamp del solicitante en bytes 0..3 y RTC remoto en 4..7; el reader SDK `reader.py:832` extrae los primeros cuatro bytes como tag y entrega el resto como data. `req_basic_sync` devuelve esa estructura sin interpretarla.
- Solución propuesta: validar data hex y longitud; interpretar sus primeros cuatro bytes LE como RTC remoto. El tag sólo sirve para correlación. Conservar hora desconocida si faltan bytes; no sustituirla por la hora del solicitante.

### PI-02 · P1 · La publicación MQTT de configuración revela el PIN BLE

- Código: [admin_handler.py:371](../../../src/admin_handler.py#L371), [cli_command_executor.py:125](../../../src/admin/cli_command_executor.py#L125), [local_config_executor.py:134](../../../src/admin/local_config_executor.py#L134).
- Réplica: cache local sintética `pin=654321`, acción `get_config`; inspeccionar el `publish_safe` simulado.
- Esperado: PIN redactado, manteniendo `has_pin`. Observado: `config.pin=654321` en resultado del handler y en JSON publicado a admin/status.
- Causa: `get_local_config()` conserva el dato privado para uso interno; esos dos caminos publican la estructura sin `redact_sensitive_dict`. La redacción del endpoint REST no protege esta salida MQTT. La lectura actual DEVICE_INFO incorpora `ble_pin`, por lo que el campo puede existir en funcionamiento real.
- Solución propuesta: redacción en el límite único de salida pública del handler/CLI, conservando la representación privada sólo dentro del dominio. Agregar regresiones para get_config y todos los comandos CLI, además de REST/WebSocket. El PIN de evidencia es ficticio.

### PI-03 · P2 · El ingreso administrativo convierte entradas inválidas en válidas

- Código: [admin_handler.py:415](../../../src/admin_handler.py#L415), [admin_handler.py:423](../../../src/admin_handler.py#L423).
- Réplica: `set_autoadd_config` con `flags:true`; `set_path_hash_mode` con `mode:1.9`.
- Esperado: 422 y cero escrituras. Observado: status ok, SDK recibe flags `1` y modo `1`.
- Causa: `int()` se ejecuta antes de las validaciones estrictas del executor y pierde el tipo original/fracción. Hay contradicción entre los contratos REST endurecidos y el ingreso compartido de MQTT/terminal.
- Solución propuesta: validar tipos originales y enteros finitos antes de convertir; aplicar el mismo validador a todas las entradas, sin depender del controlador HTTP.

### PI-04 · P2 · Lote de variables custom deja cambios parciales sin reportarlos

- Código: [admin_handler.py:394](../../../src/admin_handler.py#L394).
- Réplica: `set_custom_vars` con `{"gps":"0","bad,key":"1"}`.
- Esperado: rechazo del lote antes de cualquier escritura, o respuesta partial con valores confirmados. Observado: primer SDK write `gps=0`, cache modificada, respuesta error 422 sin `applied`.
- Causa: esta acción valida cada entrada durante el bucle; la prevalidación completa de `set_local_config.custom_vars` no cubre el alias independiente `set_custom_vars`.
- Solución propuesta: prevalidar el mapa completo antes de enviar; si posteriormente falla una confirmación real, devolver partial y los parámetros ya confirmados. No intentar rollback RF automático.

### PI-05 · P2 · La consulta consolidada anuncia éxito sin ninguna respuesta

- Código: [repeater_executor.py:862](../../../src/admin/repeater_executor.py#L862).
- Réplica: `refresh_telemetry`, transport mock devuelve MSG_SENT, las cinco esperas devuelven None y no hay datos binarios.
- Esperado: error/timeout, conservando los datos anteriores como datos históricos. Observado: status ok, responses y telemetry vacíos, mensaje `0/5 respuestas`.
- Causa: resultado final status ok incondicional; se contabiliza despacho como éxito de operación aun sin observación remota.
- Solución propuesta: definir error sin respuestas, partial si falta parte de las consultas y ok únicamente según el contrato explícito del lote; conservar pruebas de despacho separadas de datos recibidos. No añadir reintentos ni aumentar tráfico como respuesta al fallo.

### PI-06 · P2 · El lote de administración se envía a CLIENT antes de la guarda de rol

- Código: [repeater_executor.py:186](../../../src/admin/repeater_executor.py#L186), [repeater_executor.py:199](../../../src/admin/repeater_executor.py#L199), [repeater_executor.py:819](../../../src/admin/repeater_executor.py#L819).
- Réplica: registro remoto role CLIENT conocido; pedir `refresh_telemetry`.
- Esperado: rechazo de CLI de repetidor y cero despachos. Observado: cinco `send_cmd` y status ok sin respuestas.
- Causa: el branch de lote antecede a `if is_client_only`. Además, la actualización del lote fija role REPEATER si acumula telemetría; ese cambio de clasificación es un riesgo observado en código, pero no fue producido por la réplica sin respuestas.
- Solución propuesta: mover la validación de capacidades/rol antes de cualquier acción de repetidor y no deducir rol a partir de una consulta de estado. Mantener la clasificación oficial del advert y definir explícitamente qué solicitudes binarias permiten SENSOR/ROOM/CLIENT.

### PI-07 · P2 · Se ignoran unidades explícitas y la cadena false se convierte en true

- Código: [sensor_decoder.py:402](../../../src/sensor_decoder.py#L402), [sensor_decoder.py:434](../../../src/sensor_decoder.py#L434).
- Réplica: `extract_telemetry_fields({"solar_mv":100,"fixed_position":"false"})`.
- Esperado: solar_v 0.1 y fixed_position false. Observado: solar_v 100.0 y fixed_position true.
- Causa: magnitud `>100` sustituye la unidad de la clave; `bool("false")` es true.
- Solución propuesta: conversiones separadas por clave de unidad explícita y conversión booleana estricta reutilizada; decidir cómo manejar formatos antiguos ambiguos sin confundirse con campos tipados.

### PI-08 · P2 · Un tipo LPP oficial elimina las lecturas posteriores

- Código: [sensor_decoder.py:19](../../../src/sensor_decoder.py#L19), [sensor_decoder.py:204](../../../src/sensor_decoder.py#L204).
- Réplica raw: hex `01750064026700fa`: canal 1, corriente tipo 117, valor 0.100 A; canal 2, temperatura 25 C.
- Esperado: ambas lecturas. Observado: un registro unknown tipo 117; summary vacío; la temperatura posterior desaparece.
- Causa: no hay tamaño/decoder para corriente, genérico, potencia, altitud y otros tipos oficiales; se abandona toda la trama al primer tipo desconocido. El firmware los emite en `EnvironmentSensorManager.cpp:367`, `:384`, `:395`, `:409`, y el SDK los enumera en `lpp_json_encoder.py`.
- Solución propuesta: tabla de tipos/tamaños y conversiones oficiales, con signedness y escalas contrastados. Sólo detenerse ante un tipo cuyo tamaño realmente se desconoce. La réplica acredita el decoder raw; el SDK entrega otras rutas con LPP ya decodificado, que requieren pruebas propias para cada nuevo campo y no deben declararse igualmente afectadas sin evidencia.

### PI-09 · P2 · El comando local clock inventa una lectura tras rechazo del firmware

- Código: [cli_command_executor.py:449](../../../src/admin/cli_command_executor.py#L449).
- Réplica: SDK get_time devuelve evento ERROR.
- Esperado: reloj desconocido/no confirmado y status error. Observado: status ok, `Hora del Nodo` con timestamp del host.
- Causa: inicialización con hora del host seguida de `except: pass`, presentada como lectura del dispositivo.
- Solución propuesta: conservar el fallo de consulta; si se muestra hora del host, identificarla explícitamente como dato del host y no como RTC del nodo.

### PI-10 · P2 · La ACL local afirma autenticación y permisos inexistentes

- Código: [cli_command_executor.py:223](../../../src/admin/cli_command_executor.py#L223).
- Réplica: nodo local sin PIN (`has_pin:false`), acción acl.
- Esperado: capacidad real del Companion o estado no disponible. Observado: `Autenticación por PIN activa | Permisos: ADMIN / OPERATOR`, sin consulta ni evidencia.
- Causa: cadena fija. El PIN BLE de Companion y la ACL de repetidores son contratos distintos.
- Solución propuesta: quitar el estado inventado y exponer datos del mecanismo que realmente corresponda al nodo; informar unsupported cuando no exista equivalente Companion.

### PI-11 · P2 · El terminal vuelve a etiquetar rx_delay como segundos

- Código: [cli_command_executor.py:171](../../../src/admin/cli_command_executor.py#L171).
- Réplica: cfg rx_delay=10, comando tuning; resultado `Retardo RX: 10s`.
- Esperado: factor/base adimensional. El firmware Companion `MyMesh.cpp:269` calcula retardo mediante `((base ** (0.85-score))-1) * airtime`; `:1432` convierte el entero wire dividido por 1000 en ese factor.
- Causa: texto heredado incoherente con la vista corregida de configuración y el contrato binario actual.
- Solución propuesta: etiquetar base/factor; diferenciar un retardo medido si se dispone de él. No cambiar los bytes tuning, cuya escala /1000 está alineada con el firmware.

### PI-12 · P2 · Entrada CLI inválida conserva status ok

- Código: [cli_command_executor.py:956](../../../src/admin/cli_command_executor.py#L956).
- Réplica: `set tx abc`.
- Esperado: status error/422, cero escrituras. Observado: status ok con texto de advertencia `Valor de potencia inválido`.
- Causa: los except ValueError internos sólo modifican result; el envelope heredado sigue ok. Otros parámetros e instrucciones incompletas siguen el mismo patrón, pendiente de parametrizar exhaustivamente en la corrección.
- Solución propuesta: error estructurado uniforme para validación CLI y uso incorrecto; evitar que consumidores MQTT/UI tengan que inferir éxito buscando palabras en el texto.

### PI-13 · P2 · Radio local confirma más precisión de la que transmite

- Código: [local_config_executor.py:850](../../../src/admin/local_config_executor.py#L850), [local_config_executor.py:906](../../../src/admin/local_config_executor.py#L906); SDK oficial `commands/device.py:73`.
- Réplica: frecuencia 915.0009 MHz y BW 250.0009 kHz, SDK simulado aplica la conversión oficial `int(value * 1000)`.
- Esperado: applied/cache coinciden con 915.0 MHz y 250.0 kHz serializados, o el ingreso rechaza precisión no representable. Observado: status ok y applied contiene los valores .0009 originales.
- Causa: el puente sincroniza el SDK/cache desde el valor solicitado; el SDK trunca al entero wire. Una lectura real posterior puede devolver valores diferentes sin que el nodo haya rechazado la escritura.
- Solución propuesta: cuantizar primero con la regla oficial y sincronizar el valor efectivo, o validar precisión. Agregar réplicas con límites y flotantes próximos a una frontera de conversión; no cambiar frecuencia de hardware real para esta auditoría.

## Riesgos y contradicciones estáticas pendientes de réplica

| ID | Prioridad | Evidencia | Riesgo / trabajo propuesto | Estado |
|---|---|---|---|---|
| PI-S01 | P2 | `install.sh:88-92` y `:104` | --dev oculta fallos pip/playwright con `|| true`; anuncia bandit aunque el runner QA actual sólo ejecuta pytest/mypy/ruff/docs. Propagar fallos de instalación y mostrar sólo checks ejecutados. | Lectura; no se ejecuta el instalador ni se simula una instalación completa. |
| PI-S02 | P2 | `install.ps1:61` | La presencia del directorio paho se usa como acreditación de todas las dependencias. Un venv parcial con paho pero sin meshcore/serial/dotenv se anuncia listo y puede fallar al arrancar. Comprobar cada dependencia/import/version mediante el intérprete seleccionado. | Condición de código comprobada, entorno parcial no ejecutado con instalador. |
| PI-S03 | P2 | `install.sh:124,138-139` | --update detiene servicio, elimina src y después copia; no acredita nueva copia completa ni guarda copia de retorno antes de reemplazar. Fallo de copia deja instalación detenida/parcial. Usar staging verificado y sustitución/rollback explícito conservando datos. | Riesgo de fallo; no se elimina ni copia ninguna instalación. La guarda cuando origen coincide con instalación sí existe y no se reporta como ausente. |
| PI-S04 | P2 | `meshcore-bridge.service:8,18` | Servicio root y KillMode=process reducen aislamiento y pueden dejar hijos ante shutdown defectuoso. Revisar usuario dedicado, grupos serie, permisos de datos y modo de terminación según necesidad real. | Configuración observada; no hay explotación ni proceso huérfano demostrado. |
| PI-S05 | P2 | `mqtt_client.py::MQTTConfig/start` | No hay ruta configurada de TLS/validación de certificado. Para broker remoto debe definirse transporte y credenciales adecuados. | Ausencia de capacidad en esta clase; no se afirma exposición de una instalación específica. |
| PI-S06 | P3 | `mqtt_dispatcher.py:48-72` | Límite de tareas comprobado antes de `call_soon_threadsafe(schedule)`; llamadas directas desde otro hilo pueden validar el mismo conteo antes de crear tareas. Paho normal ya agenda callback al loop, por lo que esa ruta habitual no reproduce la carrera descrita. | Hipótesis de la interfaz thread-safe; sin réplica de carga ni conclusión de DoS. |
| PI-S07 | P3 | `repeater_manager.py:44-48` | Mapas cooldown sólo monotonic/RAM; pierden protección tras reiniciar proceso. No se acreditó que guardar configuración recree el manager; por tanto no se declara ese bug. Definir persistencia si debe sobrevivir al proceso. | Riesgo de política/continuidad, sin timer nuevo ni cambio de intervalos. |

## Clases, métodos y eficiencia

El inventario AST del JSON comprende **15 archivos Python, 38 clases, 295 funciones/métodos y 8133 líneas**. Incluye cada nombre, línea y longitud, además de conteo `branch_nodes`. Este conteo suma If/For/While/ExceptHandler/IfExp incluyendo nodos anidados; **no es complejidad ciclomática certificada** ni benchmark de tiempo/memoria. Optimizar todas las clases no puede demostrarse sólo con una suite verde o una búsqueda estática.

| Clase / función de frontera | Evidencia de riesgo de mantenibilidad | Propuesta |
|---|---|---|
| RepeaterAdminExecutor._execute_batch_config | 281 líneas, 64 nodos de rama; alias, capacidades, validación, compilación, envío y resultados en una función. | Catálogo tipado de parámetros y operaciones; mantener dispatch y confirmación como contrato independiente. |
| LocalConfigExecutor._prevalidate_local_params | 189 líneas, 61 nodos; validadores separados del ingreso directo de otras acciones. | Validadores compartidos entre HTTP/MQTT/CLI; modelo de solicitud con tipos originales. |
| RepeaterAdminExecutor._try_execute_binary_or_anon | 182 líneas, 38 nodos; shape/parser/registry/publicación manual por opcode. | Adaptadores de resultado por solicitud oficial y mapa de dispatch; pruebas de layout y correlación antes de refactor. |
| RepeaterAdminExecutor._execute_batch_telemetry_query | 179 líneas, 42 nodos; dependencias y resultado sin contrato de completitud. | Separar observaciones de despacho y resumen parcial; derivar unidad/semántica del comando. |
| RepeaterManager | 1094 líneas; combina cooldown, builders, getters, heurísticas telemetry y autenticación. | Separar parser contextual tipado, política de cooldown y compilador de comandos, sin introducir RF/timers. |
| CliCommandExecutor | 1035 líneas, 54 funciones incluidas funciones locales; cadena fija/heurística y resultados de SDK mezclados. | Conservar dispatch O(1), trasladar presentación a una capa y distinguir unavailable/cache/live. |
| Sensor decoder | 672 líneas; raw y JSON SDK no comparten una tabla de tipos/unidades. | Registro de tipos LPP oficial, conversión común de lecturas y fuente/unidad explícita. |
| TargetResolver | 111 líneas; resolución exacta y ambigüedad dentro de contactos enumerables. | Diseño acotado; para proveedores sólo helper el no poder demostrar unicidad debe quedar en contrato. No hay justificación medida para sustituirlo. |
| Protocol types | Frozen dataclasses/Enums; wire raw distinguido del Companion; CRC explícito y estructura íntegra. | Conservar independencia de layouts. No atribuir raw a RF oficial ni usar CRC como autenticación. |
| MQTT | Callback thread-safe y límite de payload; shutdown implementa join acotado. | Medir bursts y shutdown con broker virtual para cambios futuros; no declarar rendimiento por arquitectura. |

## Código en desuso, compatibilidad y redundancia

Búsquedas `rg` en src/tests/scripts y contexto de exports/callbacks impiden clasificar automáticamente métodos sin llamada textual como basura:

- `RepeaterManager.transmit_callback` se guarda en constructor (`:28,36`) y no se consume dentro de esa clase. Candidato a retirar del contrato tras buscar consumidores externos; no es el `TxRateLimiter.transmit_callback`, que sí se ejecuta y no debe eliminarse.
- `AsyncBridgeMQTTClient.publish_safe(ttl_seconds)` acepta el argumento (`mqtt_client.py:170`) y nunca lo usa. No hay consumidor interno encontrado. Es contrato engañoso si un consumidor externo cree que caduca publicaciones; deprecarlo o implementar su semántica explícita.
- `parse_telemetry_from_sdk` (`protocol_types.py:377`) sigue usado en `scripts/verify_all_components.py:30,126`. Nombre confuso para status binario, pero no código muerto.
- `FrameHeader.opcode` sigue usado por RxEventRouter y tests; `_DEPRECATED_ALIASES` emite warnings y tiene regresiones de compatibilidad. No son candidatos a borrado inmediato.
- `_send_pre_login` y `_send_login_fallback` sí están llamados en el executor; no son funciones huérfanas.
- Los adapters CLI `_cli_*_wrapper` están registrados por dispatch map, aunque no existan otras llamadas directas. Quitarlos por heurística eliminaría comandos.
- `LocalConfigExecutor.clear_device_stats` y `CliCommandExecutor._cli_clear_stats` duplican reseteo de cache/counters; son deuda real de duplicación, no operaciones demostradas de reset de estadísticas físicas. Unificar nombre y alcance al corregir.
- La normalización telemetría de `RepeaterManager` y `sensor_decoder` duplica unidades, campos y alias; PI-07/PI-08 evidencian el coste de contratos separados. Propuesta: lectura canónica tipada antes de presentar/publicar, con parsers fuente-específicos y sin convertir aproximaciones en hechos medidos.

## Alcance revisado y límites

Inventario Python detallado: src/admin/{__init__,sdk_commands,local_config_executor,repeater_executor,traceroute_executor,cli_command_executor}.py; src/admin_handler.py; src/repeater_manager.py; src/protocol_types.py; src/sensor_decoder.py; src/target_resolver.py; src/mqtt_client.py; src/mqtt_dispatcher.py; config.py; src/__main__.py. Fronteras adicionales leídas: meshcore_bridge.py, RxEventRouter telemetría, TxRateLimiter manejo de cancelación, NodeRegistry registro/update, requirements.txt, requirements-dev.txt, pyproject.toml, install.ps1, install.sh, meshcore-bridge.service, scripts/run_quality_checks.py; referencias oficiales citadas arriba. El inventario de todas las funciones no significa que cada combinación de entradas se haya ejecutado.

No se hicieron cambios de producción, pruebas RF, instalación, benchmarks ni carga real. No se propone un intervalo o umbral nuevo; cualquier corrección que produzca radio/timers debe mantener el checklist RF y límites acordados. Los hallazgos de c9b2d3c corregidos en informes anteriores no se vuelven a contar; aquí se describen rutas/contratos activos reproducidos que permanecen abiertos.

## Revisión complementaria de bordes: TCP Companion, preflight y estación virtual

Esta revisión adicional mantiene separados los **13 casos del harness principal** y **dos réplicas complementarias del simulador**. No se añadió código de producción ni se ejecutó la suite otra vez. Se leyeron `src/tcp_companion_server.py`, `src/preflight.py` y las fronteras/lifecycle/formatos de `src/virtual_mesh_adapter.py`; no se pretende certificar todas sus combinaciones de entradas.

### TCP Companion: contratos y ciclo de vida

- `start/stop`: servidor asyncio, ownership de tareas clientes, conjuntos active/pending, cierre de writers y cancelación con esperas acotadas. `finally` de cada cliente limpia ambos conjuntos y la tarea. No se observó una fuga confirmada mediante esta lectura.
- Admission: máximo de clientes incluye autenticaciones pendientes y se revalida antes de activar; allowlist IP y token opcional por línea `TOKEN:...`, con timeout de lectura de 5 segundos. Estas políticas se leen directamente desde `os.environ`, a diferencia de valores normalizados de config.py. La comparación de token usa igualdad normal; no se ensayó ataque de timing.
- Wire: `<`/`>` y longitud uint16 LE, máximo 300 bytes, recuperación de SOF, rechazo de sobredimensión, comandos vacíos ignorados. No es framing raw AA/55 ni RF. Las respuestas `<0x80` se entregan únicamente al propietario de transacción; pushes `>=0x80` se difunden.
- Concurrencia: lock por transacción porque Companion no trae request ID; captura de response_owner y señal response_received impiden añadir error si ya llegó una respuesta. El bridge enruta chat por rate limiter y los otros opcodes por adaptador. La verificación del opcode/semántica completa reside también en el adaptador, no sólo en este servidor.
- Backpressure: límite write buffer 65536 y drain de 2 segundos; un push recorre clientes de forma secuencial. La suma de esperas puede afectar latencia con varios clientes lentos: **hipótesis para medir con clientes virtuales**, no defecto de rendimiento demostrado. No se levantó un listener ni se usó el puerto operativo.

### Preflight: qué acredita y qué no

Se leyó el archivo completo. `run_all_async` mueve las consultas síncronas a `asyncio.to_thread`; el core también ejecuta `run_all` en thread. MQTT prueba sólo un connect TCP IPv4; no valida sesión MQTT, autenticación, TLS ni que el proceso sea realmente un broker. Serial AUTO expresa detección pendiente; las cadenas COM se consideran existentes sin abrir el dispositivo, y las rutas existentes no acreditan permisos ni interoperabilidad. TCP remoto consulta conectividad con timeout y conserva fallo como aviso. El bind de Companion acredita disponibilidad puntual del puerto con IPv4, no garantiza que siga libre cuando el servicio arranque.

Observaciones estáticas: la ruta de bind no usa context manager/finally y `sock.close()` sólo aparece después del bind exitoso; un bind fallido deja liberación al ciclo de vida del objeto, **sin fuga de recursos demostrada**. La parsificación `tcp://host:port` con split por primer ':' no maneja literal IPv6 entre corchetes. No se ejecutó preflight contra red, serial o broker de operador y no se reporta fallo de conectividad como defecto del producto.

### Estación virtual: alcance de equivalencia

La conexión arranca loop de escena y emite adverts; el echo crea tareas registradas y disconnect cancela/gather todas las tareas, evita cancelarse a sí misma y vacía el conjunto. La réplica sólo marca is_connected en memoria y **no invoca connect**, por lo que no inicia escena periódica. Se verificó `remaining_tasks=0` después de desconectar.

Se revisaron los comandos mock, almacenamiento de nodos/canales, set/get, validación de mensajes, raw Companion, LPP generado, escena y callback. Su docstring de raw declara un subconjunto y devuelve ERROR para opcodes no implementados; esa limitación es válida y no debe convertirse en supuesto de interoperabilidad completa. Sin embargo, el SDK virtual y raw Companion mantienen lecturas separadas: SELF_INFO raw tiene nombre/posición/radio fijos (`:655-676`), mientras los setters SDK actualizan mc.self_info. **Contradicción estática adicional pendiente de réplica de integración**: la misma estación puede mostrar snapshots diferentes según cliente. Debe compartir un estado de dispositivo o documentar separación deliberada antes de usarla como oráculo QA.

### PI-C01 · P2 · Alias de canal virtual evita la validación de rango

Código: [virtual_mesh_adapter.py:558](../../../src/virtual_mesh_adapter.py#L558) y [virtual_mesh_adapter.py:577](../../../src/virtual_mesh_adapter.py#L577). Entrada `send_message('audit',target='channel_999',channel_idx=0)`. Esperado: ERROR y ninguna tarea echo. Observado: `status:'ok',channel:999,delivered:false`. Se valida el argumento channel_idx inicial, y después se sobrescribe desde target sin validar de nuevo. Solución propuesta: resolver destino/canal primero, validar una sola representación canónica y no aceptar índices que excedan capacidad. Este hallazgo es del simulador; no demuestra que el adaptador físico permita canal 999.

### PI-C02 · P2 · set_time virtual confirma una hora que get_time no conserva

Código: [virtual_mesh_adapter.py:55](../../../src/virtual_mesh_adapter.py#L55) y [virtual_mesh_adapter.py:63](../../../src/virtual_mesh_adapter.py#L63). Entrada set_time(1704067200); respuesta `status:'ok',time:1704067200`. Lectura inmediata devuelve timestamp host, observado `1791167000`, sin relación con el ajuste. Causa: setter no almacena reloj; getter usa time.time; raw CMD_GET_DEVICE_TIME también usa reloj host (`:723`). Solución propuesta: modelar RTC virtual con base epoch y monotonic de ajuste y usarlo en todos los getters/lecturas raw. No hay que modificar reloj del sistema operativo.

Reproducción mínima complementaria (Python por stdin, módulos cargados con dotenv inhibido, sin radio/red/servicio):

```powershell
@'
import asyncio
import json
from unittest.mock import patch
with patch('dotenv.load_dotenv', return_value=False):
    from src.virtual_mesh_adapter import VirtualMeshAdapter
async def audit():
    adapter = VirtualMeshAdapter()
    adapter.is_connected = True
    try:
        channel = await adapter.send_message('audit', target='channel_999', channel_idx=0)
        clock_set = await adapter.mc.commands.set_time(1704067200)
        clock_read = await adapter.mc.commands.get_time()
        print(json.dumps({'channel': channel, 'clock_set': clock_set, 'clock_read': clock_read}))
    finally:
        await adapter.disconnect()
        print('remaining_tasks', len(adapter._background_tasks))
asyncio.run(audit())
'@ | .venv/Scripts/python.exe -
```

Resultado de la reproducción: exit 0, canal 999 aceptado, hora set/get distinta, tareas restantes 0. El timestamp leído depende del momento de ejecutar; la desigualdad con 1704067200 es el comportamiento observado. Estos casos no se incluyen en el JSON de 13 casos del harness principal; su evidencia/pasos quedan completos en esta sección.
