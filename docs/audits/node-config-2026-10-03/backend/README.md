# Evidencia dirigida: contratos de configuración LOCAL/REMOTA

Base: `81f4260eccf9bdec6c6f7ba9caca5322997f6eeb`. Python 3.12.14.
Estado: diagnóstico y propuesta; sin cambios de producción o referencias.

`test_reproductions.py` es un script de diagnóstico ejecutado por pytest fuera de
la suite mantenida `tests/`. Sus assertions describen los defectos observados;
**19 passed no significa que el producto sea correcto**: son 16 reproducciones
confirmadas y tres controles de rechazo. Después de corregir los defectos, los
casos relevantes deben convertirse en regresiones con expectativas deseadas.

Todas las llamadas de escritura terminan en `AsyncMock`. No hay servicios,
UART/TCP real, broker, HTTP de red o transmisión RF. `dotenv.load_dotenv` queda
bloqueado antes de importar configuración/producción; JSON, canales y mapas usan
`tmp_path`. Passwords/PINs/keys son sintéticos. La fixture garantiza cero fallback
`execute_tx` y cero waiters residuales. El mock MQTT sólo captura llamadas.

Comando final reproducible desde la raíz, usando un nuevo basetemp propio en cada
ejecución para evitar limpiar directorios ajenos:

```powershell
.venv/Scripts/python.exe scripts/run_quality_checks.py --only-tests --timeout 90 --report docs/audits/node-config-2026-10-03/backend/pytest-report.json -- docs/audits/node-config-2026-10-03/backend/test_reproductions.py -q -o addopts= -p no:cacheprovider --basetemp=docs/audits/node-config-2026-10-03/backend/tmp-run-04 --junitxml=docs/audits/node-config-2026-10-03/backend/junit.xml
```

La evidencia final está en `pytest-report.json` y `junit.xml`: 19 casos, cero
fallos/skips, 0,75 s de pytest. No se ejecutaron suites amplias, cobertura, mypy,
ruff o navegador en esta subtarea. Los archivos `initial-environment-failure.*`
conservan el fallo inicial de ACL del TEMP de Windows, anterior a todas las
reproducciones; **no es defecto del producto**. `intermediate-observed-output.*`
conserva una expectativa diagnóstica inicial que reveló `None` en la radio
remota. `intermediate-with-integration-duplicate.*` registra una ejecución de 20
casos que incluía el NameError de adverts; ese caso se retiró por estar cubierto
por la evidencia de integración del agente principal.

## Casos y resultados

| # | Clase | Entrada | Resultado observado / evidencia JSON |
|---|---|---|---|
| 1 | Reproducción | POST LOCAL `{tx_power:22}`, SELF_INFO anterior 20 | HTTP 200, applied=22, config/GET=20. `local_tx_readback_stale.json` |
| 2 | Reproducción | POST LOCAL `{bandwidth:500}`, SELF_INFO 868 MHz/SF7/CR6 | SDK recibe 915 MHz/SF11/CR5: se modifican campos no pedidos. `local_radio_patch_defaults.json` |
| 3 | Reproducción | owner_info, altitude, beacon_interval, telemetry_interval, hop_limit | HTTP 200/applied; cero comandos SDK; handler recreado pierde owner/intervalos. `local_memory_only_applied.json` |
| 4 | Reproducción | POST LOCAL sólo latitude=41 | HTTP 200/applied vacío; coordenada permanece 40; cero set_coords. `local_coordinate_ignored.json` |
| 5 | Reproducción | name válido + path_hash_mode=3 | set_name ejecutado; interno partial/applied; REST 503 oculta lo aplicado. `local_partial_hidden.json` |
| 6 | Reproducción de límite mock | set_name devuelve False | HTTP 200 y caché mutada. `local_false_success_false.json` |
| 7 | Reproducción de límite mock | set_name devuelve Event DISABLED | HTTP 200 y caché mutada. `local_false_success_disabled.json` |
| 8 | Control | set_name devuelve Event ERROR | HTTP 400; caché sin mutar. `control_sdk_error_rejected.json` |
| 9 | Reproducción | PIN sintético=123456 | Publicación status MQTT incluye PIN en applied y config. `local_pin_status_secret.json` |
| 10 | Reproducción | REMOTA admin_password sintético | Contraseña literal en dispatched_commands REST/MQTT. `remote_batch_secret.json` |
| 11 | Reproducción | REMOTA bogus_setting=42 | HTTP 200/dispatched; envía set_bogus_setting, sin valor. `remote_unknown_dispatched.json` |
| 12 | Reproducción | REMOTA name válido + tx_power inválido | Envía name antes del rechazo HTTP 400; respuesta no indica despacho parcial. `remote_partial_hidden.json` |
| 13 | Reproducción | REMOTA sólo bandwidth; registro con métricas None | Envía `set radio None,500,None,5`. `remote_radio_patch_null_fields.json` |
| 14 | Reproducción | REMOTA sólo bandwidth; contacto SDK sin registro | Envía defaults 915/500/SF11/CR5 sin readback. `remote_radio_patch_defaults.json` |
| 15 | Reproducción | REMOTA target_node por nombre de CLIENT | Guardia por rol eludida; send_cmd al CLIENT. `remote_client_alias_guard.json` |
| 16 | Control | Mismo CLIENT por clave pública | HTTP 400; cero send_cmd. `control_client_key_rejected.json` |
| 17 | Reproducción | Password ` synthetic ` con espacios válidos | SDK recibe `synthetic`: credencial alterada. `remote_login_password_trimmed.json` |
| 18 | Control | LOGIN_SUCCESS de public key ajena | HTTP 401. `control_login_wrong_sender.json` |
| 19 | Reproducción | GET LOCAL refresh=true con provider desconectado | HTTP 200/caché/defaults; radio_connected=false pero ninguna indicación de refresh fallido o freshness. `local_refresh_offline_cached.json` |

