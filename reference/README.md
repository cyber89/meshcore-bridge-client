# Repositorios de Referencia MeshCore (Single Source of Truth)

Este directorio contiene los repositorios oficiales de MeshCore utilizados exclusivamente como **fuente única de verdad (Single Source of Truth)** para los agentes de Antigravity.

---

## 1. Catálogo de Repositorios

| Directorio | Origen | Descripción | Propósito para Agentes |
| :--- | :--- | :--- | :--- |
| **`/reference/meshcore/`** | `https://github.com/meshcore-dev/MeshCore` | Firmware oficial en C/C++ (ESP32, nRF52840, RP2040) | Extracción de layouts de structs, enums, opcodes, constantes de framing UART y algoritmos CRC. |
| **`/reference/meshcore_py/`** | `https://github.com/meshcore-dev/meshcore_py` | SDK oficial de Python para MeshCore | Consulta de clases de eventos, deserializadores de paquetes y comandos seriales. |
| **`/reference/meshcore_cli/`** | `https://github.com/meshcore-dev/meshcore-cli` | CLI oficial en Python | Referencia de interacción interactiva, comandos de repetidor y utilidades de configuración. |
| **`/reference/openhop_core/`** | `https://github.com/openhop-dev/openhop_core` | Reimplementación completa de MeshCore en Python nativo para Linux/Raspberry Pi con soporte LoRa SPI | Referencia de routing en Python, drivers SPI SX1262/SX127x y compatibilidad binaria MeshCore. |
| **`/reference/openhop_repeater/`** | `https://github.com/openhop-dev/openhop_repeater` | Daemon de repetidor MeshCore en Python para Linux/SBCs con dashboard web | Referencia de arquitectura de repetidores autónomos, gestión de paquetes y panel web. |
| **`/reference/openHop_docs/`** | `https://github.com/openhop-dev/openHop_docs` | Documentación técnica del ecosistema openHop | Guías de integración de hardware, repetidores y especificaciones. |
| **`/reference/openHop_RepeaterUI/`** | `https://github.com/openhop-dev/openHop_RepeaterUI` | Dashboard Web oficial de openHop Repeater (Vue/Vite) | Referencia de interfaces web, componentes visuales, gráficas y control de repetidores MeshCore. |
| **`/reference/openHop-Glass/`** | `https://github.com/openhop-dev/openHop-Glass` | Stack de gestión integral para repetidores (API, DB, MQTT y UI Glass) | Referencia de arquitectura full-stack, persistencia y monitoreo de repetidores. |

---

## 2. Reglas de Operación para Agentes

1. **Solo Lectura**: Ningún agente debe modificar el código dentro de `/reference/`.
2. **Inspección sin saturar contexto**: Utilizar la skill `meshcore-source-inspector` (`.agents/skills/meshcore-source-inspector/scripts/inspect_meshcore_ast.py`) para extraer definiciones sintéticas en lugar de cargar archivos `.cpp` o `.h` completos en el contexto.
3. **Trazabilidad**: Cualquier struct implementado en `/src/protocol_types.py` o documentado en `/docs/PROTOCOL_SPEC.md` debe incluir una referencia al archivo y línea de C/C++ del que proviene.
