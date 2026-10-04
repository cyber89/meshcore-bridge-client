# Configuración local: guardado, confirmación y recarga

Fecha: 2026-10-04. Base examinada: `226f8aceb17bb35fb285dc8a2f6300bb05a0a577`.
Esta revisión resuelve el reporte de **Telemetría Periódica** y **Intervalo de
Telemetría (seg)** y amplía la comprobación a las demás rutas de guardado local.
No modifica la administración remota ni certifica hardware físico.

## Resultado y diferencia de funciones

El protocolo Companion del nodo local no permite configurar transmisiones
periódicas de telemetría ni su intervalo. El bridge tampoco tenía un scheduler
que consumiera ese valor. El formulario ofrecía una función inexistente: guardar
un número en RAM no configuraba el dispositivo. Ambos controles quedan
deshabilitados con explicación visible, y la API rechaza esas escrituras con
HTTP 422 antes de aplicar cualquier otro campo del lote.

Los modos Base, Ubicación y Ambiental sí son preferencias del firmware:
determinan quién puede solicitar telemetría. Se conservan editables y no se
confunden con una programación de envíos.

Además, las preferencias soportadas que recibían ACK podían volver a mostrar
valores antiguos: el SDK conserva SELF_INFO y sus setters no siempre actualizan
esa caché. El executor ahora sincroniza los snapshots después de una respuesta
válida y excluye refrescos concurrentes durante el guardado.

## Plan ejecutado y responsabilidades

1. Principal: delimitar el parámetro reportado, revisar contratos y coordinar
   propiedad de archivos, integración, comprobación de navegador y documento.
2. Agente protocolo: contrastar firmware, SDK, CLI y cliente de referencia;
   lectura exclusiva de `reference/`.
3. Agente backend: corregir confirmaciones, snapshots, baselines y capacidades;
   añadir regresiones REST con estado del dispositivo independiente de su caché.
4. Agente frontend: enviar únicamente campos editados, exigir confirmación por
   campo y conservar borradores ante errores y carreras de lectura/escritura.
5. Principal: incorporar textos ES/EN y aviso accesible, conciliar el terminal
   local, ejecutar pruebas aisladas y revisión estática, registrar evidencia y
   publicar exclusivamente los archivos de esta tarea.

Skills aplicadas: `contract-openapi-sync`, `python-patterns-typing`,
`web-browser-inspection`, `bridge-test-runner` y `meshcore-source-inspector`.
La autorización de comprobación del frontend continúa durante esta corrección;
no incluye una estación real, broker operativo ni transmisiones físicas.

## Problemas reproducidos y solución

| Problema | Reproducción / efecto anterior | Corrección |
| --- | --- | --- |
| Intervalos locales ficticios | POST con `telemetry_interval` o `advert_interval` devolvía éxito sin setter SDK ni persistencia de firmware. | Capacidades explícitas, controles indisponibles y rechazo 422 previo a cualquier escritura. |
| Otras escrituras sólo RAM | Propietario, altitud y límite de saltos aparentaban aplicarse. | Eliminar esos setters ficticios; rechazar campos y sus alias. Posición fija también se declara indisponible. |
| Caché antigua sobre un ACK | Cambiar un permiso devuelve `applied=2` y `config=1`; GET conserva el antiguo valor. | Sincronizar SELF_INFO público/privado y snapshot serial sólo después de confirmar. |
| Guardado de todo el formulario | Editar potencia enviaba también intervalos, valores por defecto y políticas no tocadas. | Payload con campos modificados; parámetros agrupados del SDK conservan sus baselines. |
| Baseline desconocido | Editar un flag o tuning podía sustituir compañeros desconocidos por cero/defaults. | Rechazar el lote antes de cualquier comando cuando falta un baseline necesario. |
| Éxito optimista | HTTP erróneo, `status=ok` sin confirmación o ACK incompleto limpiaba campos o mostraba éxito. | Comprobar HTTP, estado interno y `applied` de cada parámetro; nunca usar el payload como evidencia. |
| Respuesta parcial | Se borraban todos los cambios pendientes aunque sólo parte llegara al dispositivo. | Limpiar sólo campos confirmados y mantener el resto editable, con mensaje de fallo. |
| GET atrasado / edición durante POST | Una lectura anterior podía revertir el guardado; una respuesta podía borrar una nueva edición. | Revisiones y secuencia de lecturas; snapshot/versiones de cada edición. |
| Botón habilitado durante guardado | Una actualización de configuración podía rehabilitar el botón mientras seguía el POST. | Preservar estado de guardado y desconexión. |
| Indicador PIN desaparece | Una segunda redacción de `pin=0` oculto reemplazaba `has_pin=true` por falso. | Redacción idempotente; el valor secreto continúa oculto. |

Las escrituras por lotes no son transacciones atómicas de firmware: si un comando
posterior falla, los anteriores con ACK pueden haber quedado aplicados. La
respuesta parcial muestra ese hecho y la UI conserva únicamente lo pendiente.

## Contrato actual

- GET `/api/config` (alias `/api/node/config`) devuelve `data.capabilities` con
  `false` para `telemetry_interval`, `beacon_interval`, `advert_interval`,
  `hop_limit`, `owner_info`, `altitude` y `fixed_position`.
- Los valores históricos pueden seguir en la respuesta para compatibilidad;
  no son prueba de una preferencia activa. La UI limpia los intervalos y el
  terminal indica expresamente que no están soportados por Companion.
- POST `/api/config/radio` y `/api/config/identity` conservan sus rutas. La UI
  envía sólo modificaciones y consume `data.applied` / `data.config`.
- Solicitar un campo no soportado en un lote devuelve 422, `applied={}` y cero
  comandos de escritura, incluso si el lote incluía un nombre válido.
