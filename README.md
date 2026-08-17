# MeshCore Universal Bridge v2.1: LoRa Companion USB <-> MQTT <-> n8n

Puente bidireccional asíncrono, resiliente y de grado industrial para conectar nodos de radio **MeshCore Companion USB (v1.17+)** (**Heltec**, **LilyGO TTGO**, **RAKwireless WisBlock**, **Seeed Studio**, **Raspberry Pi RP2040**) con un broker **MQTT (Mosquitto)** y flujos de automatización en **n8n**.

---

## 📻 Dispositivos LoRa Compatibles

- **Heltec Automation**: WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket.
- **Seeed Studio**: SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield LoRa SX1262 / RP2040.

---

## 🚀 Características Principales (v2.1)

- **Arquitectura Modular por Capas (`/src/`)**: Desacoplamiento total entre capas de hardware, transporte, serialización y almacenamiento.
- **Adaptador Serial Híbrido Resiliente**: Soporte nativo para el SDK oficial `meshcore_py` con fallback autónomo a `RawSerialFramingAdapter` (framing binario SOF/EOF/ESC/CRC-16).
- **Decodificador Nativo CayenneLPP (`src/sensor_decoder.py`)**: Deserialización determinista de telemetría ambiental (temperatura, humedad, presión, GPS, acelerómetro MMA y voltaje).
- **Directorio Dinámico de Nodos (`src/contact_manager.py`)**: Registro en memoria `NodeRegistry` con resolución de alias y claves públicas en $O(1)$.
- **Gestión Remota de Repetidores (`src/repeater_manager.py`)**: Enrutamiento de comandos de diagnóstico (`stats-radio`, `neighbors`, `log start/stop`, `set tx`) a repetidores remotos por RF.
- **Sniffer RF de Paquetes (`meshcore/rx/log`)**: Captura en tiempo real de tramas LoRa en el aire emitidas por repetidores (evento push `0x88`).
- **Store & Forward Transaccional con TTL**: Persistencia en SQLite en modo `WAL` (`Write-Ahead Logging`), purga por expiración y deduplicación LRU en memoria RAM.
- **LoRa TX Rate Limiter con Cola de Prioridades**: Espaciado adaptativo según el cálculo analítico de tiempo en el aire LoRa de Semtech (`estimate_lora_airtime_ms`).
- **Serial Watchdog Activo**: Detección automática de bloqueos silenciosos del puerto USB y autorrecuperación suave.
- **Suite Exhaustiva de 50 Pruebas Automatizadas (100% Superadas)**: Pruebas unitarias, concurrencia multihilo, simulación de flapping de red, fallas de hardware, fuzzing de payloads, inyección SQL y matriz de flujos n8n.

---

## 📁 Estructura del Proyecto

