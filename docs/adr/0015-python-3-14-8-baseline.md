# ADR 0015: Baseline CPython 3.14.8, Eliminación de Retrocompatibilidad y Estabilización

- **Estado**: Sustituido por [ADR 0016](0016-python-3-12-baseline.md). Se conserva como decisión histórica; su mínimo 3.14.8 y exclusión de versiones anteriores ya no están vigentes.
- **Fecha**: 2026-10-10
- **Autores**: Consejo Multi-Agente (Lead Orchestrator, Bridge Architect, Protocol QA, Installer Maintenance, Security Auditor), Usuario
- **Sustituye**: [ADR 0014](0014-python-3-15-baseline.md) (revocado por experimentalidad e incompatibilidad WinRT) y [ADR 0013](0013-python-3-14-modernization.md) (propuesta histórica).

---

## Contexto y Problema

Durante la actualización arquitectónica previa, se intentó forzar la adopción de CPython 3.15.0 bajo el ADR 0014. Esta decisión introdujo fricciones severas:
1. **Sintaxis Experimental Incompatible**: Se utilizó la sintaxis PEP 810 (`lazy from ... import ...`), que constituye un `SyntaxError` en todos los intérpretes estables <= 3.14.8.
2. **Incompatibilidad de Ecosistema Binario**: En entornos Windows AMD64, las dependencias transitivas del SDK MeshCore (`winrt-runtime` y bindings WinRT de Bluetooth/Bleak) carecían de wheels precompiladas para Python 3.15, requiriendo compiladores nativos C++ inexistentes en hosts estándar.
3. **Petición Explícita del Usuario**: El usuario identificó formalmente la actualización a Python 3.15 como un error prematuro y solicitó reorientar el bridge hacia **Python 3.14.8**, eliminando categóricamente la retrocompatibilidad con versiones anteriores (< 3.14.8).

---

## Factores de Decisión

- **Estabilidad y Madurez**: Python 3.14.8 ofrece una distribución estable y consolidada con soporte completo de wheels binarias para Windows, Linux (x86_64 y aarch64) y macOS.
- **Ruptura de Retrocompatibilidad Total**: Se descarta permanentemente el soporte para Python 3.10–3.13. Toda la base de código asume características nativas de Python 3.14 sin código defensivo.
- **Imports Diferidos Estándar (PEP 562)**: Carga dinámica limpia en `src/__init__.py` utilizando `__getattr__` y `__dir__`, desacoplando tipos puros de protocolo (`src.protocol_types`) de dependencias pesadas (ASGI, red, base de datos).
- **Tipado Moderno de Nueva Generación**:
  - PEP 649 / PEP 749: Evaluación diferida nativa de anotaciones mediante la biblioteca estándar `annotationlib`.
  - PEP 695: Sintaxis de alias de tipo (`type Name = ...`) y parámetros genéricos.
  - `typing.Self` en constructores de clase (`from_dict`, `unpack`, `parse_raw_packet`).
- **Concurrencia Determinista**:
  - `asyncio.timeout` nativo para límites de espera de red y radio.
  - Retención estructurada de tareas y cancelación limpia de recursos en `bridge_core.py`.
- **Rendimiento de Checksum**:
  - Uso nativo de `binascii.crc_hqx` para el cálculo determinista de CRC-16-CCITT (polinomio 0x1021).

---

## Decisión

1. **Establecer CPython 3.14.8 como Estándar Único**:
   - `requires-python = ">=3.14.8"` en `pyproject.toml`.
   - `target-version = "py314"` en Ruff y `python_version = "3.14"` en Mypy estricto.
   - `runtime_requirements.py` aborta la ejecución con `SystemExit` ante cualquier intérprete < 3.14.8 o prerelease.
2. **Erradicar Sintaxis Experimental PEP 810**:
   - Reemplazar `lazy from` en `src/__init__.py` por una implementación canónica PEP 562 con mapa estricto `_MODULE_LOOKUP`.
3. **Alinear Instaladores y Verificadores de Dependencias**:
   - `install.sh` y `install.ps1` detectan e imponen intérpretes `Python >= 3.14.8` con `venv` y `ensurepip`.
   - `scripts/check_runtime_dependencies.py` fija `MIN_PYTHON_VERSION = (3, 14, 8)`.
   - La herramienta MCP SSH (`tools/ssh_mcp/server.py`) valida CPython >= 3.14.8 antes de importar Paramiko.
4. **Gobierno Documental**:
   - Consolidar en `AGENTS.md` y `CONTEXT.md` la referencia inmutable a Python 3.14.8.
   - El presente ADR 0015 es la Single Source of Truth para la versión de Python del proyecto.

---

## Consecuencias

- **Positivas**:
  - Eliminación de errores de sintaxis y compatibilidad 100% determinista.
  - Disponibilidad inmediata de wheels precompiladas en Windows y Linux.
  - Código fuente más limpio y expresivo sin backports ni `from __future__ import annotations`.
  - Desacoplamiento efectivo entre tipos puros de dominio e infraestructura IP/ASGI.
- **Impacto en la Malla LoRa**:
  - **Cero paquetes adicionales**. Esta optimización afecta exclusivamente la eficiencia del intérprete de backend y no altera la física ni los tiempos de emisión de radio LoRa.
