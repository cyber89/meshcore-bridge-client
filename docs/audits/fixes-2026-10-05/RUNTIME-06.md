# RUNTIME-06: SELF_INFO no debe convertir TX -9 dBm en 247 dBm

Fecha: 2026-10-05. Estado: corregido y verificado con eventos y SDK simulado.

## Reproducción y causa

El parser SDK de referencia lee `SELF_INFO.tx_power` con `dbuf.read(1)[0]` (`reference/meshcore_py/src/meshcore/reader.py`): una potencia int8 de -9 se representa como el byte 247. La lectura de configuración local ya corregía ese caso, pero el adaptador almacenaba el byte sin normalizar y un evento asíncrono ejecutaba `int(247)` en el router, sobrescribiendo la caché que contenía -9. Por ello la configuración podía cambiar entre una lectura y un evento posterior.

Se agregó una regresión antes del parche que recorre `_handle_self_info()` → `bridge.on_mesh_event()` → router → caché de administración, con un payload SDK independiente y sin arrancar servicios:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_self_info_power_normalization.py -k normalizes -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/power-normalization-before-tmp
```

Resultado previo: **1 fallo y 3 controles aprobados**. El fallo mostró `adapter.self_info["tx_power"] == 247`, frente al valor esperado -9; el log del router también anunciaba `TX: 247 dBm`. Los controles -9, 0 y 30 no fallaban.

## Solución

`normalize_tx_power()` en `src/protocol_types.py` define una sola interpretación del campo de lectura: conserva enteros int8 y convierte bytes uint8 de 128–255 a su representación con signo. Devuelve `None` para ausencia, booleanos, fracciones, cadenas y valores fuera de -128–255. Es una normalización binaria, sin aplicar límites de potencia del hardware ni validar solicitudes de escritura.

El adaptador usa snapshots propios normalizados al asignar/leer inicialmente `self_info` y al procesar eventos. Copia el diccionario del SDK; no cambia el payload original entregado al dispatcher privado. Un dato explícito `None` conserva el estado desconocido. Un valor malformado en un evento no reemplaza una potencia anterior válida.

El router y `LocalConfigExecutor` consumen la misma función. Para `SELF_INFO`, el router evita que el decodificador genérico de telemetría redondee una fracción inválida a una potencia inventada; esa lectura se excluye de la actualización. Las lecturas de configuración conservan la última potencia válida cuando el snapshot contiene un valor malformado. El caso 0 sigue siendo un valor válido y 30 permanece 30: no se modifica `max_tx_power`, el rango hardware ni la política de escritura.

Archivos de producción: `src/protocol_types.py`, `src/serial/sdk_adapter.py`, `src/rx_router.py`, `src/admin/local_config_executor.py`. Se conservaron los cambios anteriores de RUNTIME-05 y WEB-01 en sus módulos compartidos.

## Verificación

```powershell
.venv/Scripts/python.exe -m pytest tests/test_self_info_power_normalization.py tests/test_local_advanced_parameters.py tests/test_local_config_save_roundtrip.py tests/test_domain_official_compatibility.py tests/test_capture_privacy.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/power-normalization-final3-tmp
.venv/Scripts/python.exe -m ruff check src/rx_router.py src/serial/sdk_adapter.py src/admin/local_config_executor.py src/protocol_types.py tests/test_self_info_power_normalization.py
.venv/Scripts/python.exe -m mypy --strict src/rx_router.py src/serial/sdk_adapter.py src/admin/local_config_executor.py src/protocol_types.py
```

- **159 pruebas aprobadas**, incluidas 27 regresiones propias, en 1,71 s.
- Ruff: sin incidencias.
- Mypy estricto: sin incidencias en los cuatro módulos modificados.
- Valores de integración: 247/-9, -9, 0, 30, `None` y datos malformados; se verifica que el payload SDK permanece intacto.
- Valores de frontera del helper: -128, 127, 128 y 255; asignación inicial y fallback de snapshot SDK normalizados sin aliasar el payload privado.
- Se mantienen las verificaciones de parámetros locales, guardas de dominio, guardado/recarga y privacidad de capturas.

Una primera invocación posterior incluyó por error un nombre inexistente de archivo de pruebas: pytest no ejecutó casos y se repitió el comando con las rutas reales. No se incluye esa incidencia como defecto de producción.

## Impacto y límites

No se envían paquetes RF ni comandos nuevos, no se agregan publicaciones, timers, notificaciones ni reintentos; el airtime y los cooldowns permanecen sin cambios. Sólo se interpreta correctamente una lectura recibida. No se realizaron conexiones serie ni pruebas en un dispositivo físico. El helper interpreta el byte de protocolo, pero no certifica qué potencias soporta un modelo concreto: la validación de escritura sigue en los mecanismos existentes.
