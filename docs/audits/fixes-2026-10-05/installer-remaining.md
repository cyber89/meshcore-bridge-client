# Correcciones complementarias PI-S01 a PI-S04

Fecha: 2026-10-05. Estos cuatro IDs pertenecen a los riesgos estáticos adicionales del anexo [protocol-integration.md](../layers-2026-10-04/protocol-integration.md), separados del inventario original de 39 hallazgos. Skills aplicadas: `installer-release-maintenance` y `security-code-auditor`.

## Alcance y evidencia

No se ejecutaron los entrypoints de los instaladores, sudo, apt, pip real, modificaciones de cuentas, servicios systemd, broker ni radio. Las pruebas sólo operan sobre temporales y funciones/bloques extraídos con comandos externos simulados. PowerShell se comprobó con su parser; Bash con `bash -n` y bloques extraídos de `--dev` e instalación completa con comandos del sistema simulados. No se leyó `.env` operativo.

Antes: el bloque `--dev` extraído de `776eed7` y ejecutado con un mock de pip que devuelve 17 y Python que devuelve 0 terminó con **exit 0 y anuncio de Bandit SAST**. La evidencia está en `tests/artifacts/installer-dev-baseline.json`. Es una reproducción del error de propagación, no una instalación real. El resto de riesgos originales se acreditaba por lectura; los casos corregidos verifican comportamiento de helpers y contratos del instalador, sin afirmar que se reprodujera una caída de servicio real.

Después: [test_remaining_installer_audit.py](../../../tests/test_remaining_installer_audit.py) dio **26 passed in 2.59s**. Mypy strict de los dos helpers y Ruff de helpers/regresiones fueron correctos. La ejecución del probe con el intérprete del proyecto verificó las cuatro dependencias disponibles. No se midió cobertura de este lote aislado.

