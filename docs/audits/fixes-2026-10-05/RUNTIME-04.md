# RUNTIME-04 — Conservar observaciones desconocidas al guardar nodos

Fecha: 2026-10-05. Base: auditoría `6717e87`. Corrección en producción con regresiones aisladas; sin migración de datos operativos.

## Reproducción

La persistencia utilizaba `NodeContactInfo.to_dict()`, un DTO de presentación que
añade sugerencias cuando no hay medición. Tras guardar y restaurar un repetidor
sin datos RF, aparecían `hop_limit=3`, `max_tx_power=22` y `repeat_enabled=True`.
El ranking inventaba además TX=20 y conectividad a partir del total de otros nodos.

Antes de modificar producción, `tests/test_registry_observed_state.py` reprodujo
el comportamiento incorrecto: **3 fallos y 3 controles aprobados**. JSON y
registros se crearon exclusivamente en el directorio temporal del fixture.

## Corrección y compatibilidad

`NodeRegistry._snapshot_contacts()` selecciona contactos canónicos bajo el lock,
sin duplicar el nodo local. La vista pública sigue usando su DTO; el writer JSON
utiliza ahora `as_flat_dict()`, con los campos del dominio y sus valores `None`.
Mantiene el contenedor existente, generation/dirty, writer serializado y replace
atómico; no cambia el esquema del archivo ni introduce una base de datos.

La analítica usa valores observados de TX, máximo TX, saltos y repetición.
No atribuye a un repetidor los clientes directos de todo el registro. La cantidad
es la lista de vecinos recibida o el contador reportado. Un cero sin evidencia
conserva compatibilidad numérica, acompañado por
`connected_clients_count_source="unknown"`; los otros orígenes son `neighbors`
y `reported`.

Los archivos históricos pueden contener tanto defaults persistidos como medidas
reales con esos mismos valores: **no se puede distinguir su procedencia**.
Por ello no se sustituyen automáticamente 3/22/True por desconocidos. La regresión
conserva los valores de un archivo legado. Una lectura real posterior debe
actualizarlos. La presentación y el slider de WEB-09 siguen pendientes;
esta corrección impide que sus sugerencias contaminen nuevos guardados.

## Verificación

```powershell
.venv/Scripts/python.exe -m pytest tests/test_registry_observed_state.py tests/test_contact_manager.py tests/test_registry_persistence_regressions.py tests/test_node_registry_telemetry.py tests/test_channels_and_contacts_controllers.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/registry-observed-after2-tmp --junitxml=tests/artifacts/registry-observed-after.xml
.venv/Scripts/python.exe -m mypy --strict src/contact_manager.py
.venv/Scripts/python.exe -m ruff check src/contact_manager.py tests/test_registry_observed_state.py
```

**19 aprobadas**, incluidas seis regresiones nuevas; mypy y Ruff sin errores.
Se cubren desconocidos después de reload, valores válidos 0/-9/False, claves
locales únicas, hashes 00, LQI real, vecinos, contadores y archivos legados.
Una invocación inicial incluyó nombres inexistentes de pruebas y no ejecutó
casos; se corrigieron las rutas antes de obtener estos resultados.

## Impacto

Cero paquetes, timers, reintentos o publicaciones nuevos; no cambia los límites
de radio ni rearma un scheduler al guardar. Atomicidad no acredita durabilidad
ante corte eléctrico. La evidencia prueba JSON temporal y dominio real,
sin confirmar el estado de dispositivos físicos.
