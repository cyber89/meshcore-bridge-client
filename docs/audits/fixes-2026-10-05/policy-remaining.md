# PI-S06 y PI-S07 — admisión MQTT y continuidad de cooldowns

Fecha: 2026-10-05. Se corrigen los riesgos del anexo de [la auditoría de protocolo](../layers-2026-10-04/protocol-integration.md), sin modificar esa evidencia histórica. Skills: `async-concurrency-engineering`, `python-patterns-typing`, `bridge-test-runner`.

## PI-S06: admisión antes de publicar callbacks entre hilos

La auditoría original distinguía una hipótesis de la ruta thread-safe de la ruta normal de Paho; no demostraba entonces un DoS. Ahora se reproduce con un hilo externo que entrega cien entradas mientras el loop propietario no puede ejecutarlas. Con límite de fixture tres, la implementación anterior retenía **100 tareas**: todas comprobaban el tamaño del conjunto antes de que los callbacks añadieran tareas. El caso de regresión bloquea deliberadamente el loop sólo para hacer determinista la prueba; producción conserva el event loop no bloqueante.

Corrección: reservar un token bajo `threading.Lock` antes de `call_soon_threadsafe`. El presupuesto comprende callbacks aún pendientes y tareas admitidas, contando también tareas externas que ya participaban en la protección anterior, sin contar dos veces las propias. Se conserva el fallback configurado existente `MAX_MQTT_INBOUND_TASKS=50`; no se añade un límite operativo distinto.

Los callbacks crean tareas dentro del loop propietario. El token se libera al finalizar, cancelar, fallar la inscripción de ownership o no poder utilizar un loop cerrado. Un callback cuyo token fue invalidado al cerrar no inicia trabajo. El dispatcher conserva sus handles y tareas; `close()` cierra admisión, cancela handles pendientes y cancela/espera únicamente sus tareas. El lifecycle del bridge llama start/close; no se cancela asyncio globalmente. Una ráfaga fuera de capacidad produce un warning observable y no ejecuta comandos descartados, ni reintenta publicaciones.

Además, las publicaciones finales de TX vía MQTT conservan `delivery_tracking` del resultado real, de modo que `capacity_exceeded` del tracker de ACK no desaparece detrás del envelope del dispatcher.

## PI-S07: timestamps persistidos, sin IO síncrono ni timers nuevos

Réplicas: registrar un comando a epoch 1000, reiniciar manager a epoch 1002 con otro monotonic y comprobar un intervalo ya existente de cinco segundos. Antes se permitía transmitir inmediatamente; después quedan **tres segundos**. Se comprueban también cooldowns existentes de ping, traceroute, vecinos y telemetría consolidada. No se afirma que guardar configuración recreara el manager: eso no estaba demostrado en la auditoría.

El bridge instala el manager con `DATA_DIR/repeater_cooldowns.json`. El constructor no lee/escribe disco ni arranca tareas. Un manager independiente puede omitir `storage_path` para trabajar exclusivamente en memoria, conservando compatibilidad de herramientas y pruebas. `load_state()` lee mediante `asyncio.to_thread` antes de revisar cooldowns, tanto al arrancar el bridge como en los ejecutores remoto/traceroute.

El archivo schema 1 contiene mapas de epochs UTC para `command`, `telemetry`, `ping`, `traceroute` y `neighbours`. No se escriben passwords, PIN, payloads o mensajes. Se validan schema, categorías, claves y epochs finitos no negativos; un archivo inválido no se ignora para habilitar radio. La carga conserva observaciones más recientes de este proceso y reconstruye cada timestamp monotonic a partir del tiempo civil transcurrido.

Las APIs sync `record_*` sólo modifican memoria y una generación. Los executors esperan `flush_state()` después de reservar un disparo y **antes del paquete correspondiente**, incluida autenticación asociada al comando unitario y solicitudes binarias. Una falla de escritura impide ese envío. El timestamp de la reserva puede consumir el cooldown aunque el envío siguiente falle; es la política conservadora necesaria para no habilitar ráfagas tras un fallo/reinicio. No se hace rollback de esa protección ni se agrega una retransmisión.

