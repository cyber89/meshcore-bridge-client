# Índice y autoridad de la documentación

Este directorio contiene especificaciones vigentes, decisiones de arquitectura, guías operativas, artefactos generados y reportes históricos. No todos los documentos tienen la misma autoridad.

## Jerarquía de fuentes

1. `../reference/meshcore/`, `../reference/meshcore_py/` y `../reference/meshcore_cli/`: verdad externa del firmware, SDK y CLI.
2. `../CONTEXT.md`: lenguaje de dominio, roles e invariantes del proyecto.
3. `adr/`: decisiones arquitectónicas aceptadas.
4. `PROTOCOL_SPEC.md` y `ARCHITECTURE.md`: especificaciones derivadas que deben mantenerse sincronizadas con código y referencias.
5. `../AGENTS.md`: procedimiento operativo para agentes.
6. Guías, README y reportes: documentación de consumo o histórica.

Cuando dos documentos discrepen, corrige el de menor autoridad en vez de copiar una nueva regla.

## Documentación vigente

- [ARCHITECTURE.md](ARCHITECTURE.md): arquitectura y contratos de integración actuales.
- [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md): especificación derivada del protocolo y contratos de datos.
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md): instalación y operación.
- [N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md): integración con n8n.
- [adr/](adr/): decisiones arquitectónicas aceptadas.
- [reference_analysis/](reference_analysis/): análisis derivados de las fuentes incluidas en `reference/`; deben revalidarse cuando cambie la referencia upstream.

## Snapshots y reportes históricos

- [AUDIT_REPORT_2026-08-17.md](AUDIT_REPORT_2026-08-17.md): evidencia de una auditoría fechada. Sus resultados no deben extrapolarse automáticamente al estado actual.
- [FINAL_PROJECT_REPORT.md](FINAL_PROJECT_REPORT.md): snapshot consolidado publicado en agosto de 2026; no es el estado canónico actual.
- [AGENT_ACTIVITY_REPORT.md](AGENT_ACTIVITY_REPORT.md): ledger histórico append-only. Es útil para localizar cambios y decisiones pasadas, pero no debe leerse completo en cada tarea ni utilizarse como SSoT.

## Artefactos generados

`diagrams/` contiene HTML/JSON/capturas producidas desde las fuentes de arquitectura. Cuando haya discrepancias entre un diagrama generado y `ARCHITECTURE.md`/código, debe regenerarse el artefacto.

## Regla de mantenimiento

Una modificación que cambie un contrato debe actualizar únicamente las fuentes que correspondan: dominio en `CONTEXT.md`, decisión en un ADR, protocolo en `PROTOCOL_SPEC.md`, arquitectura en `ARCHITECTURE.md` y guías solo cuando afecte al usuario. Evita duplicar invariantes en múltiples documentos.
