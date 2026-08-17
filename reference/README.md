# Repositorios de Referencia MeshCore (Single Source of Truth)

Este directorio contiene los repositorios oficiales de MeshCore utilizados exclusivamente como **fuente única de verdad (Single Source of Truth)** para los agentes de Antigravity.

---

## 1. Catálogo de Repositorios

| Directorio | Origen | Descripción | Propósito para Agentes |
| :--- | :--- | :--- | :--- |
| **`/reference/meshcore/`** | `https://github.com/meshcore-dev/MeshCore` | Firmware oficial en C/C++ (ESP32, nRF52840, RP2040) | Extracción de layouts de structs, enums, opcodes, constantes de framing UART y algoritmos CRC. |
| **`/reference/meshcore_py/`** | `https://github.com/meshcore-dev/meshcore_py` | SDK oficial de Python para MeshCore | Consulta de clases de eventos, deserializadores de paquetes y comandos seriales. |
| **`/reference/meshcore_cli/`** | `https://github.com/meshcore-dev/meshcore-cli` | CLI oficial en Python | Referencia de interacción interactiva, comandos de repetidor y utilidades de configuración. |

---

## 2. Reglas de Operación para Agentes

1. **Solo Lectura**: Ningún agente debe modificar el código dentro de `/reference/`.
2. **Inspección sin saturar contexto**: Utilizar la skill `meshcore-source-inspector` (`.agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py`) para extraer definiciones sintéticas en lugar de cargar archivos `.cpp` o `.h` completos en el contexto.
3. **Trazabilidad**: Cualquier struct implementado en `/src/protocol_types.py` o documentado en `/docs/PROTOCOL_SPEC.md` debe incluir una referencia al archivo y línea de C/C++ del que proviene.
