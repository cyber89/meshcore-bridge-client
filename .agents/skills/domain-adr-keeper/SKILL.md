---
name: domain-adr-keeper
description: Mantener CONTEXT.md y ADRs coherentes con invariantes y capacidades implementadas; conservar decisiones históricas y registrar discrepancias explícitas.
---

# Dominio y decisiones

Leer [AGENTS.md](../../../AGENTS.md), [CONTEXT.md](../../../CONTEXT.md) y
[índice documental](../../../docs/README.md). La pila oficial en reference/ es de
sólo lectura y define el protocolo; las skills no sustituyen sus opcodes/layouts.

- Mantener CLIENT, REPEATER, ROOM, SENSOR y LOCAL sin inferir rol por nombre.
- Excluir REPEATER/LOCAL de contactos y chat; administración remota usa su canal propio.
- Cada ADR registra Estado, Fecha, Contexto y Problema, Factores de Decisión,
  Decisión y Consecuencias. Distinguir acuerdo, evolución implementada y pendientes.
- No borrar historia para simular que una decisión siempre describió el código actual.
- Leer entradas recientes al inicio del ledger tras cada fase; el principal registra
  la entrega conjunta para evitar escrituras concurrentes del reporte.

```bash
python .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py
python .agents/skills/domain-adr-keeper/scripts/audit_domain_adr.py --new "Titulo de decision"
python scripts/validate_project_docs.py
```

Los validadores revisan estructura y enlaces; no certifican cumplimiento semántico
de dominio. Verificar evidencia en código y agregar regresiones cuando estén autorizadas.
