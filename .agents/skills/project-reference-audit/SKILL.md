---
name: project-reference-audit
description: Inventariar y verificar documentación y procedencia de referencias de MeshCore Bridge; contrastar afirmaciones con el checkout y parsers oficiales sin arrancar servicios.
---

# Documentación y procedencia de referencias

Usar para inventarios del proyecto, revisión documental y trazabilidad de las
copias oficiales/terceras. [AGENTS.md](../../../AGENTS.md) establece permisos y
roles; [PROJECT_KNOWLEDGE.md](../../../docs/PROJECT_KNOWLEDGE.md) reúne el mapa y
los pendientes comprobados. Domain-adr-keeper mantiene decisiones e invariantes.

- Inventariar con `scripts/inventory_project_knowledge.py`, usando el Python
  local disponible. Imprime JSON sin importar aplicación ni leer `.env`, logs o
  datos operativos. El snapshot en docs/PROJECT_INVENTORY.json requiere generación
  deliberada; los hashes acreditan un momento, no actualidad permanente.
- Comprobar `.git` propio antes de consultar remote/HEAD de una referencia:
  sin ese marcador Git asciende al bridge y devuelve una procedencia falsa.
  Registrar origen, SHA, fecha, estado limpio y evidencia; un URL del README es
  sólo origen declarado, no acredita la copia ni su versión.
- Sólo firmware meshcore, SDK meshcore_py y CLI meshcore_cli son autoridad del
  protocolo. Terceros son comparación. No modificar ni actualizar reference/.
  Consultar upstream cuando se solicite actualidad y registrar lo no verificable;
  disponibilidad web no demuestra igualdad con el checkout local.
- Para afirmaciones binarias, leer serializador/parser y constantes oficiales;
  distinguir advert RF, Companion y raw propio, datos del contacto/opcode y
  layout wire/struct en memoria. Cotejar líneas y offsets del helper con fuente.
- Para capacidades, vincular cada afirmación a código actual. Conservar informes
  históricos y ADRs; registrar divergencias en lugar de convertir bugs en dominio.
- Revisar enlaces portables y nombres reales de skills. El validador
  `scripts/validate_project_docs.py` sólo acredita estructura/enlaces locales;
  no comprueba anchors, URLs remotas, semántica o funcionamiento.
- Entregar alcance, comandos, hallazgos, archivos cambiados y omisiones al
  principal para el ledger. Un inventario no autoriza suites, hardware, broker,
  workflows o instalación. Usar agentes lectores para áreas distintas cuando la
  tarea abarque varios subsistemas; el principal integra con propiedad de archivos.
