# Verificación backend de configuración LOCAL/REMOTA

Fecha 2026-10-03. HEAD `9f561932d648470e8c8bd23fc789a66bdb378d0e`. Skills aplicadas: `contract-openapi-sync`, `bridge-test-runner` y `python-patterns-typing` para el diagnóstico Python. Sin modificaciones de producción, referencias ni suites existentes.

## Alcance y conclusión

Se siguieron los contratos reales REST → controller → AdminHandler → executor → SDK mock. **No se puede certificar que cada parámetro se lea y escriba sin errores**: se reproducen fallos actuales, incluidos campos aceptados que no despachan ningún comando, lectura de PIN sin redactar, AutoAdd con max_hops que falla y configuración radio local basada en defaults del host. Los resultados de despacho positivos acreditan que el código llega al SDK mock y actualiza un snapshot; no acreditan escritura física ni persistencia del firmware.

La auditoría previa corresponde a `81f4260`. El checkout actual sí corrige parte de sus hallazgos. Este documento conserva esa diferencia y utiliza evidencia nueva.

## Método y evidencias

- [test_current_backend.py](test_current_backend.py): 71 diagnósticos, **71 passed**, sin skips/failures; [pytest-report.json](pytest-report.json), [junit.xml](junit.xml). Cada caso guarda un JSON de entradas, salida real y llamadas SDK.
- Suites mantenidas revisadas antes de ejecutar: `test_node_and_repeater_config.py`, `test_admin_executors.py`, `test_admin_official_compatibility.py`, `test_repeater_manager_unit.py`: **55 casos, 47 passed, 8 failed, 1 warning**, [maintained-pytest-report.json](maintained-pytest-report.json), [maintained-junit.xml](maintained-junit.xml).
- Python 3.12.14. Se desactiva carga dotenv antes de imports; rutas de persistencia, canales, mapas y logs se redirigen a temporales propios. Toda escritura RF termina en AsyncMock; MQTT captura llamadas. Cero radio real, broker, red HTTP, fallback TX o waiters residuales.
- No se ejecutaron cobertura, mypy, ruff ni navegador en esta subtarea. La suite general no se ejecutó. Los mocks positivos de setters son `Event(OK)` y los de CLI `Event(MSG_SENT)`; son respuestas sintéticas.
- Primer intento de colección usó el nombre reservado pytest `request` en parametrización; se corrigió el harness. La salida intermedia de 62 passed/1 failed detectó trimming residual y se reemplazó por un diagnóstico del defecto; su informe se sobrescribió y no se conserva como archivo, aunque fue leído durante la auditoría. La suite mantenida terminó y guardó JSON/JUnit, pero el runner falló después al imprimir stdout mediante cp1252 (`UnicodeEncodeError`); se conservan conteos reales de pytest. Reproducciones finales usaron `PYTHONIOENCODING=utf-8`.

**71 passed significa observaciones confirmadas, incluyendo bugs**, no aceptación del producto. Estos diagnósticos quedan fuera de `tests/`; tras corregir código deben convertirse en regresiones sobre resultados deseados.

