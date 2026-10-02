# Agentes y skills del proyecto

La política operativa está en [AGENTS.md](../AGENTS.md); el dominio en
[CONTEXT.md](../CONTEXT.md); la documentación vigente se encuentra en
[docs/README.md](../docs/README.md). Las instrucciones del usuario prevalecen.

## Selección por tarea

| Área | Skills propias | Evidencia y límites |
|---|---|---|
| Dominio/documentación | domain-adr-keeper | ADRs, implementación y enlaces; un chequeo estructural no prueba semántica |
| Protocolo | meshcore-source-inspector, lora-frame-validator | Pila oficial de sólo lectura; separar Companion, LoRa wire y fallback propio |
| Python/concurrencia | python-patterns-typing, async-concurrency-engineering, asyncio-profiler-leak-detector | Python 3.10 mínimo; profiler sintético, no garantía 24/7 |
| Arquitectura/refactor | clean-code-solid, refactoring-clean-architecture, gof-design-patterns-expert, software-architecture-patterns | Heurísticas y patrones; preservar contratos, evitar cambios por cuotas de líneas |
| API/web | api-design-testing, contract-openapi-sync, html-css-modern-js, web-ui-design-system, web-browser-inspection | HTTP nativo/Vanilla SPA; paridad léxica no valida payloads/WS |
| QA/simulación | bridge-test-runner, lora-packet-simulator, distributed-mesh-simulation | Suites autorizadas, radio virtual, datos temporales, loopback |
| Seguridad | security-code-auditor | Bandit y revisión específica; no garantía de ausencia de vulnerabilidades |
| Búsqueda | tgrep-code-search | Reutilizar binario disponible; rg es fallback |

Consultar únicamente los SKILL.md relevantes; no ejecutar todo el catálogo como una
suite ni considerar sus ejemplos una descripción del sistema.

## Paquetes de terceros

`skills/archify` y `skills/ui-ux-pro-max` incluyen sus propios assets, herramientas y
licencias. Se conservan como paquetes externos; esta revisión no actualiza su código
ni aplica sus ejemplos de frameworks al frontend Vanilla del bridge.

## Verificación y herramientas

[TESTING.md](../docs/TESTING.md) describe el entorno, inventario y resultados.
`python scripts/run_quality_checks.py` coordina pytest, mypy, ruff y comprobación
documental. `.agents/skills/bridge-test-runner/scripts/run_checks.py` delega en él.
Los helpers regex/AST son señales auxiliares: sus alcances se documentan en cada skill.
No probar contra la radio física o un servidor de producción. Guardar evidencia
generada en `tests/artifacts/` (ignorada por Git) y publicar el resumen en documentación.
