# MeshCore Universal Bridge & Web Station v3.0

Puente bidireccional asíncrono, resiliente y de grado industrial para conectar nodos de radio **MeshCore Companion USB (v1.17+)** (**Heltec**, **LilyGO TTGO**, **RAKwireless WisBlock**, **Seeed Studio**, **Raspberry Pi RP2040**) con **MQTT (Mosquitto)**, flujos de automatización en **n8n** y una **Interfaz Web SPA Moderna (HTML5, Vanilla CSS, JS)** con **RF Packet Sniffer** y **Tablero de Métricas Avanzadas**.

---

## 📻 Dispositivos LoRa Compatibles

- **Heltec Automation**: WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket.
- **Seeed Studio**: SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield LoRa SX1262 / RP2040.

---

## 🚀 Características Principales (v3.0)

- **🌐 Cliente Web Station SPA Integrado (`http://<IP>:8080`)**:
  - Interfaz ultraligera sin frameworks pesados (< 10 MB RAM, arranque en < 50ms).
  - Cumplimiento **WCAG 2.2 AA** con navegación 100% por teclado, foco visible y regiones ARIA.
  - Chat en tiempo real para Canal Público 0, Canales Privados 1..7 (Cifrado AES) y Mensajes Directos (DMs).
  - **Mapa GPS Interactivo** (Leaflet) con detección de modo offline para despliegues de campo aislados.
  - **🕵️ RF Packet Sniffer & Analizador Wire (`0x88 LOG_DATA`)**: Captura e inspección profunda de tramas LoRa en el aire en tiempo real con visor de volcado hexadecimal.
  - **📈 Tablero de Métricas Avanzadas & Estadísticas**: Rankings de Top 10 Nodos por Tráfico, Top Repetidores por Clientes/Vecinos, Ranking de Calidad de Señal (SNR/RSSI) y Desglose de Errores por Categoría.
  - **📜 Consola de Logs del Sistema**: Terminal interactiva con filtros de severidad (`INFO`, `WARN`, `ERROR`), buscador y exportación en formato `.json`.
- **🔌 API REST JSON & WebSocket Hub**: Endpoints completos (`/api/status`, `/api/nodes`, `/api/contacts`, `/api/channels`, `/api/tx`, `/api/analytics`, `/api/sniffer/control`, `/api/system/logs`) con soporte CORS preflight `OPTIONS`.
- **Decodificador Nativo CayenneLPP (`src/sensor_decoder.py`)**: Deserialización determinista de telemetría ambiental (temperatura, humedad, presión, GPS, acelerómetro MMA y voltaje).
- **Directorio Dinámico de Nodos (`src/contact_manager.py`)**: Registro en memoria `NodeRegistry` con resolución de alias y claves públicas en $O(1)$.
- **Gestión Remota de Repetidores (`src/repeater_manager.py`)**: Enrutamiento de comandos de diagnóstico (`stats-radio`, `neighbors`, `log start/stop`, `set tx`) a repetidores remotos por RF.
- **Store & Forward Transaccional con TTL**: Persistencia en SQLite en modo `WAL` (`Write-Ahead Logging`), purga por expiración y deduplicación LRU en memoria RAM.
- **LoRa TX Rate Limiter con Cola de Prioridades**: Espaciado adaptativo según el cálculo analítico de tiempo en el aire LoRa de Semtech (`estimate_lora_airtime_ms`).
- **Serial Watchdog Activo**: Detección automática de bloqueos silenciosos del puerto USB y autorrecuperación suave.
- **Suite Exhaustiva de 55 Pruebas Automatizadas (100% Superadas)**: Pruebas unitarias, concurrencia multihilo, simulación de flapping de red, fallas de hardware, fuzzing de payloads y endpoints web.

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
│   ├── __init__.py                   # Exportaciones públicas de interfaz v3.0
│   ├── __main__.py                   # Entrypoint 'python -m src'
│   ├── bridge_core.py                # Orquestador central MeshCoreBridge
│   ├── contact_manager.py            # Registro dinámico de nodos, métricas top y libreta
│   ├── mqtt_client.py                # Cliente MQTT asíncrono puenteado
│   ├── protocol_types.py             # Dataclasses inmutables y tipadas con CRC-16
│   ├── rate_limiter.py               # Rate Limiter con PriorityQueue y LoRa Airtime
│   ├── repeater_manager.py           # Gestor de repetidores remotos y RF sniffer
│   ├── sensor_decoder.py             # Decodificador CayenneLPP para sensores ambientales
│   ├── serial_driver.py              # Adaptadores de comunicación serial y Watchdog
│   ├── store_forward.py              # SQLiteStoreAndForward con TTL y deduplicación
│   └── web/                          # Subsistema del Servidor Web y Cliente SPA
│       ├── __init__.py               # Exportaciones de MeshCoreWebServer y WebAPIRouter
│       ├── api_router.py             # Enrutador REST API para contactos, canales, sniffer y métricas
│       ├── http_server.py            # Servidor HTTP 1.1 y WebSocket Hub asíncrono
│       └── static/                   # Assets estáticos de la interfaz web
│           ├── index.html            # Maquetación semántica SPA accesible (WCAG 2.2)
│           ├── css/app.css           # Sistema de diseño moderno en Vanilla CSS
│           └── js/app.js             # Lógica reactiva Vanilla JS y WebSocket
├── docs/                             # Documentación técnica completa
│   ├── ARCHITECTURE.md               # Diagramas Mermaid v3.0, clases y flujos
│   ├── PROTOCOL_SPEC.md              # Especificación de tramas binarias y contratos JSON
│   └── reference_analysis/           # Análisis técnico profundo de repositorios MeshCore
├── reference/                        # Repositorios oficiales de referencia (SSoT)
└── tests/                            # 55 Suites de pruebas unitarias y fuzzing
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

### Ejecutar Verificación Completa de Calidad (`bridge_test_runner`):
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py
```

### Ejecutar Simulación Interactiva en Vivo (Con Nodos Alpha, Bravo y Auto-Echo):
```bash
python run_interactive_demo.py
```

### Ejecutar Suite E2E & Automatización Visual con Playwright:
```bash
# Ejecutar suite de pruebas de integración en navegador real
pytest -v tests/test_e2e_playwright.py

# Inspección visual automática y capturas Desktop/Mobile (1920x1080 / 390x844)
python scripts/inspect_web.py --url http://localhost:8080
```
