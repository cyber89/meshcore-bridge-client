# ADR 0014: Baseline CPython 3.15.0 y actualización aislada de dependencias

- **Estado**: Sustituido por [ADR 0015](0015-python-3-14-8-baseline.md); decisión histórica revocada por inestabilidad de ecosistema (WinRT en Windows) y sintaxis experimental no estándar (PEP 810).
- **Fecha**: 2026-10-10
- **Sustituye**: [ADR 0013](0013-python-3-14-modernization.md), conservado como propuesta histórica.
- **Sustituido por**: [ADR 0015](0015-python-3-14-8-baseline.md)

## Contexto y Problema

El proyecto conservaba documentación y comprobaciones para Python 3.10, mientras
una propuesta posterior elegía Python 3.14.8. El usuario pidió actualizar el runtime
y las dependencias. [Python.org](https://www.python.org/downloads/release/python-3150/)
publicó CPython 3.15.0 estable el 2026-10-09. Las versiones usadas en revisiones
anteriores no acreditan el funcionamiento de esta nueva combinación.

## Factores de Decisión

- Usar una base explícita común en packaging, instaladores, comprobadores y CI.
- Conservar contratos REST/WebSocket/MQTT, framing oficial, roles y protección de secretos.
- Comprobar las dependencias transitivas y distribuciones por intérprete/plataforma.
- Separar producción, QA y herramientas de mantenimiento; no reutilizar una estación operativa como fixture.

## Decisión

1. Adoptar CPython 3.15.0 o superior como mínimo del bridge. Python 3.10–3.14 deja
   de ser una matriz de soporte actual; los registros anteriores siguen siendo históricos.
2. Alinear `requires-python`, mypy, Ruff, CI, checker e instaladores con esta base.
   Crear entornos nuevos con el intérprete seleccionado; no sustituir el Python del sistema.
3. Fijar versiones publicadas verificadas para producción y QA. La fecha de consulta
   y los resultados de resolución se registran en el informe de actualización; un
   paquete universal no demuestra disponibilidad de todas sus dependencias nativas.
4. Modernizar tipos y concurrencia sólo cuando preserve el comportamiento observable.
   `TaskGroup` tiene cancelación conjunta al fallar un miembro; no sustituye automáticamente
   registros de tareas independientes o workers de disco retenidos durante el apagado.
   Conservar deadlines, propietarios y cierre de recursos. No reemplazar mecánicamente
   `wait_for`/`gather`, ni retirar anotaciones diferidas sin revisar sus consumidores.
5. Ejecutar pytest/cobertura, mypy, Ruff y navegador únicamente en los entornos
   aislados autorizados por el usuario. Registrar fallos y limitaciones por herramienta
   y runtime. No conectar a radio, broker o SSH operativos durante QA.

## Consecuencias

Las estaciones anteriores necesitan un intérprete adecuado y una nueva venv antes
de actualizar. Un repositorio APT, una wheel o un instalador disponible no acredita
por sí solo cada destino. La selección de JIT o builds sin GIL necesita evaluación
independiente; no se afirma menor RAM, más velocidad, ausencia de fugas o seguridad
completa. Esta decisión no introduce transmisiones RF, reintentos ni timers nuevos.

## Evidencia y pendientes

La integración y los resultados por plataforma se registran en el
[informe de modernización](../PYTHON_314_MODERNIZATION_REPORT.md). La ausencia de wheels
WinRT para CPython 3.15 impidió instalar el SDK completo en este Windows; la prueba
ASGI aislada no elimina ese límite. Linux permitió resolver e importar el SDK.

La versión estable se contrastó con la página primaria de Python.org. La implementación
efectiva debe verificarse en los diffs de los cuatro límites de instalación/runtime y
en los resultados de QA. Los snapshots de `reference/`, el inventario histórico y los
informes anteriores conservan sus versiones y procedencia; no se actualizan para simular
compatibilidad nueva. Los resultados de otras versiones del intérprete no se atribuyen a 3.15.
