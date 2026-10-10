# ADR 0016: Mínimo CPython 3.12 y versión recomendada 3.13.5

- **Estado**: Aceptado por el usuario.
- **Fecha**: 2026-10-10
- **Sustituye**: [ADR 0015](0015-python-3-14-8-baseline.md) en su política de versión de Python. Conserva las decisiones independientes sobre dependencias y protocolo.

## Contexto y Problema

La actualización del instalador exigía CPython estable >=3.14.8 con `venv` y
`ensurepip`. El usuario encontró un bloqueo de actualización por ese requisito
y cambió explícitamente el mínimo a 3.12. Después indicó 3.13.5 y aclaró que es
la versión recomendada, con versiones estables posteriores admitidas y sin máximo.
Los ADR anteriores se conservan como historia, no como política vigente.

## Factores de Decisión

- Distinguir el mínimo obligatorio de la versión recomendada.
- Permitir intérpretes estables posteriores sin imponer un máximo.
- Mantener instaladores, runtime, empaquetado, herramientas y documentación coherentes.
- Conservar compatibilidad con las APIs disponibles en Python 3.12.
- Separar la política de soporte de la evidencia real de instalación y funcionamiento.

## Decisión

1. El mínimo obligatorio del proyecto es **CPython estable >=3.12**.
2. **CPython 3.13.5 es la versión recomendada**. No es una versión exacta obligatoria
   ni un máximo; se admiten versiones estables posteriores. Esta recomendación
   no afirma que 3.13.5 sea la publicación más reciente de Python.
3. Los prereleases y los intérpretes inferiores a 3.12 quedan fuera de soporte.
   Los instaladores mantienen los requisitos de `venv` y `ensurepip`.
4. El empaquetado, los guards y las herramientas deben expresar el mínimo 3.12;
   los candidatos de instalación deben incluir 3.12 y la rama recomendada 3.13,
   además de permitir una ruta explícita mediante `MESHCORE_PYTHON`.
5. No introducir dependencias obligatorias de APIs exclusivas de versiones
   posteriores a 3.12. La selección de intérpretes no modifica los pins de
   dependencias ni prueba su disponibilidad para cada sistema y arquitectura.
6. El README y los instaladores mantienen su texto en inglés, conforme a
   [AGENTS.md](../../AGENTS.md).

## Consecuencias

Una instalación con CPython estable 3.12 puede superar la comprobación de versión;
debe seguir cumpliendo módulos, paquetes y permisos requeridos. Una venv existente
no cambia de intérprete al actualizar dependencias. El operador puede seleccionar
otro Python compatible y crear un entorno nuevo cuando lo necesite.

La integración requiere comprobaciones estáticas de los archivos modificados.
Esta decisión no acredita instalación, radio, rendimiento ni resultados de suites;
las pruebas automatizadas siguen requiriendo petición explícita. Los informes
anteriores conservan sus intérpretes y resultados originales.

### Integración y evidencia del 2026-10-10

Se alinearon instaladores, guard de arranque, checker de dependencias, metadatos,
CI, herramientas de inspección y skills propias. Con Python local 3.12.10, el
análisis AST con objetivo 3.12 validó 214 archivos mantenidos; mypy estricto
validó los 81 archivos de `src` y el guard/checker. Ruff pasó sobre los archivos
Python de implementación modificados. Los parsers Bash y PowerShell validaron
la sintaxis de ambos instaladores; la estructura documental y los 16 ADRs no
presentaron incidencias.

El chequeo mypy ampliado a dos scripts de auditoría y el MCP SSH produjo diez
errores de tipado/stubs; se reprodujeron los mismos diez con sus archivos de
HEAD anterior y el objetivo 3.12. Se registran como pendientes previos, sin
relajar comprobaciones. No se ejecutaron suites, instaladores, servicios ni
conexiones operativas; no se acredita instalación en la versión recomendada.
