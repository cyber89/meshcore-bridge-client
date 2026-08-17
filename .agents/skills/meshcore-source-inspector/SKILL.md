---
name: meshcore-source-inspector
description: >-
  Herramienta especializada para analizar el código fuente de referencia en C/C++ y Python
  de MeshCore (/reference/). Extrae structs binarios, enums, constantes de framing (#define)
  y algoritmos de CRC sin saturar la ventana de contexto. Usar cuando se requiera investigar
  tipos, formatos de tramas o layouts de memoria del firmware.
---

# MeshCore Source Inspector Skill

Esta skill permite al **Protocol & Firmware Investigator Agent** inspeccionar la base de código C/C++ de MeshCore de forma sintética y determinista.

## Scripts y Herramientas

El script principal de análisis se encuentra en:
[inspect_meshcore_ast.py](./scripts/inspect_meshcore_ast.py)

## Modos de Uso

### 1. Extracción Global de Protocolo (Defines, Structs, Enums)
```bash
python .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py
```

### 2. Filtrado por Símbolo Específico
Para buscar structs, constantes u opcodes particulares (ej. `telemetry`, `packet`, `routing`, `crc`):
```bash
python .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py --symbol telemetry
python .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py --symbol crc
```

### 3. Generación en formato JSON
Para procesamiento estructurado:
```bash
python .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py --format json --out docs/ast_dump.json
```

### 4. Inspección de Rutas Específicas
```bash
python .agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py --path reference/meshcore/include --path reference/meshcore_py/src
```

## Buenas Prácticas
- No volcar archivos `.cpp` enteros en el prompt; utilizar siempre esta herramienta para extraer únicamente las firmas y layouts necesarios.
- Utilizar los offsets calculados para redactar `/docs/PROTOCOL_SPEC.md` y verificar la correspondencia con `/src/protocol_types.py`.
