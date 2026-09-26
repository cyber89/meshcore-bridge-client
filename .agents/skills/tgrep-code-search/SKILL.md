---
name: tgrep-code-search
description: >-
  Motor de búsqueda indexada por trigramas de alto rendimiento (microsoft/tgrep).
  Permite realizar búsquedas regex ultra-rápidas (<10ms) en miles de archivos del
  repositorio, bases de código C/C++ de referencia (/reference/) y módulos del bridge.
---

# tgrep Code Search Skill

Esta skill permite a los agentes ejecutar búsquedas de código a escala con latencia submilisegundo utilizando el motor **`microsoft/tgrep`**.

## Binarios Disponibles

- **Ruta Global en PATH**: `tgrep.exe` (ubicado en `C:\Users\Ruby\.gemini\antigravity\bin\tgrep.exe`).
- **Ruta de Respaldo Local**: `.agents\bin\tgrep.exe`.

---

## Modos de Uso y Comandos Principales

### 1. Búsqueda Rápida de Expresiones Regulares o Símbolos
Utiliza la sintaxis estándar compatible con `ripgrep`:

```powershell
# Búsqueda insensible a mayúsculas
tgrep -i "FirmwareAdvertType"

# Búsqueda exacta de palabra
tgrep -w "REPEATER" src/

# Búsqueda con contexto (3 líneas antes y después)
tgrep -C 3 "AdvertDataHelpers" reference/meshcore/
```

### 2. Filtros por Tipo de Archivo y Globs
```powershell
# Filtrar solo archivos C/C++
tgrep -t c -t cpp "MeshPacket" reference/meshcore/

# Filtrar solo archivos Python
tgrep -t py "class .*Router" src/

# Filtrar por glob específico
tgrep -g "*.h" "MAX_PACKET_SIZE" reference/
```

### 3. Salida Estructurada JSON
Para procesamiento sintético y análisis por scripts:
```powershell
tgrep --json "packet_loss" > results.jsonl
```

### 4. Gestión del Índice Trigram
El índice reside en el directorio local `.tgrep/` (ignorado en `.gitignore`):

```powershell
# Comprobar el estado del índice
tgrep status

# Reconstruir o actualizar el índice tras cambios masivos
tgrep index

# Búsqueda directa sin utilizar el índice (comportamiento puro ripgrep)
tgrep --no-index "patrón"
```

---

## Buenas Prácticas para Agentes

1. **Exploración de `/reference/`**: Siempre preferir `tgrep` para localizar firmas de structs o enums en `/reference/meshcore/` antes de abrir archivos completos con `view_file`.
2. **Medición de Tiempos**: Agregar `--stats` cuando se requiera diagnosticar el plan de ejecución y número de candidatos filtrados por trigramas.
3. **No Indexar Binarios**: `tgrep` excluye automáticamente archivos binarios detectados y respeta `.gitignore`.
