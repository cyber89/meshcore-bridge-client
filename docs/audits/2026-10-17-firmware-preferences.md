# Preferencias locales CAD y diagnóstico RX/hash

Fecha: 2026-10-17. Base: `0a79b7b`. Entrega de capa4 del
[plan MeshCore1.18](../MESHCORE_1_18_UPGRADE_PLAN.md).

## Decisión del usuario y alcance

El usuario eligió incluir ajustes manuales de radio y concretó después:
**CAD on/off; RX gain sólo lectura**. El hash mantiene su editor binario existente
con valores0/1/2. No se seleccionan valores por defecto, intervalos, reintentos,
presupuestos o umbrales nuevos. La implementación sólo administra la preferencia
local; no amplía los setters remotos ni modifica parámetros de una radio real.

La allowlist de consultas añade `get cad`, `get radio.rxgain` y
`get path.hash.mode` a `get radio`/`get freq`. Todas son consultas locales manuales
de preferencias, sin sondeo al abrir pestañas, reconectar WS o guardar formularios.
Se conserva la separación del CLI histórico del bridge y del ámbito remoto.

## Evidencia oficial

Inspección de objetos Git locales, sin modificar `reference/` ni hacer fetch:
tag anotado `companion-v1.18.0`, objeto `7d6d255104eadbfccd85ceae4ccbc14133946f7e`,
resuelto a `81dbae592ffad40b4212bc0b37e82b38da08f4bc`.

| Fuente en ese commit | Evidencia |
| --- | --- |
| `src/helpers/CommonRadioPrefs.cpp:112–119` | `get cad` devuelve `> on/off`; `set cad on/off` modifica preferencia y responde `OK`. |
| `src/helpers/CommonRadioPrefs.cpp:122–135` | RX getter informa preferencia; setter llama `setRxGain` antes del driver, incluso si devuelve `Error: unsupported`. Por eso no se habilita su escritura. |
| `src/helpers/CommonRadioPrefs.cpp:175–188` | Getter hash informa entero; la ruta binaria existente se conserva para escribir0/1/2 sin duplicar CLI permisiva. |
| `examples/companion_radio/NodePrefs.h:97–117` | Getters leen campos de preferencias. |
| `examples/companion_radio/MyMesh.cpp:2089–2091` | Dispatcher puede guardar prefs previamente dirty aun tras un getter. No prometer ausencia absoluta de escrituras internas. |
| `src/Dispatcher.cpp:66–71` | Aplica CAD durante su ciclo existente de calibración; el bridge no añade timer ni exige reinicio. |
| `src/Dispatcher.h:68`, `src/helpers/radiolib/RadioLibWrappers.h:63` | La implementación CAD depende del driver; el método base puede no hacer nada. Un `OK` no certifica capacidad física. |

Las rutas se conservan como referencias a archivos del commit, no como enlaces
al checkout que puedan acreditar otra revisión. Se inspeccionaron handlers y
getters; no se compiló firmware ni se realizó interoperabilidad física.

## Contrato y estado observado

Se amplía POST `/api/admin` sin nuevas rutas o WS. Sesión, CSRF, API key y Origin
mantienen la política existente. Escritura acepta exclusivamente las claves:

```json
{"action":"set_preference","scope":"firmware","preference":"cad","value":true}
```

Sólo booleano JSON; no aceptar1/0, strings, comandos, prefijos, params, password
o destino. Getters no aceptan campos de escritura ambiguos. Adaptador y ejecutor
revalidan CAD y su tipo; se usa una sola llamada SDK con la sesión y lock
existentes. `run_firmware_cli` sigue rechazando cualquier setter textual.

Éxito200 exige `OK` semántico y devuelve en `result`: `status:"ok"`,
`scope:"firmware"`, `action:"set_preference"`, `preference:"cad"`, booleano `value`,
`acknowledged:true` y `hardware_verified:false`. Entrada inválida422, rechazo400,
indisponibilidad/timeout503; no reflejar valores o errores privados del firmware.
El bloqueo conservador tras timeout/cancelación/error de E/S se comparte entre
getters y escrituras hasta una nueva conexión. No reintentar por otra vía.

`capabilities.firmware_cli.writable_preferences` contiene `cad` sólo con capacidad
CLI observada. Es capacidad de escritura de preferencias, no identificación del
chip ni comprobación de CAD físico. `session_generation` cambia con la sesión
del adaptador y forma parte de la firma web: una reconexión entre muestras con
idéntica identidad/versión invalida la lectura anterior aunque no llegue un
estado desconectado a la SPA. La SPA exige una lectura `get cad` válida y
vigente en su sesión antes de habilitar Guardar. Tras cualquier intento invalida
esa observación y pide otra consulta manual; no hace readback automático. La API
autenticada puede solicitar la escritura directamente: la lectura previa es una
guarda de interfaz, no una precondición adicional del endpoint.

## Checklist de impacto en malla

1. **Airtime:** una consulta o escritura local por acción manual, cero paquetes
   RF al ejecutarla. CAD cambia la decisión de acceso al canal en transmisiones
   posteriores; no hay barrido por nodo ni nuevas transmisiones para identificar
   hardware o verificar la aplicación física.
2. **Spam/feedback:** sin nuevos publicadores MQTT, notificaciones automáticas,
   reintentos o cadena de consultas. Se conserva el evento genérico de auditoría
   HTTP ya existente, sin comandos o respuestas privadas nuevos en historial.
3. **Persistencia/timers:** el firmware guarda CAD; no se crea scheduler, no se
   modifica el ciclo firmware existente y no se resetean timestamps, cooldowns
   o presupuesto airtime del bridge al guardar. Valores on/off elegidos por el
   usuario; no hay intervalo adicional que decidir.

## Verificación y pendientes

Regresiones nuevas de adaptador, administración y navegador escritas sin
ejecución; se actualizan expectativas de capacidades y añade un caso HTTP de
sesión/CSRF/Origin. AGENTS.md exige solicitud explícita de pruebas: esta entrega
no acredita TDD rojo/verde ni aceptación funcional, visual o en hardware.

Comprobaciones estáticas ejecutadas con salida satisfactoria:

- Ruff sobre las cinco fuentes Python modificadas y los cinco módulos de tests
  escritos/actualizados en esta entrega.
- `mypy --strict src`:87 archivos sin incidencias.
- Build y `build_frontend.cjs --check`:31 assets y gzip coherentes.
- Auditoría léxica i18n:1589 claves por idioma, cero findings o candidatos sin
  traducir; las expresiones dinámicas siguen necesitando revisión humana.
- Validador documental:104 archivos, cero incidencias.

El selector Serial/TCP de la entrega anterior también conserva QA pendiente.
El alcance remoto por hardware, WiFi y sensores continúa pendiente en el plan.

Reversión: revertir únicamente el commit de esta entrega. No migra datos del
bridge. Revertir código no restaura una preferencia ya guardada en una radio;
si se usó el control, el operador debe restituir su valor anterior manualmente.