## Causas y solución propuesta

- **Readback/caché:** `local_config_executor.py:111` superpone tx_power antiguo de
  SELF_INFO; setter `:533-535` cambia sólo `_local_config`. Fusionar la misma
  versión de estado tras confirmación y distinguir el valor solicitado, ACK
  local y readback físico. Las pruebas no demuestran que la radio aplicó 22 dBm,
  sino la contradicción entre ACK mock, applied y DTO devuelto.
- **PATCH radio LOCAL:** los valores no enviados se toman del cache host en
  `local_config_executor.py:548/559/570/584`, no de la configuración consolidada
  del dispositivo. Leer un snapshot actual y validar el conjunto antes de
  mutarlo; no completar silenciosamente con defaults si faltan datos reales.
- **Parámetros sólo memoria:** `local_config_executor.py:498-512/650-676` no
  escribe esos parámetros al dispositivo ni los persiste como configuración
  bridge. Separar metadatos bridge de opciones soportadas por firmware, y
  devolver unsupported/ignored explícitos o implementar persistencia dentro
  del alcance definido. No presentar almacenamiento volátil como aplicación
  física. Contrastar los comandos admitidos con la auditoría de protocolo.
- **Coordenada incompleta:** condición `local_config_executor.py:481` ignora
  silenciosamente un único eje. Exigir la pareja o completar con coordenada
  vigente validada; rechazar campos ignorados en vez de retornar éxito vacío.
- **Mutación parcial LOCAL:** orden secuencial `:429-433` aplica antes de validar
  todo; catch `:435` produce partial que `BaseController.command_failure` rechaza
  como estado desconocido (`base.py:76`), perdiendo applied. Prevalidar todas las
  entradas y preservar detalle de cambios ya confirmados ante fallos posteriores.
- **Éxito SDK demasiado permisivo:** `admin/sdk_commands.py:22-27` no rechaza
  False/DISABLED. Usar tipos de respuesta admitidos por cada comando; no sólo una
  lista corta de errores. Estos dos casos son inyección defensiva controlada;
  no prueban que set_name oficial emita DISABLED en hardware.
- **Secretos en salidas:** PIN se incluye en configuración/applied y publicación
  `local_config_executor.py:725-727/463`; batch remoto conserva el comando sin
  redactar `repeater_executor.py:258/263-264`. Redactar en DTO/logs/MQTT de estado
  sin alterar el comando real; no mostrar contraseña nueva en dispatched_commands.
- **Validación y parcial REMOTA:** params se recorren/envían de inmediato en
  `repeater_executor.py:250-259`; builder fallback `repeater_manager.py:207`
  admite keys desconocidas como comandos sin argumentos. Validar y compilar todo
  el lote antes del primer envío; conservar despachos confirmados en fallo.
- **PATCH radio REMOTA:** `repeater_executor.py:234-245` usa dict.get con keys
  presentes en None y defaults cuando falta el registro. No hay lectura previa.
  Rechazar componentes desconocidos o recuperar readback bajo demanda antes de
  construir el comando; no transmitir `None` ni completar valores arbitrarios.
- **Guardia de rol por alias:** `_collect_target_info` (`repeater_executor.py:191`)
  sólo compara keys; `_resolve_target` sí admite nombre. Resolver primero clave
  canónica única, luego validar rol/localidad del mismo destinatario que se enviará.
- **Password trimming:** `repeater_controller.py:59/100/127` y
  `admin_handler.py:331` aplican strip. Preservar bytes de credenciales y validar
  sólo longitud/NUL según protocolo; frontend tiene trimming adicional que
  requiere corrección sincronizada.
- **Refresh offline:** `fetch_device_config` (`local_config_executor.py:230-246`)
  devuelve caché cuando no hay SDK; controller `config_controller.py:24-28`
  también convierte excepciones en caché sin comunicar freshness. Permitir datos
  cacheados, pero incluir status/fuente/timestamp/refresh_error inequívocos para
  que la UI no presente una lectura del hardware que no ocurrió.

`/api/node/config` es alias de `/api/config` (`api_router.py:62`); radio/identity
también comparten setter (`:690-701`). No existe readback de hardware después del
batch remoto, y correctamente su status interno es dispatched, no applied
(`repeater_executor.py:261-263`). Este diagnóstico no prueba aplicación remota,
sesiones operativas, interoperabilidad de firmware ni seguridad completa.