```
meshcore-bridge/
├── config.py                         # Carga de variables de entorno y configuración
├── meshcore_bridge.py                # Entrypoint raíz compatible
├── requirements.txt                  # Dependencias Python de producción
├── pyproject.toml                    # Configuración estricta de pytest, mypy y ruff
├── .env.example                      # Plantilla de configuración de entorno
├── install.sh                        # Script de instalación y actualización para Linux / Raspberry Pi
├── install.ps1                       # Script de instalación y ejecución para Windows PowerShell
├── meshcore-bridge.service           # Archivo de servicio systemd para Linux
├── n8n_workflow_meshcore.json        # Workflow exportable listo para importar en n8n
├── src/                              # Código fuente modular de producción
│   ├── __init__.py                   # Exportaciones públicas de interfaz
│   ├── __main__.py                   # Entrypoint 'python -m src'
│   ├── bridge_core.py                # Orquestador central MeshCoreBridge
│   ├── contact_manager.py            # Registro dinámico de nodos y libreta de contactos
│   ├── mqtt_client.py                # Cliente MQTT asíncrono puenteado
│   ├── protocol_types.py             # Dataclasses inmutables y tipadas con CRC-16
│   ├── rate_limiter.py               # Rate Limiter con PriorityQueue y LoRa Airtime
│   ├── repeater_manager.py           # Gestor de repetidores remotos y RF sniffer
│   ├── sensor_decoder.py             # Decodificador CayenneLPP para sensores ambientales
│   ├── serial_driver.py              # Adaptadores de comunicación serial y Watchdog
│   └── store_forward.py              # SQLiteStoreAndForward con TTL y deduplicación
├── docs/                             # Documentación técnica completa
│   ├── ARCHITECTURE.md               # Diagramas Mermaid v2.1, clases y flujos
│   ├── PROTOCOL_SPEC.md              # Especificación de tramas binarias y contratos JSON
│   └── reference_analysis/           # Análisis técnico profundo de repositorios MeshCore
│       ├── 01_FIRMWARE_C_CPP.md      # Internals del firmware C/C++ y Packet.h
│       ├── 02_PYTHON_SDK.md          # Arquitectura del SDK meshcore_py y OpCodes
│       ├── 03_CLI_AND_REPEATER_MANAGEMENT.md # Modos UART vs Mesh y catálogo de repetidores
│       └── 04_INTEGRATION_GUIDE_FOR_AGENTS.md # Manual operativo para agentes
├── reference/                        # Repositorios oficiales de referencia (SSoT)
└── tests/                            # 50 Suites de pruebas unitarias y fuzzing
```

---

## 📡 Mapa de Tópicos MQTT para n8n

| Tópico | Tipo | Dirección | Descripción |
| :--- | :--- | :--- | :--- |
| `meshcore/bridge/state` | Estado | Bridge ➔ Broker | Estado `online`/`offline` (Retained LWT). |
| `meshcore/bridge/health`| Salud | Bridge ➔ Broker | Métricas periódicas de salud, memoria y contadores. |
| `meshcore/rx/all` | Stream | Bridge ➔ Broker | **Tópico unificado**: Todos los eventos RX normalizados en JSON. |
| `meshcore/rx/public` | RX | Bridge ➔ Broker | Mensajes recibidos en el canal público (Canal 0). |
| `meshcore/rx/channel/ch_<idx>` | RX | Bridge ➔ Broker | Mensajes recibidos en canal secundario `<idx>`. |
| `meshcore/rx/direct/<sender_id>`| RX | Bridge ➔ Broker | Mensajes directos (DMs) recibidos. |
| `meshcore/rx/telemetry` | Telemetría | Bridge ➔ Broker | Batería, voltaje, CayenneLPP (temp, hum, baro, GPS). |
| `meshcore/rx/nodes` | Anuncios | Bridge ➔ Broker | Nodos descubiertos y presencia en la malla. |
| `meshcore/rx/log` | Sniffer | Bridge ➔ Broker | Streaming de paquetes LoRa capturados en el aire. |
| `meshcore/tx` | TX | n8n ➔ Bridge | Petición para transmitir mensaje por RF. |
| `meshcore/tx/status` | ACK | Bridge ➔ n8n | Confirmación de transmisión RF (`sent`/`error`). |
| `meshcore/admin/cmd` | Admin | n8n ➔ Bridge | Comandos locales (`get_config`, `set_name`, `list_nodes`). |
| `meshcore/admin/status`| Admin | Bridge ➔ n8n | Resultado de comandos administrativos locales. |
| `meshcore/admin/repeater/<id>/cmd` | Admin | n8n ➔ Bridge | Comandos remotos a repetidores (`stats-radio`, `neighbors`). |
| `meshcore/admin/repeater/<id>/status`| Admin | Bridge ➔ n8n | Acuse y resultado del comando remoto a repetidor. |

---

## ⚡ Instalación y Despliegue en 1 Comando

### En Linux (Orange Pi / Raspberry Pi / Ubuntu / Debian):
```bash
sudo bash install.sh
```

### En Windows (PowerShell):
```powershell
.\install.ps1 -InstallDeps -Run
```

### Ejecutar Verificación Completa de Calidad:
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py
```
