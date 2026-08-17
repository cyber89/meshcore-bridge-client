---
name: python-patterns-typing
description: >-
  Estándares avanzados de Python moderno (3.10+): Tipado estático estricto (mypy --strict),
  estructuras inmutables (@dataclass slots/frozen), protocolos estructurales (typing.Protocol),
  patrones asíncronos nativos (asyncio/async generators) y suites deterministas de pytest.
---

# Python Patterns & Static Typing Skill

Esta skill establece las directrices de ingeniería y tipado estático estricto para Python moderno (>= 3.10) en arquitecturas de alto rendimiento y grado industrial.

## Principios Fundamentales
1. **Tipado Estático Estricto (mypy --strict)**:
   - Toda función, método y generador debe declarar anotaciones completas en parámetros y retorno (`def func(x: int) -> list[str]:`).
   - Uso de uniones modernas con sintaxis de pipe (`str | None`, `int | float`) en lugar de `Optional` o `Union`.
   - Colecciones nativas parametrizadas (`list[dict[str, Any]]`, `tuple[int, ...]`, `set[str]`) importando `from __future__ import annotations`.
   - Prohibido el uso indiscriminado de `Any`. Utilizar `TypeVar`, `Generic[T]`, o `typing.Protocol` para polimorfismo estructural.

2. **Inmutabilidad y Eficiencia de Memoria**:
   - Modelos de datos y tramas de protocolo deben usar `@dataclass(frozen=True, slots=True)` para optimización de memoria (reducción de `__dict__`) e inmutabilidad garantizada.
   - Enums tipados estrictos derivados de `enum.Enum` o `enum.IntEnum`.

3. **Asincronía Determinista (asyncio)**:
   - Nunca realizar llamadas I/O bloqueantes dentro del event loop (`time.sleep` $\to$ `asyncio.sleep`, `socket.recv` $\to$ `asyncio.StreamReader.read`).
   - Gestión adecuada de tareas en segundo plano con `asyncio.create_task` y almacenamiento de referencias para evitar que el garbage collector las destruya prematuramente.
   - Manejo de cancelación limpia (`asyncio.CancelledError`) en loops de larga duración.

4. **Testing Determinista con Pytest**:
   - Fixtures modulares y parametrización con `@pytest.mark.parametrize`.
   - Aislamiento de recursos y limpieza garantizada (`setUp`/`tearDown` o `yield` fixtures).
   - Uso de `unittest.IsolatedAsyncioTestCase` o `pytest-asyncio` para corutinas.

## Herramientas de Verificación
```bash
python .agents/skills/python-patterns-typing/scripts/verify_python_standards.py
```