Reejecución desde raíz, con basetemp nuevo:

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-tests --timeout 90 --report docs/audits/node-config-verification-2026-10-03/backend/pytest-report.json -- docs/audits/node-config-verification-2026-10-03/backend/test_current_backend.py -q -o addopts= -p no:cacheprovider --basetemp=docs/audits/node-config-verification-2026-10-03/backend/tmp-repeat-01 --junitxml=docs/audits/node-config-verification-2026-10-03/backend/junit.xml
```

## Matriz parámetro → endpoint → executor → SDK → resultado

Abreviaturas: **S** = despacho setter con `OK` mock; **H** = lectura snapshot host/SDK, sin consulta independiente; **Q** = getter SDK mock con payload; **D** = CLI enviado, sin confirmación remota de aplicación; **M** = sólo memoria del bridge. No hay equivalencia entre D y configuración aplicada.

Todos los campos locales generales se consumen por GET/POST `/api/config`; `/api/node/config` y `/api/node/settings` son aliases. `/radio` y `/identity` comparten el mismo setter y no restringen el payload a su dominio. Fuente: [api_router.py:652](../../../../src/web/api_router.py#L652), [ConfigController:112](../../../../src/web/controllers/config_controller.py#L112).

| Parámetro LOCAL | Lectura | Escritura/executor y SDK | Resultado actual dirigido |
|---|---|---|---|
| name | SELF_INFO, H y Q en refresh | `_apply_identity_settings` → set_name | S/H consistentes tras OK; False/ERROR/DISABLED rechazados |
| latitude, longitude (lat/lon) | SELF_INFO adv_lat/adv_lon; H/Q | mismo executor → set_coords | pareja S/H correcta; eje único falla si pareja sólo existe en SELF_INFO |
| altitude (alt/altitude_m), owner_info (owner) | snapshot/cache | mismo executor, sin setter SDK | M presentada como applied; owner no persiste en nuevo handler; altitude puede sobrevivir en objeto SDK por mutación host, sin escritura física |
| tx_power (power) | SELF_INFO; H/Q | `_apply_radio_settings` → set_tx_power, clamp | S/H coherentes en 22; límite efectivo de placa y signed wire requieren matriz de protocolo |
| frequency (radio_freq), bandwidth (bw), spreading_factor (sf), coding_rate (cr) | SELF_INFO; H/Q | mismo executor → set_radio | S/H positivos con baseline int; PATCH rellena datos desde cache host distinto al dispositivo; default CR `4/5` rompe PATCH; CR99 enviado en mock |
| repeat (repeat_enabled) | SELF_INFO/DEVICE_INFO, H/Q | mismo executor → set_radio con radio completa | S/H positivo con baseline completo; no basta parámetro booleano si baseline no validado |
| beacon_interval (advert_interval), telemetry_interval, hop_limit (hops) | cache/defaults | `_apply_timing_settings`, ningún comando | M, applied sin hardware ni persistencia; conversión inválida silenciada |
| telemetry_mode_base, telemetry_mode_loc, telemetry_mode_env | SELF_INFO/H/Q | `_apply_other_params_settings` → set_other_params_from_infos | S/H positivos 2; no hay validación completa de enum/rango antes del primer setter |
| adv_loc_policy, manual_add_contacts, multi_acks | SELF_INFO/H/Q | mismo executor/SDK OTHER_PARAMS | S/H para 1; `to_bool` reduce a 0/1, investigar multi_acks contra bitfield oficial |
| pin (devicepin) | SELF_INFO/cache/H | `_apply_advanced_meshcore_settings` → set_devicepin | S con 123456; POST/MQTT redacted; GET revela PIN sintético literal |
| rx_delay (rx_dly), airtime_factor (af) | get_tuning, Q divide wire ×1000; H | mismo executor → set_tuning, wire ×1000 | S/Q nominales correctos; SELF_INFO previo vuelve a sobreponer valor antiguo |
| path_hash_mode | cache; `/api/config/path_hash_mode` GET | setter general o dedicado → set_path_hash_mode | S/H modo2; modo3 bloqueado antes de name; getter dedicado no consulta hardware |
| custom_vars | get_custom_vars Q o cache H; endpoint GET/POST/DELETE | set_custom_var y delete→cadena vacía | S/Q/H positivos; lote segundo error devuelve500 tras aplicar primero sin parcial |
| autoadd flags, max_hops | `/api/config/autoadd` → get_autoadd_config Q/H | set_autoadd_config | sólo flags15 S; incluir max_hops1 produce500 sin setter |
| flood_scope | `/api/config/flood_scope` → get_default_flood_scope Q/H | set_default_flood_scope o reset | S/Q/H nominal positivo; freshness independiente ausente |
| device clock | get_time Q, proyección H | `/api/config/sync-clock` → set_time | S/H epoch positivo; get clock UI también inserta hora host |
| duty_cycle_limit_pct, warn_threshold_pct, cutoff enabled/threshold/resume | ConfigController/tracker | muta AirtimeTracker y save_history(sync=True) | Inspección estática; no se reprodujo escritura de políticas en esta subtarea |
| repeater_pre_send_delay_enabled, repeater_pre_send_delay_s | módulo config | ConfigController muta módulo | Sólo memoria; no se acreditó persistencia; valor finito/no negativo validado |
| hardware_board, model, firmware, batería, ruido, uptime, métricas | getters hardware/Q + métricas bridge | sólo lectura | refresh nominal con 11 getter payloads; refresh totalmente fallido también marca stale=false |

RemoteConfig POST `/api/repeater/remote/config` → `RepeaterController.set_remote_config` → `RepeaterAdminExecutor._execute_batch_config` → `RepeaterManager` → `send_cmd`. Lectura remota usa `/api/repeater/remote/action`, queries específicas y respuestas parseadas; no existe GET/POST remoto simétrico por campo ni verificación posterior automática del lote. Fuente: [executor:225](../../../../src/admin/repeater_executor.py#L225).

| Parámetro REMOTO | Lectura real disponible por construcción | Escritura batch/SDK | Resultado dirigido |
|---|---|---|---|
| name/owner_name | get name (acción CLI explícita; capacidad por firmware) | set name | name D probado; sin readback automático |
| owner_info | get owner.info; endpoint owner | set owner.info | D probado |
| latitude/longitude | get lat/get lon | batch arma set_latitude/set_longitude | HTTP200 D vacío, sin SDK; alias lat/lon sí D probados |
| frequency/freq, bandwidth/bw, sf/spreading_factor, cr/coding_rate | get radio + parser | set radio conjunto | lote completo D y pending_reboot=true; incompleto rechazado; CR99 cambia a5 |
| tx_power/power/tx | get tx | set tx | D22 probado; clamp genérico sin conocer placa remota |
| repeat | get repeat | set repeat on/off | D true probado; repeat_enabled batch ignorado |
| advert_interval | get advert.interval | set advert.interval | D120 probado, unidad ambigua en builder; beacon_interval batch ignorado |
| flood_advert_interval | get flood.advert.interval | set flood.advert.interval | D6 probado; unidades/rango comprobar protocolo |
| admin_password/password | secreto no debe leerse | password valor | D y respuesta redactada; login espacios aún alterados en handler |
| guest_password | acceso write-only según firmware | builder set_guest_password devuelve None | HTTP200 sin SDK |
| new_password | write-only | set_new_password no reconocida | Inspección estática: descartada; diagnóstico guest_password representa misma ruta |
| public_key/pk, permission/perm, acl_mode, identity_key | ACL binaria/query por permisos | requiere comando compuesto setperm, no set individual | public_key/permission descartados reproducidos; ACL restante inspección; builder setperm mapea permisos mal (agente protocolo) |
| region | consulta según implementación/capacidad | set_region no reconocida | HTTP200 sin SDK; no asumir región local como dato remoto |
| hop_limit/telemetry_interval/altitude/path_hash_mode/tuning | depende de firmware y acción CLI | ausentes del allowed_keys batch | no son campos batch implementados; interfaz debe declarar unsupported o usar capacidad explícita |
| password de sesión/login, logout | LOGIN_SUCCESS correlacionado; session remoto | send_login_sync/send_cmd | LOGIN_SUCCESS guest rechazado; no se ejercitó logout aquí; password se strip en handler |

Lecturas remotas listadas indican comandos/rutas disponibles por inspección; **no se ejecutó readback remoto de cada parámetro** ni se certifica éxito semántico del parser/firmware. Los positivos locales Q sí ejercitan extracción de payload, escalado tuning y cache en entorno aislado.

## Correcciones históricas que sí sobreviven en el checkout

1. TX power actualiza SELF_INFO; POST y GET mock muestran22 coherente.
2. path_hash_mode3 se prevalidó: name previo no se ejecuta. Error parcial local conserva applied/config y `partial=true` en HTTP400.
3. False/ERROR/DISABLED se rechazan; nombre host no muta. Falta allowlist positiva por comando.
4. POST local y publicación MQTT redactan PIN; comando password remoto en DTO/MQTT también se redacta. GET local permanece expuesto.
5. Campo remoto desconocido, TX no convertible y radio incompleto rechazados antes de send_cmd.
6. Alias de CLIENT y LOCAL rechazados. Contraseñas conservadas por controlador pero handler aún las recorta.
7. Refresh offline devuelve stale/cache/error explícitos. La ruta conectada con todos los getters fallidos aún presenta freshness positiva.

## Defectos actuales reproducidos: pasos, impacto y solución

| ID | Reproducción y evidencia | Resultado/impacto | Solución propuesta y aceptación |
|---|---|---|---|
| BV01 P1 | Guardar PIN123456 mock; GET /api/config; [JSON](bug_pin_get_leak.json) | POST/MQTT PIN=0; GET PIN123456 | redactor común DTO para GET, refresh, WS y admin get_config; conservar secreto sólo internamente; todos los canales públicos sin literal |
| BV02 P1 | SELF_INFO868/125/SF7/CR6; host915/250/SF11/CR5; PATCH bandwidth500; [JSON](bug_local_radio_host_baseline.json) | setter915/500/SF11/CR5 cambia3 campos ajenos | baseline consolidado por fuente/timestamp del mismo dispositivo; no rellenar defaults host; preservar868/7/6 |
| BV03 P1 | Constructor limpio default CR4/5; PATCH bandwidth125; [JSON](bug_local_default_cr_string.json) | error invalid literal int('4/5') aunque SELF_INFO CR6 | normalizar CR una sola vez; representación wire5..8; usar baseline hardware; pruebas cold start/refresh/reset |
| BV04 P2 | Enviar owner_info, altitude, intervalos, hop_limit; recrear handler; [JSON](bug_local_memory_only.json) | HTTP200 applied con0 comandos SDK; intervalos regresan defaults | declarar metadatos/políticas host separados; persistir JSON asíncrono/atómico o rechazar unsupported; nunca prometer escritura física |
| BV05 P2 | Sólo latitude41 y SELF_INFO longitude−3; [JSON](bug_local_single_coord_baseline.json) | HTTP400 datos incompletos pese longitud conocida | tomar baseline consolidado; aceptar eje con pareja real o explicar necesidad de enviar ambos; no defaults geográficos |
| BV06 P1 | name válido + tx_power invalid; [JSON](bug_local_partial_validation.json) | name aplicado antes de HTTP400 partial | precompilar/validar todo lote antes del primer setter; preservar parcial por fallo de transporte, distinto de entrada inválida |
| BV07 P1 | GET refresh conectado sin getters disponibles; [JSON](bug_refresh_queries_unavailable_fresh.json) | once fallos silenciosos; stale=false/cached=false | recopilar éxito/error de cada consulta, source/timestamp por campo; no actualizar observed_at como si hardware respondió |
| BV08 P1 | POST autoadd flags15,max_hops1; [JSON](bug_autoadd_max_hops.json) | HTTP500 NotImplementedError,0 setters | soportar opcode58 extendido via gateway/SDK compatible o declarar max_hops unsupported HTTP422/501; no añadir kwargs inexistentes al SDK actual |
| BV09 P1 | POST remoto latitude41, longitude−2, beacon_interval120, repeat_enabled=true, guest_password, public_key, permission o region por separado; `bug_remote_allowed_ignored_*.json` | HTTP200 status dispatched pero lista vacía | normalizar aliases y tabla explícita campo→builder; exigir compilación no vacía; ACL como estructura completa; rechazar unsupported antes de RF |
| BV10 P1 | Local CR99; remoto conjunto CR99; [local JSON](bug_local_cr_not_prevalidated.json), [remoto JSON](bug_remote_cr_defaults.json) | local envía99, remoto sustituye5 | rangos5..8 y formato4/N validado; nunca defaults ante entrada inválida; cero paquetes |
| BV11 P1 | Login password ` synthetic `; [JSON](bug_login_spaces_guest_control.json) | SDK recibe synthetic; contraseña válida alterada | quitar strip en AdminHandler331 y demás rutas de credenciales; validar bytes UTF8/NUL sin transformar |
| BV12 P1 | Lote remoto name válido + lat inválida; [JSON](bug_remote_partial_http_ok.json) | name enviado; HTTP200 exterior status ok, interior partial | precompilar lote; controller manejar partial/error uniforme; conservar dispatched sin presentarlo como completo |
| BV13 P2 | SELF_INFO tuning0.2/1.0; POST0.125/1.5; [JSON](bug_tuning_stale_self_info.json) | applied nuevo/config viejo | versión de snapshot única y actualización coherente tras ACK; readback independiente para verificado |
| BV14 P2 | Local bogus_setting42; [JSON](bug_local_unknown_ignored.json) | HTTP200 applied vacío | allowlist local explícita incluyendo políticas host; unknown→422 y cero setter |
| BV15 P2 | Setter name devuelve SELF_INFO mock en vez OK; [JSON](bug_sdk_positive_allowlist_missing.json) | HTTP200 y mutación | allowlist por operación: OK setters, eventos tipados getters, MSG_SENT transporte; esta inyección defensiva no prueba respuesta física inválida |
| BV16 P1 | Custom vars first=OK, second=ERROR; [JSON](bug_custom_vars_partial_hidden.json) | first guardada; HTTP500 sin applied/partial | API common partial; preservar claves escritas y rechazadas; validador previo y redactor de payloads |

Fuentes que explican las causas: [local executor:447](../../../../src/admin/local_config_executor.py#L447), [:565](../../../../src/admin/local_config_executor.py#L565), [:626](../../../../src/admin/local_config_executor.py#L626), [:772](../../../../src/admin/local_config_executor.py#L772), [:838](../../../../src/admin/local_config_executor.py#L838), [:952](../../../../src/admin/local_config_executor.py#L952); [SDK success:22](../../../../src/admin/sdk_commands.py#L22); [batch remoto:233](../../../../src/admin/repeater_executor.py#L233), [:273](../../../../src/admin/repeater_executor.py#L273), [:321](../../../../src/admin/repeater_executor.py#L321); [controller remoto:98](../../../../src/web/controllers/repeater_controller.py#L98); [handler credenciales:331](../../../../src/admin_handler.py#L331); [custom controller:335](../../../../src/web/controllers/config_controller.py#L335).

## Las ocho pruebas mantenidas que fallan

| Prueba | Causa observada y cómo tratarla |
|---|---|
| node_and_repeater: local_node_get_and_set_config | AsyncMock setter sin respuesta Event explícita; strict success inspecciona mock is_error y produce warning coroutine; fijar fixture representativa, después verificar baseline real |
| node_and_repeater: post_config_radio_updates_frozen_radio_config | mock set_radio sin respuesta tipada; fixture debe devolver OK/ERROR auténticos |
| node_and_repeater: remote_repeater_login_and_config | esperaba401 pero obtiene400 antes del criterio de autenticación; inspección muestra add_contact MagicMock no tipado que strict success puede rechazar al asegurar contacto; revisar resolución/contactos y devolver Event explícito; no ocultar si reaparece con fixture realista |
| node_and_repeater: repeater_manager_payload_builder | esperaba set_freq retirado porque CommonCLI no lo soporta; reescribir expectativa hacia set radio completo |
| admin_executors: local_config_executor_set_local_config | local_cfg sólo name/pubkey, pese SELF_INFO válido; nueva prevalidación exige baseline cache local completo; coincide con BV02: corregir implementación/fuente, no rellenar fixture para ocultar defecto |
| admin_official: repeat_string_false_is_encoded_as_zero | cache local sin BW/SF/CR; no se llama set_radio; usar snapshot real coherente y verificar rechazo baseline desconocido |
| repeater_manager_unit: build_repeater_radio_commands | expectativa set_freq obsoleta; protocolo dicta conjunto radio |
| repeater_manager_unit: build_repeater_location_and_security_commands | esperaba set pos compuesto retirado; usar setters lat/lon independientes y validar sus resultados |

No se corrigieron fixtures ni se redujeron expectativas durante esta auditoría. Los 47 positivos conservan su alcance unitario actual; no acreditan interoperabilidad de la malla.

## Pasos de implementación y aceptación

1. Crear esquema capacidades por dispositivo, versión y rol; listar cada campo, unidad, rango, read/write, secret, requires_reboot y soporte. Separar identidad radio, política bridge y telemetría sólo lectura.
2. Resolver target a clave única antes de rol/localidad/login/despacho; cuando se use SDK contacts ausente del registry, contrastar el tipo oficial. Mantener REPEATER fuera de contactos/chat y LOCAL sin loop. Validar admin read/write según sesión RF y HTTP.
3. Baseline por campo con source, observed_at y freshness; consolidar SELF_INFO/DEVICE_INFO/getters sin defaults de escritura. GET redactado obligatorio.
4. Normalizar aliases, números/CR/booleanos y credenciales; validar todo lote y compilar plan completo antes de radio. Cero llamadas si falla validación; campos desconocidos/unsupported explícitos.
5. Serializar comandos oficiales con SDK del checkout; coordinar AutoAdd extendido y OTHER_PARAMS con agente protocolo. No considerar un mock setter prueba de serialización real.
6. Resultado por campo: requested, sent, accepted, applied, verified, failed, unsupported y pending_reboot. Respuesta partial uniforme en todos los controladores. La UI sólo anuncia completo cuando todos los campos pertinentes se verifican.
7. Readback local bajo demanda; remoto planificado bajo autorización RF del usuario, con recuperación si cambiar radio deja el enlace inaccesible. Lote RF queda dispatched hasta respuesta/readback del mismo destinatario.
8. Persistencia host atómica y asíncrona; revisar `save_history(sync=True)` en event loop. Guardar configuración no debe crear/rearmar timers ni borrar cooldowns.
9. Convertir diagnósticos BV01..BV16 a regresiones de aceptación, reparar fixtures contra enums oficiales y ejecutar suites dirigidas, mypy, ruff y cobertura; luego suite general autorizada. Matriz hardware real separada de mocks.

No se implementaron timers, envíos físicos ni cambios de intervalos. Antes de implementar pasos que emitan paquetes debe quedar documentado: número de paquetes y airtime por hop, rutas de feedback/MQTT y deduplicación/origen local, cooldowns/reintentos y persistencia de timestamps. **Intervalos y umbrales requieren elección del usuario conforme AGENTS.md §4**; esta auditoría propone estados/contratos sin fijarlos.
