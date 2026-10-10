# ADR 0013: Migración Arquitectónica a Python 3.14.8 y Ruptura de Retrocompatibilidad

- **Estado**: Sustituido por [ADR 0014](0014-python-3-15-baseline.md); propuesta histórica, no especificación vigente.
- **Fecha**: 2026-10-10
- **Autores**: Consejo Multi-Agente (Lead Orchestrator, Bridge Architect, Firmware Investigator, Security Auditor, Installer Agent), Usuario
- **Base**: `930823f` (Web SPA en Bootstrap 5.3 + FastAPI ASGI consolidado)

> **Rectificación del 2026-10-10**: Se conserva el texto original para mantener el
> historial. Python.org publicó CPython 3.15.0 estable el 2026-10-09 y la decisión
> vigente está en el ADR 0014. Las promesas de rendimiento, seguridad total y
> eliminación de fugas que aparecen abajo no fueron demostradas por mediciones o
> suites. `wait_for`/`gather` siguen siendo APIs válidas; `TaskGroup`, t-strings,
> JIT o ejecución sin GIL no se adoptan universalmente ni garantizan esos resultados.

## Contexto y Problema

MeshCore Bridge se diseñó históricamente con una restricción estricta de retrocompatibilidad con **Python 3.10** (`requires-python = ">=3.10"`). Esto obligó al proyecto a:
1. Mantener patrones de concurrencia obsoletos basados en `asyncio.wait_for()`, `asyncio.gather()` manual y manejo defensivo de tareas descolgadas en lugar de `asyncio.TaskGroup` y `asyncio.timeout()`.
2. Congelar paquetes críticos en versiones legadas (por ejemplo, `websockets==16.1.1` debido a que `websockets>=17.0` requiere Python 3.11+).
3. Evitar el uso de sintaxis moderna de tipado (`type Alias = ...` de PEP 695, `typing.Self`, `@override`, `assert_never`).
4. Requerir `from __future__ import annotations` de forma generalizada para evitar evaluación temprana de referencias circulares o forward references.
5. Sufrir la contención del Global Interpreter Lock (GIL) en cargas intensivas de deserialización de paquetes RF, cálculo de LQI y retransmisión MQTT simultánea.

Con el lanzamiento oficial de **Python 3.14** (y su mantenimiento consolidado en **Python 3.14.8** en septiembre de 2026), el usuario ha solicitado formalmente **abandonar el soporte para versiones anteriores (< 3.14)** y adoptar Python 3.14.8 como estándar único y obligatorio para MeshCore Bridge.

## Factores de Decisión

1. **Aportes de Rendimiento y Paralelismo**: Python 3.14.8 incorpora mejoras profundas en el motor Tier 2 JIT, ejecución de bucles sin sobrecarga, soporte oficial Free-Threaded (nogil, PEP 779) y subintérpretes en la librería estándar (PEP 734).
2. **Concurrencia Determinista y Estructurada**: Reemplazar más de 45 llamadas frágiles a `asyncio.wait_for()` por `asyncio.timeout()` nativo y estructurar la orquestación del ciclo de vida con `asyncio.TaskGroup`.
3. **Desbloqueo de Ecosistema de Dependencias Modernas**: Permitir la actualización de todas las dependencias a su última versión oficial en PyPI, desbloqueando `websockets==17.2` y aprovechando Pydantic 2.14 y FastAPI 0.143 sin restricciones de compatibilidad con versiones obsoletas.
4. **Tipado Estricto de Nueva Generación**: Adopción de la sintaxis de parámetros de tipo (PEP 695 `type Alias = ...`), evaluación diferida de anotaciones (PEP 649 / PEP 749), `typing.Self`, `@override` y `typing.Never`.
5. **Seguridad y Control de Flujo**: Adopción de Template String Literals (PEP 750 / t-strings) para prevenir inyecciones y cumplimiento de las restricciones de control de flujo en bloques `finally` (PEP 765).
6. **Compresión Moderna**: Incorporación del módulo estándar `compression.zstd` (PEP 784) para el almacenamiento de telemetría y logs.

## Decisión

1. **Ruptura de Retrocompatibilidad**:
   - Establecer `requires-python = ">=3.14.8"` en `pyproject.toml`.
   - Modificar las reglas de `AGENTS.md` y `CONTEXT.md` para consagrar Python 3.14.8 como Single Source of Truth, eliminando las restricciones de Python 3.10.
2. **Actualización de Despliegue e Instaladores**:
   - Actualizar `requirements.txt` y `requirements-dev.txt` con todas las dependencias en su versión más reciente disponible en PyPI:
     - `websockets==17.2` (desbloqueado de 16.1.1).
     - `meshcore==2.3.15`, `paho-mqtt==2.1.0`, `pyserial==3.5`, `python-dotenv==1.2.4`.
     - `fastapi==0.143.0`, `uvicorn==0.54.0`, `pydantic==2.14.0`, `starlette==1.7.0`, `h11==0.16.0`.
     - `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `mypy==2.4.0`, `ruff==0.17.0`, `bandit==1.9.4`, `playwright==1.63.0`, `httpx==0.28.1`.
   - Modificar `install.sh` y `install.ps1` para verificar y requerir el intérprete `Python 3.14.8`.
3. **Plan de Modernización del Código Fuente (`/src/`)**:
   - **Concurrencia**: Reemplazar llamadas a `asyncio.wait_for` por context managers `async with asyncio.timeout(...)`.
   - **Ciclo de Vida**: Refactorizar tareas de fondo en `bridge_core.py` utilizando `async with asyncio.TaskGroup() as tg:`.
   - **Tipos**: Migrar `TypeVar` y definiciones complejas a `type Name = ...`, eliminando el boilerplate de `from __future__ import annotations`.
   - **Compresión**: Utilizar `compression.zstd` nativo para almacenamiento de paquetes sniffer y logs históricos.

## Consecuencias

- **Positivas**:
  - Aumento medible de rendimiento en bucles de deserialización de tramas LoRa gracias a la combinación de compilador JIT y ejecución sin GIL.
  - Erradicación de fugas de tareas huérfanas mediante concurrencia estructurada.
  - Código fuente más limpio, moderno y conciso sin código defensivo para versiones antiguas.
  - Máxima seguridad de paquetes al operar con el 100% de las dependencias en su última versión oficial de PyPI.
- **Riesgos y Mitigación**:
  - *Disponibilidad de Python 3.14.8 en el entorno operativo*: Para las estaciones donde el sistema operativo anfitrión (e.g. Raspberry Pi OS / Debian) proporcione únicamente versiones anteriores de Python en sus repositorios APT por defecto, el instalador `install.sh` proveerá instrucciones o scripts de compilación/instalación autónoma del binario de Python 3.14.8 mediante `pyenv` o paquetes oficiales.
  - *Impacto en la Malla LoRa*: **Cero paquetes adicionales**. Esta optimización afecta exclusivamente la eficiencia del intérprete de backend y no altera la física ni los tiempos de emisión de radio LoRa.
