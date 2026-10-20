# Preferencias remotas CAD y RX gain

Fecha: 2026-10-17. Base: `9e40b4e`. Siguiente paso de capa4 del
[plan MeshCore1.18](../plans/MESHCORE_1_18_UPGRADE_PLAN.md).

## Plan de implementación y alcance acordado

Se extiende a infraestructura remota el alcance ya elegido por el usuario:
CAD on/off y RX gain sólo lectura. Se reutilizan las acciones administrativas
unitarias autenticadas, su correlación por tag/emisor y la pausa manual HTTP
de0s previamente acordada. No se añaden umbrales o intervalos.

Los botones sólo envían a petición explícita. La web exige lectura CAD antes de
guardar y la invalida tras cada intento o cambio de destino. El guardado requiere
una nueva lectura manual para contrastar la preferencia; ni `OK` ni el getter
acreditan aplicación física. No se amplían los lotes de configuración o telemetría.

Se exige destino canónico inequívoco REPEATER/ROOM, excluyendo LOCAL, CLIENT,
SENSOR, desconocidos y metadatos contradictorios. Los parámetros se validan antes
de alta de contacto SDK, login, registro de cooldown o primer comando. El bloqueo
de repeat on para ROOM permanece independiente de CAD.

## Checklist de impacto en malla previo a implementación

1. **Airtime:** cada acción es un comando administrativo RF y su posible
   respuesta; si requiere autenticación, se añade login/respuesta. Cada salto
   multiplica el coste. No se da una cifra de milisegundos sin medir SF/BW/ruta.
   Sólo se consulta el destino seleccionado; sin descubrimiento por nodo ni
   polling. Una pulsación no encadena readback, ping, traceroute o advert.
2. **Spam/feedback:** se reutiliza gateway/lock SDK, correlación, exclusión por
   destino y política manual HTTP de pausa0 elegida anteriormente. Sin nuevos
   reintentos, topics MQTT, suscripciones o callbacks de envío. Las publicaciones
   administrativas de estado ya existentes se conservan; no afirmar que esta
   ruta utiliza la cola de chat TxRateLimiter. Los flujos internos conservan sus
   cooldowns existentes y no se autorizan chat a repetidores ni loopback local.
3. **Guardado/reinicio:** CAD persiste en el firmware remoto; guardar no crea ni
   rearma timers, ni borra timestamps/cooldowns o airtime de SQLite. El bridge
   sigue guardando los timestamps administrativos existentes. No se reenvía la
   preferencia al arrancar, reconectar WS o guardar otra configuración. La web
   limpia sus observaciones al cerrar/cambiar destino.

## Implementación y contrato

El constructor compartido reconoce `get_cad`/`get cad`, `get_rx_gain`/
`get radio.rxgain` y `set_cad` con exactamente `params:{enabled:boolean}`.
El preformateado acepta sólo `set cad on`/`set cad off`; no permite sufijos ni
coerciones. Setters RX gain y parámetros en lecturas se rechazan antes de efectos.
La configuración por lotes conserva su contrato y no incluye estas acciones.

POST `/api/repeater/remote/action` conserva autenticación, CSRF, API key y Origin.
No se crean rutas o eventos WS. El controlador existente devuelve `data`:

| Resultado | Proyección |
| --- | --- |
| GET confirmado | `status:"ok"`, `preferences:{cad:boolean}` o `{rx_gain:boolean}`, `preferences_source:"saved_preferences"`, `hardware_verified:false`. |
| SET confirmado por `OK` exacto | `status:"ok"`, `saved_preferences:{cad:boolean}`, `acknowledged:true`, `hardware_verified:false`. |
| Sin respuesta | `status:"dispatched"`; sin preferencias, sin ACK ni reintento automático. |
| Respuesta inesperada/error | Fallo semántico, sin reflejar texto arbitrario del firmware. |

El destino devuelto es la clave canónica completa. `applied`, `telemetry` y
`pending_reboot` no representan estas preferencias. Los errores de entrada/rol
son422; la política HTTP de errores administrativos/dispatched existente conserva
el resto de códigos. El endpoint no exige lectura previa: esa guarda pertenece
a la interfaz. Un API client autenticado comparte la política manual de pausa0.

La resolución congela identidad/ruta SDK antes de cualquier await; las claves de
cooldown y topics siguen usando el identificador histórico de la solicitud.
Las contradicciones entre rol del registro y advert SDK se rechazan. Al dar de
alta un ROOM ausente del contacto SDK se conserva tipo3; no se convierte a
repetidor2 ni se añade a la libreta de contactos de chat. La correlación existente
exige tag y emisor y serializa por destino.

La SPA usa un formulario separado del lote RF. Sólo conserva observaciones para
el destino/modal autenticado actual, descarta respuestas tardías al cerrar/cambiar
modal o sesión WS/autenticación y pide otra lectura tras guardar. No actualiza el
resumen de radio ni NodeRegistry con CAD/RX gain. Los textos ES/EN y datos se
renderizan como texto. Los errores no copian la contraseña ni un eco arbitrario
a la nueva respuesta tipada o publicación MQTT de estado existente.

## Fuentes verificadas

Objetos Git locales del repositorio propio `reference/meshcore`, sin fetch,
checkout o modificación:

- MeshCore1.18 `81dbae592ffad40b4212bc0b37e82b38da08f4bc`:
  `src/helpers/CommonRadioPrefs.cpp:112–135` define getters CAD/RX gain y setters.
  RX gain escribe la preferencia antes de comprobar soporte; se mantiene sólo
  lectura. `src/helpers/CommonCLI.cpp:184–185` delega y guarda prefs dirty.
- ROOM del mismo commit: `examples/simple_room_server/MyMesh.cpp:471,989`
  entrega CLI remota a CommonCLI. La guarda repeat on es independiente.
- MeshCore1.17.1 `d92964352441e53b93e8667b802e04f6e072b39e`:
  CommonCLI CAD en470/818 y RX gain en535/845; ROOM delega en471/987.
  Los getters no son capacidades exclusivas de1.18. No se deduce soporte físico
  por versión, nombre o una respuesta escalar almacenada.

## Verificación y pendientes

Regresiones backend y navegador escritas sin ejecución. Las suites siguen
suspendidas porque el usuario no ha solicitado su ejecución. No se atribuye TDD
rojo/verde ni aceptación funcional, visual o física. Se revisan controles,
correlación, destinos, redacción y conservación de timestamps por inspección.
El tipo advert también se congela antes de cargar estado, para que un cambio
posterior de metadatos no convierta un ROOM en repetidor al crear contacto SDK.

Comprobaciones estáticas satisfactorias:

- Ruff sobre las tres fuentes Python modificadas y dos módulos de regresiones.
- `mypy --strict src`:87 archivos sin incidencias.
- Build y `build_frontend.cjs --check`:31 assets y gzip coherentes.
- Auditoría léxica i18n:1602 claves por idioma, cero findings/candidatos sin
  traducir; no acredita layout, traducción de toda salida dinámica o accesibilidad.
- Validador documental:105 archivos, cero incidencias.

No se conecta a hardware real ni se usa una instalación operativa como fixture.
El selector de conexión y las preferencias locales también mantienen su QA
pendiente. WiFi y otros controles por hardware, modelo durable de sensores y
aceptación final permanecen en el plan.

Reversión: revertir el commit propio. No hay migración de datos del bridge; la
reversión no restaura un CAD ya guardado en hardware remoto. Antes de usar el
control, conservar su lectura anterior para poder restituirla manualmente.
