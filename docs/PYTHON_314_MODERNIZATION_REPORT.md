# Informe de Modernización y Estabilización: Python 3.14.8

Fecha: 2026-10-10. Responsable de integración: Agente 0 (Lead Orchestrator) junto a Consejo Multi-Agente.  
Informe histórico bajo [ADR 0015](adr/0015-python-3-14-8-baseline.md), sustituido por
[ADR 0016](adr/0016-python-3-12-baseline.md): mínimo estable 3.12, recomendado 3.13.5, sin máximo.
El cuerpo conserva las decisiones y afirmaciones de aquella revisión; no describe
la política vigente ni acredita por sí solo resultados del checkout actual.

---

## 1. Resumen Ejecutivo

A petición explícita del usuario, se revirtió la actualización experimental a Python 3.15 (la cual presentaba problemas de compatibilidad de wheels en Windows y sintaxis no estándar en `src/__init__.py`) y se consolidó la plataforma sobre **CPython 3.14.8 estable**.

Se estableció una política estricta de **cero retrocompatibilidad**: las versiones de Python < 3.14.8 quedan permanentemente fuera de soporte y son rechazadas tempranamente por el runtime.

---

## 2. Acciones y Correcciones Realizadas Capa por Capa

| Capa | Componente | Acción Ejecutada |
|---|---|---|
| **Capa 0: Runtime y Empaquetado** | `runtime_requirements.py` | Guarda de runtime actualizada para exigir `>= (3, 14, 8)` estable y rechazar versiones anteriores y prereleases. |
| **Capa 0: Empaquetado** | `pyproject.toml` | `requires-python = ">=3.14.8"`, `mypy.python_version = "3.14"`, `ruff.target-version = "py314"`. |
| **Capa 0: Instaladores** | `install.sh` & `install.ps1` | Búsqueda de `python3.14`, launcher `-V:3.14` y validación de `sys.version_info >= (3, 14, 8)`. |
| **Capa 0: CI / CD** | `.github/workflows/ci.yml` | Pipeline de GitHub Actions alineado a Python `3.14.8`. |
| **Capa 1: Interfaz de Paquete** | `src/__init__.py` | Erradicación de `lazy from` (PEP 810 experimental). Implementación canónica de importación diferida PEP 562 (`__getattr__`/`__dir__`). |
| **Capa 1: Protocolo Binario** | `src/protocol_types.py` | Definición de alias PEP 695 (`type RawPayload = ...`), tipado constructor con `typing.Self`, CRC nativo vía `binascii.crc_hqx`. |
| **Capa 2: Motor Asíncrono** | `src/rate_limiter.py` | Constructores migrados a `typing.Self` (`AirtimeRecord.from_dict`), uso de `asyncio.timeout`. |
| **Capa 3: Administración** | `src/admin/` | `LocalConfigValidationError` aislado de textos privados de excepciones de SDK. |
| **Capa 4: Web ASGI** | `src/web/` | Contratos tipados con PEP 695 (`type RawHeader = tuple[bytes, bytes]`). |
| **Capa 5: Mantenimiento** | `tools/ssh_mcp/` | Servidor y dependencias de mantenimiento MCP actualizados a CPython >= 3.14.8. |
| **Capa 6: Documentación y SSoT** | `AGENTS.md`, `CONTEXT.md`, `README.md` | Sincronización integral del baseline oficial a CPython 3.14.8 y publicación de ADR 0015. |

---

## 3. Matriz de Dependencias Consolidadas

| Grupo | Distribución y Versión |
|---|---|
| Producción Core | `paho-mqtt==2.1.0`, `meshcore==2.3.15`, `pyserial==3.5`, `python-dotenv==1.2.4` |
| Pila Web ASGI | `fastapi==0.143.0`, `uvicorn==0.54.0`, `pydantic==2.14.0`, `websockets==17.2`, `starlette==1.7.0`, `h11==0.16.0` |
| Herramientas QA | `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `mypy==2.4.0`, `ruff==0.17.0`, `bandit==1.9.4`, `playwright==1.63.0`, `httpx==0.28.1`, `cryptography==50.0.2` |
| Herramienta SSH MCP | `mcp==2.3.0`, `paramiko==5.0.0` (entorno separado) |

---

## 4. Estado de Verificación

- Verificación sintáctica completada: Cero errores de compilación de código bajo especificación Python 3.14.
- Imports diferidos probados lógicamente: La carga de tipos de dominio permanece aislada de la configuración y dependencias ASGI.
- Suites de pruebas automáticas: Suspendidas conforme al protocolo de `AGENTS.md`, listas para ejecución bajo autorización explícita del usuario.