La revisión de integración detectó que la instalación completa no llamaba a
configure_service_identity: la cuenta dedicada podía no existir y SERVICE_GROUP
seguía vacío antes de chown/render_service. Dos nuevos casos, root y operador,
reprodujeron el fallo con exit 19 del chown simulado. La rama completa prepara
ahora la misma identidad/grupos existentes antes del despliegue, retirando el
bloque antiguo que asignaba grupos al invocante sin preparar el servicio.
Resultado final focalizado: **28 passed in 4.02s**; evidencia
tests/artifacts/remaining-fixes-2026-10-05/installer-final.xml. Se conserva .env
sintético y se comprueban User y Group renderizados, sin crear cuentas reales.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_remaining_installer_audit.py -q --no-cov -p no:cacheprovider --basetemp tests/artifacts/installer-remaining-second --junitxml=tests/artifacts/installer-remaining-second.xml
.venv/Scripts/python.exe -m mypy --strict scripts/check_runtime_dependencies.py scripts/staged_update.py
.venv/Scripts/python.exe -m ruff check scripts/check_runtime_dependencies.py scripts/staged_update.py tests/test_remaining_installer_audit.py
```

## PI-S01: fallos ocultos y comprobaciones anunciadas — corregido

`install.sh --dev` crea/reutiliza `.venv` local y utiliza exclusivamente su intérprete con `python -m pip`. Elimina los `|| true` de pip y Chromium y llama directamente al runner mantenido. Un fallo de instalación de tooling, navegador o QA se propaga; no se alcanza el anuncio final. Se enumeran pytest/cobertura, mypy, Ruff y documentación, y se aclara que instalar Bandit no acredita ejecutar SAST.

Tres regresiones ejecutan el bloque aislado con mocks que fallan respectivamente en pip, Chromium y runner: los tres conservan exit 17. No se cambian el servicio ni el entorno Python de producción durante `--dev`.

## PI-S02: una carpeta paho acreditaba todo el entorno — corregido

[check_runtime_dependencies.py](../../../scripts/check_runtime_dependencies.py) comprueba por el intérprete seleccionado los imports `paho.mqtt.client`, `meshcore`, `serial` y `dotenv`, las versiones de sus distribuciones y Python >=3.10. Una dependencia ausente o inferior al mínimo devuelve error. El instalador PowerShell llama al probe antes de decidir que el entorno está listo y después de instalar requirements; utiliza el mismo Python para pip y arranque.

Regresiones: cada módulo ausente, cada versión antigua, entorno completo y syntax parser PowerShell. El probe no reemplaza el resolver de pip ni constituye un inventario SBOM completo. Los imports/versiones no certifican compatibilidad RF de cada firmware.

`install.ps1 -Simulate` además utiliza la demo temporal mantenida, evitando el launcher histórico que publicaba a Mosquitto operativo; la URL real se informa al arrancar.

## PI-S03: update destructivo antes de verificar release — corregido

1. [staged_update.py](../../../scripts/staged_update.py) valida archivos requeridos y copia únicamente componentes de release a una carpeta hermana temporal, independiente incluso si origen y destino coinciden. `.env`, datos y logs nunca se copian ni reemplazan.
2. El instalador crea allí un venv nuevo, instala/verifica requirements y comprueba la sintaxis antes de detener el servicio. Si falla staging o preparación, la instalación previa no se reemplaza.
3. Guarda la unidad systemd previa, registra si el servicio estaba activo y lo detiene antes de mover componentes. Cada componente anterior se conserva en backup. Un journal registra movimientos y nuevas instalaciones; valida estructura, destino absoluto no raíz/no symlink, pertenencia a la carpeta staging y nombres de componentes permitidos.
4. Después de mover el venv se regenera configuración y activación con `EnvBuilder(with_pip=False)`, sin acceso a red ni reinstalar paquetes, y se reescribe el prefijo antiguo en los scripts de consola. Se valida nuevamente la disponibilidad de las dependencias por el intérprete definitivo.
5. `ERR`, `INT` y `TERM` restauran código/unidad y tratan de arrancar el servicio anterior si estaba activo. Si la recuperación no puede completarse, se informa y conserva el staging. Sólo un update cuya comprobación `systemctl is-active` pasa elimina las copias y anuncia éxito.

Pruebas: release incompleto, fallo de copia antes del cambio, origen igual al destino, preservación byte por byte de configuración/datos/logs sintéticos, fallo de rename después de reemplazar `src`, rollback repetible, journal inválido/escape y corrección de prefijos de un venv movido. El shell se inspecciona para confirmar preparación antes de stop y presencia del rollback; no se acredita mediante mocks el comportamiento de un systemd real.

Límites: atomicidad por rename, no transacción única del árbol ni garantía frente a pérdida de energía. El rollback conserva el código previo al inicio del instalador, no un commit anterior a operaciones externas del administrador. No se revierte actividad de aplicación o datos producidos después de un intento de arranque. El ajuste de ownership a la cuenta configurada sigue siendo una acción del instalador; los bytes de preferencias/datos no se migran silenciosamente. Consulte los pasos y recuperación manual en [DEPLOYMENT_GUIDE.md](../../DEPLOYMENT_GUIDE.md).

## PI-S04: servicio root y terminación limitada al proceso principal — corregido

La plantilla usa `meshcore:meshcore`, `NoNewPrivileges=true` y `KillMode=control-group`. El instalador renderiza `User`/`Group` con la cuenta invocante de sudo si no tiene UID 0; una invocación directa como root utiliza/crea `meshcore`. `MESHCORE_SERVICE_USER` permite seleccionar explícitamente otra cuenta. Se rechaza una cuenta con UID 0 y el grupo se obtiene de la cuenta, sin inventar GID/contraseñas.

Se incorporan sólo los grupos serie existentes (`dialout`/`uucp` por defecto, configurables mediante `MESHCORE_SERIAL_GROUPS`). Debe verificarse el grupo real del dispositivo USB: el instalador no garantiza permisos de un dispositivo arbitrario ni crea grupos inexistentes. Datos y venv se asignan a esa identidad antes del arranque; en despliegue manual la cuenta debe existir y disponer de acceso a `.env`, datos y puerto.

Las pruebas verifican la plantilla y el contrato de renderizado/validación de cuenta/grupos; no crearon usuarios ni simularon una explotación. La eliminación de root y la limpieza del cgroup son propiedades configuradas, no una certificación completa de sandbox del host.

## Impacto de malla

Las correcciones no añaden paquetes, reintentos, sondeos ni intervalos de RF. Los instaladores ya arrancaban/reiniciaban el bridge cuando el operador los invocaba; este lote cambia preparación, identidad y recuperación de ese despliegue, sin ejecutar dichos pasos en la auditoría. `--dev` conserva separación de pruebas aisladas y servicio operativo. Ningún parámetro RF o umbral de airtime se eligió durante este trabajo.
