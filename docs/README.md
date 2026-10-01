# Documentación de MeshCore Bridge

Índice revisado el 2026-09-29. Distingue las reglas y guías actuales de los informes que describen un momento histórico del proyecto.

## Autoridad y lectura recomendada

1. [README del proyecto](../README.md): propósito, instalación, estructura y configuración principal.
2. [AGENTS.md](../AGENTS.md): reglas operativas, autorización de pruebas, responsabilidades y checklist de impacto RF.
3. [CONTEXT.md](../CONTEXT.md): lenguaje e invariantes del dominio, clasificación de nodos, contactos y mensajería.
4. [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md): contratos binarios/JSON, distinguiendo Companion oficial del framing raw propio.
5. [ARCHITECTURE.md](ARCHITECTURE.md), [SYSTEM_LAYERS_MANUAL.md](SYSTEM_LAYERS_MANUAL.md) y [CODE_EXPLANATION.md](CODE_EXPLANATION.md): diseño canónico en 5 capas, clases, módulos, flujos y persistencia de la implementación.
6. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md): instaladores raíz, sistema operativo, broker, permisos y servicio.
7. [N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md): descripción del [export n8n](../n8n_workflow_meshcore.json), sus contratos y límites actuales.
8. [TESTING.md](TESTING.md) e [inventario de verificación](TEST_INVENTORY.md): entorno de QA, aislamiento, alcance y evidencia; [agentes y skills](../.agents/README.md): selección y límites de herramientas.

La fuente oficial bajo `reference/meshcore/`, `reference/meshcore_py/` y `reference/meshcore_cli/` es la referencia del protocolo; esos directorios son de sólo lectura. El código del checkout determina el comportamiento implementado. Si contradice una invariante de dominio o el protocolo oficial, registrar la divergencia y corregirla expresamente; no convertir un bug en autoridad cambiando la regla.

Defaults de runtime: [config.py](../config.py). Configuración de ejemplo: [.env.example](../.env.example), que puede diferir del default efectivo; no publicar secretos de `.env`. Dependencias de runtime: [requirements.txt](../requirements.txt) y `[project].dependencies` de [pyproject.toml](../pyproject.toml). Herramientas de QA: [requirements-dev.txt](../requirements-dev.txt) y extra `dev`.

## Arquitectura visual

Los JSON de [diagrams/](diagrams/) son fuentes de los tres HTML interactivos; `scripts/build_diagrams.py` valida y los regenera con Archify. El pipeline de CRC representa el formato raw propio, no todos los eventos SDK o paquetes RF. Los recibos `*.visual-check.json` describen la versión y momento de su captura; después de regenerar deben renovarse antes de atribuirles verificación visual actual.

El contenido de los diagramas está en español; los controles del visor Archify y
su atributo HTML de idioma usan el fallback inglés del paquete instalado.

## Decisiones e historial

- [ADRs](adr/): decisiones y contexto histórico (ADR 0001 a ADR 0010); revisar estado y fecha. Una decisión anterior que no coincida con el código necesita conciliación explícita, sin borrar su historia.
- [PROTOCOL_AUDIT_2026-09-29.md](PROTOCOL_AUDIT_2026-09-29.md): auditoría de frontera de protocolo MeshCore contrastando firmware C/C++, SDK oficial 2.3.14 y el bridge.
- [AGENT_ACTIVITY_REPORT.md](AGENT_ACTIVITY_REPORT.md): registro de fases, archivos y contratos; no es una certificación del checkout completo.
- [AUDIT_REPORT_LAYER_BY_LAYER.md](AUDIT_REPORT_LAYER_BY_LAYER.md): informe de auditoría exhaustiva capa por capa (Capa 1 a Capa 5) con replicación de errores.
- [AUDIT_REPORT_2026-08-17.md](AUDIT_REPORT_2026-08-17.md): snapshot de auditoría de agosto. Sus conteos, capturas, SQLite y resultados se conservan como afirmaciones históricas.
- [FINAL_PROJECT_REPORT.md](FINAL_PROJECT_REPORT.md): consolidado histórico de agosto. Sus afirmaciones de producción, rendimiento y accesibilidad no son garantías actuales.

Las guías vigentes describen JSON para nodos/canales/airtime, capturas RAM y chat del navegador en IndexedDB. SQLite sólo interviene actualmente en la lectura cartográfica MBTiles, no como backend de nodos, mensajes o cola MQTT durable.

## Verificación y cambios RF

Las suites y auditorías se ejecutan cuando el usuario las solicita o autoriza. Indicar siempre el checkout, alcance y evidencia de la ejecución; no reutilizar un resultado histórico como prueba actual. Las herramientas de `.agents/skills/` son instrucciones/procedimientos y también deben contrastarse con el inventario del repositorio.

Antes de crear notificaciones, reintentos, timers o comandos que envíen RF, documentar airtime, riesgos de feedback/origen propio y persistencia del último disparo. Acordar con el usuario los límites y los intervalos según `AGENTS.md`. La edición documental por sí sola no activa hardware ni workflows externos.
