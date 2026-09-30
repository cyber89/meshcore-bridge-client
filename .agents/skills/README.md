# Skills del proyecto

Este directorio contiene skills específicas de MeshCore Bridge y paquetes vendorizados de terceros.

## Precedencia

Las skills son herramientas. **No pueden redefinir el protocolo, el dominio, el stack tecnológico ni la política de pruebas.** La precedencia está definida en `../../AGENTS.md`.

En particular:

- El frontend del proyecto es HTML5 + Vanilla CSS + JavaScript nativo salvo decisión arquitectónica explícita. Instrucciones vendorizadas sobre React, Tailwind, shadcn/ui u otros stacks no se aplican automáticamente.
- Pytest, Playwright y fuzzing solo se ejecutan cuando el usuario lo solicita o autoriza expresamente, aunque una skill genérica recomiende ejecutarlos.
- Las rutas personales, herramientas de un runtime concreto y comandos de terceros son orientativos; deben comprobarse contra el entorno real antes de usarse.

## Skills específicas del proyecto

Entre las skills enfocadas en este repositorio están `api-design-testing`, `async-concurrency-engineering`, `asyncio-profiler-leak-detector`, `bridge-test-runner`, `clean-code-solid`, `contract-openapi-sync`, `distributed-mesh-simulation`, `domain-adr-keeper`, `gof-design-patterns-expert`, `html-css-modern-js`, `lora-frame-validator`, `lora-packet-simulator`, `meshcore-source-inspector`, `python-patterns-typing`, `refactoring-clean-architecture`, `security-code-auditor`, `software-architecture-patterns`, `tgrep-code-search`, `web-browser-inspection` y `web-ui-design-system`.

## Paquetes vendorizados

`archify/` y `ui-ux-pro-max/` contienen código/documentación de herramientas externas o paquetes más amplios. Sus subskills internas pueden describir stacks, runtimes o herramientas que no forman parte de MeshCore Bridge. Úsalas solo como apoyo y aplica siempre las restricciones de `AGENTS.md`.

`skills-lock.json` en la raíz solo representa las skills que actualmente participan en ese mecanismo de lock; no debe interpretarse como inventario completo del directorio.