`flush_state()` serializa un solo writer propio y escribe un snapshot JSON en archivo temporal de la misma carpeta, flush/fsync y `os.replace` atómico. IO se ejecuta en thread. Si hay cambios durante la escritura se vuelve a guardar la generación más reciente, sin timer. Cancelar al llamador no cancela el writer ni permite iniciar una escritura concurrente que sobrescriba el estado reciente: el task se conserva y se espera mediante shield. Sus excepciones se consumen y se propagan al llamador; se registra un error observable si falla.

`close()` espera persistencia, y el stop del bridge utiliza el límite existente de **1.5s por subsistema**; fallo/timeout produce warning. El task de escritura conserva ownership en el manager. Un thread de disco ya iniciado no puede detenerse forzosamente por cancelación asyncio y puede terminar después del límite: no se presenta el timeout como durabilidad confirmada. La prueba de cancelación seguida de close demuestra el cierre normal determinista del writer y la preservación de ambas generaciones.

Un reloj UTC que retrocede o una fecha persistida futura conservan el cooldown completo usando los intervalos existentes; no habilitan una ráfaga. Sin una fuente de reloj fiable no se puede reconstruir con exactitud un lapso entre procesos. Si el reloj se adelanta, la política deriva el lapso de ese reloj civil; no se inventa una fuente monotonic persistente que el sistema no proporciona. No se cambian los intervalos configurados para compensarlo.

## Evidencia y verificaciones

Archivo mantenido: [test_remaining_admission_policy.py](../../../tests/test_remaining_admission_policy.py). Evidencia de antes: `tests/artifacts/policy-before2.xml`, tres fallos (admisión real, lifecycle ausente y pérdida de protección al reiniciar). El primer ensayo había omitido `raising=False` al introducir el límite de fixture, por lo que sus errores de setup no se atribuyen al producto; se conservó el reporte y se repitió con el setup correcto.

Después: `tests/artifacts/policy-final.xml`, **96 pruebas aprobadas**, 1.41s, combinando las nuevas políticas con regresiones administrativas, ACK y routers. `tests/artifacts/admin-policy-broad.xml`: **403 pruebas aprobadas**, 40.21s, con compatibilidad de config local/remota, privacidad, core y lifecycle. Ruff de todos los archivos propios sin errores. Mypy global integrado corresponde al principal, porque se revisaron también dependencias MQTT modificadas en paralelo.

Casos adicionales: reinicio con cambio de monotonic, rollback del reloj, categorías de protección preservadas, os.replace fallido sin pérdida del archivo anterior ni temporales sobrantes, cancelación durante escritura seguida de una generación nueva sin dos writers, state corrupto rechazado, slots liberados tras completar tareas y close antes de ejecutar callbacks.

Comprobación final independiente de cache: `mypy --strict --no-incremental` sobre los once archivos fuente propios, sin errores; Ruff de las fuentes y regresiones propias, sin errores. Los workers RX y otras tareas externas ya presentes siguen contando dentro del presupuesto compartido original; la reserva no redefine ese contrato como si sólo hubiera tareas MQTT.

No se usaron radio, broker, puertos, `.env`, configuración operativa ni servicios. Los JSON son temporales de pruebas. El hilo externo sólo entrega strings sintéticos a un dispatcher con mocks.

## Checklist LoRa

1. **Airtime:** ninguna solicitud adicional; todos los paquetes corresponden a acciones existentes. La barrera de persistencia ocurre antes de esos envíos y puede impedirlos ante fallo de IO.
2. **Spam/feedback:** admisión MQTT acotada antes de encolar callbacks; no hay reintentos, rollback remoto ni retransmisión causada por rechazo/timeout. Los cooldowns existentes sobreviven al reinicio.
3. **Timers:** no se crea scheduler periódico. Guardar config no borra timestamps ni rearma una primera iteración RF. La reserva/persistencia conserva intervalos existentes; no se eligieron umbrales nuevos.
