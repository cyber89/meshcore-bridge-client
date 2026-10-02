---
name: web-browser-inspection
description: Inspeccionar la SPA con Playwright autorizado, servidor virtual propio y capturas desktop/mobile; no usar una estación operativa como fixture.
---

# Navegador y SPA

Leer [AGENTS.md](../../../AGENTS.md) y [TESTING.md](../../../docs/TESTING.md).
Las pruebas de navegador se ejecutan cuando el usuario las autoriza, no automáticamente
por tocar frontend. Revisar las fixtures mantenidas en tests antes de iniciar procesos.

Usar VirtualMeshAdapter, datos temporales y servidor en loopback con puerto asignado
por el SO. No asumir que localhost:8080 es virtual: puede transmitir por radio real.
Cerrar browser/context/server/tasks en finally. Si faltan Playwright o Chromium,
instalarlos en el entorno de QA cuando sean necesarios y registrar versiones.

- Capturar pageerror, errores de consola, HTTP fallidos y WebSocket desconectado.
- Verificar navegación, exclusión LOCAL/REPEATER, TX virtual, ACK y refresco de nodos.
- Inspeccionar desktop 1920x1080 y móvil 390x844; guardar evidencia en tests/artifacts/.
- Aislar recursos externos o declarar la dependencia. Un CDN fallido no demuestra
  fallo del backend, pero tampoco debe quedar oculto por una afirmación de éxito total.
- Los scripts históricos [inspect_web.py](../../../scripts/inspect_web.py) e
  [inspect_all_views.py](../../../scripts/inspect_all_views.py) requieren leer sus
  argumentos y confirmar el destino antes de usarlos.

Las capturas sirven para revisar layout; un chequeo DOM no acredita WCAG completo
ni latencia medida. Reportar límites y skips de forma explícita.