- Para cambios soportados, `applied` acredita respuesta válida del dispositivo.
  La sincronización de caché evita el retroceso visual; una consulta forzada
  permite obtener un SELF_INFO independiente.

## Fuentes y límites de la referencia

Firmware propio `d9296435`, SDK `c487efbe` y CLI `0856c723`, comprobados en sus
repositorios respectivos; sin actualizar ni escribir en las referencias.

- `reference/meshcore/examples/companion_radio/NodePrefs.h:5–7`: modos de
  permisos; `:127–128`: entradas de intervalos de anuncios comentadas.
- `reference/meshcore/examples/companion_radio/MyMesh.cpp:627–659`: los permisos
  se aplican al recibir solicitudes; `:1043–1083`: campos de SELF_INFO;
  `:1220–1230`: altitud futura sin aplicación; `:1443–1458`: flags, `savePrefs()`
  y respuesta OK.
- `reference/meshcore_py/src/meshcore/commands/device.py:117–130`:
  `set_other_params_from_infos` empaqueta permisos y políticas; `:36–43`:
  `set_coords` transmite altitud cero.
- `reference/meshcore_cli/src/meshcore_cli/meshcore_cli.py:2510–2545`: comandos
  locales de permisos de telemetría.
- El cliente `remote-terminal` disponible es de terceros, no la app móvil
  oficial: separa permisos (`SettingsRadioSection.tsx:331–338`) de recopilación
  periódica propia (`SettingsRadioAppSection.tsx:146–170`), y refresca SELF_INFO
  después de setters (`app/services/radio_commands.py:120–122`).

No se encontró checkout de la app móvil oficial. La administración remota de
repetidores usa CommonCLI y otro contrato: sus intervalos de anuncios tienen
unidades de minutos/horas. No deben trasladarse a estos controles locales en
segundos.

## Evidencia de verificación

Entorno: Windows, Python 3.12.14, pytest 9.1.1, Chromium headless mediante
Playwright y dependencias ya instaladas. Todos los fixtures usan archivos
temporales, radio virtual, MQTT mock y un puerto de loopback propio.

| Comprobación | Resultado |
| --- | --- |
| Backend histórico, selección de 19 regresiones nuevas | 17 fallos reproducidos, 2 aprobadas; sin errores de fixture en la ejecución válida. |
| JS aislado histórico / corregido | 2/18 antes; 18/18 después. |
| Backend: executor local, administración, REST, tipos y configuración local/remota | 117 aprobadas. |
| Cobertura de esa selección | 39% global de `src`; 72% de executor local. No equivale a cobertura de toda la aplicación. |
| Frontend: auditorías mantenidas y nuevas regresiones de navegador | 97 aprobadas; sin errores de consola ni recursos locales fallidos. |
| mypy strict | 60 archivos fuente sin incidencias. |
| Ruff | `src`, `tests`, `scripts` y reproductor de baseline sin incidencias. |
| Integridad documental y diff | Sin incidencias al revisar estructura y espacios. |

Los nueve casos nuevos de navegador comprueban controles periódicos
indisponibles, ausencia de POST sin cambios, guardado exclusivo del campo
editado y recarga de potencia, seis políticas y nombre. El dispositivo simulado
persiste en un diccionario independiente: un ACK no actualiza por sí solo el
snapshot SDK usado en la prueba.

Reproductores y recibos versionados: [audits/local-config-save-2026-10-04/](audits/local-config-save-2026-10-04/).
JUnit y cobertura completos en `tests/artifacts/local-config-*.xml` (ignorados en
Git). La primera integración detectó el error real de PIN; quedó corregido antes
de la aceptación final. El primer intento del reproductor histórico encontró
permisos del directorio temporal; la ejecución válida usa `--basetemp` dentro de
los artefactos aislados del proyecto.

## Pasos de aceptación en una instalación real

1. Actualizar el código y reiniciar el bridge con el procedimiento habitual de
   despliegue. Recargar la SPA para cargar el JavaScript nuevo.
2. Abrir Ajustes → Radio. Comprobar el aviso de intervalos no soportados; elegir
   un permiso de telemetría que el operador quiera cambiar.
3. Guardar y comprobar que el mensaje confirma el cambio. Consultar el nodo de
   forma explícita y recargar la página; el permiso debe conservarse.
4. Repetir con un cambio autorizado de nombre. Si falla la comunicación, la UI
   debe mostrar el error y mantener el borrador; no prometer aplicación.
5. Para parámetros de radio, realizar la aceptación durante mantenimiento y
   con valores elegidos por el operador; verificar compatibilidad de la malla.
6. Si se desea telemetría periódica del bridge, tratarla como funcionalidad
   nueva: definir destino, intervalo, permisos y persistencia, acordar airtime
   y cooldown antes de implementar un scheduler.

Estos pasos físicos quedan como aceptación del operador; no se han ejecutado en
la estación real. Firmware guarda preferencias antes de OK, sin necesidad de
un reinicio general. Su `MyMesh.h:168–171` no propaga el resultado booleano del
almacenamiento: ni un ACK ni los mocks garantizan detección de averías de flash.

## Checklist de impacto LoRa

1. **Airtime:** el parche no añade consultas RF, anuncios ni telemetría
   automática. Conserva escrituras Companion puntuales solicitadas al guardar;
   no incorpora timer ni multiplicación por nodos.
2. **Spam/feedback:** no hay nuevo flujo MQTT, reintento ni notificación
   automática; se conservan los mecanismos existentes. Las pruebas no
   transmiten por hardware.
3. **Rearmado de timers:** no se crea ni modifica scheduler de RF. Guardar un
   intervalo no soportado se rechaza antes de escribir. No se elige ningún
   intervalo nuevo ni se cambia un umbral de protección.
