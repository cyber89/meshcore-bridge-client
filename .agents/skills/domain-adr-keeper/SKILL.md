---
name: domain-adr-keeper
description: >-
  Guardián de CONTEXT.md y asistente para Architecture Decision Records (docs/adr/).
  Supervisa la adherencia al lenguaje ubicuo, valida la integridad de los ADRs existentes
  y genera borradores de nuevos ADRs ante decisiones de diseño relevantes.
---

# Domain & ADR Keeper Skill

Esta skill asegura que el modelo de dominio (`CONTEXT.md`) y el historial de decisiones de arquitectura (`docs/adr/`) se mantengan sincronizados y respetados por todos los agentes de desarrollo.

---

## 1. Capacidades

1. **Auditoría de Integridad de ADRs**:
   - Valida que todos los archivos en `docs/adr/` sigan la numeración secuencial (`0001`, `0002`, `0003`...).
   - Verifica la presencia obligatoria de secciones estándar: **Estado**, **Fecha**, **Contexto y Problema**, **Factores de Decisión**, **Decisión** y **Consecuencias**.
2. **Guardián de Invariantes de Dominio**:
   - Analiza el código fuente para garantizar que las restricciones inmutables registradas en `CONTEXT.md` y en los ADRs no hayan sido transgredidas (ej. `is_repeater` excluido de la libreta de contactos).
3. **Generador de Nuevos ADRs (Scaffolding)**:
   - Proporciona un comando para inicializar el siguiente ADR disponible con el formato estandarizado y metadatos correctos.

---

## 2. Comandos Operativos

```bash
# Auditar integridad de CONTEXT.md y docs/adr/
python .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py

# Generar un borrador para el siguiente ADR
python .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py --new "Migracion de Almacenamiento a SQLite WAL"
```
