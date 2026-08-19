# MeshCore Universal Bridge & Web Station v3.0

Puente bidireccional asíncrono, resiliente y de grado industrial para conectar nodos de radio **MeshCore Companion USB / TCP (v1.17+)** (**Heltec v2/v3/v4**, **LilyGO TTGO**, **RAKwireless WisBlock**, **Seeed Studio**, **Raspberry Pi RP2040**) con **MQTT (Mosquitto)**, integración nativa de **Home Assistant (MQTT Auto-Discovery)**, flujos de automatización en **n8n** y una **Interfaz Web SPA Moderna (HTML5, Vanilla CSS, ES6+)** con **Centro de Control de Repetidores**, **RF Packet Sniffer** y **Paleta de Comandos (`Ctrl+K`)**.

---

## 📻 Dispositivos LoRa Compatibles

- **Heltec Automation**: WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket.
- **Seeed Studio**: SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield LoRa SX1262 / RP2040.
- **Puertos Remotos TCP**: Conexión transparente por red `tcp://host:port` (MeshCore sobre TCP/WiFi/Ethernet).

---

## 🚀 Características Principales (v3.0)

- **🌐 Cliente Web Station SPA Integrado (`http://<IP>:8080` / `8085`)**:
  - Interfaz ultraligera sin frameworks pesados (< 10 MB RAM, arranque en < 50ms).
  - Cumplimiento **WCAG 2.2 AA** con navegación 100% por teclado, foco visible `:focus-visible` y `prefers-reduced-motion`.
  - **Paleta de Comandos (`Ctrl+K` / `⌘K`)**: Acceso rápido a cualquier sección, comandos de administración y descubrimiento.
  - **Centro de Control de Repetidores LoRa**:
    - 📋 *Info de Nodo*: Batería, voltaje solar, SNR, RSSI y uptime.
    - 📻 *Ajustes de Radio RF*: Frecuencia, potencia TX (dBm), Spreading Factor (SF7-SF12) y ancho de banda.
    - 🌐 *Vecinos y Malla*: Tabla de vecinos directos con sondeo `discover.neighbors` y acceso directo a DM.
    - 💻 *Consola Terminal Interactiva*: Stream en vivo y botones de comando rápido (`stats-radio`, `stats-core`, `stats-packets`, `neighbors`, `reboot`).
  - **Chat Multi-Canal y DMs Aislados**: Canal Público 0, Canales Privados 1..7 (Cifrado AES) y Mensajes Directos (DMs) sin mezcla de conversaciones.
  - **Mapa GPS Interactivo** (Leaflet) con detección de coordenadas en tiempo real de nodos y routers.
  - **🕵️ RF Packet Sniffer & Analizador Wire (`0x88 LOG_DATA`)**: Captura e inspección profunda de tramas LoRa en el aire con modal de volcado hexadecimal y JSON estructurado.
  - **📈 Tablero de Métricas Avanzadas & Estadísticas**: Top Nodos por Tráfico, Top Repetidores por Calidad de Enlace y Rendimiento del Puente.
- **🏠 Integración Home Assistant (MQTT Auto-Discovery)**:
  - Generación y publicación automática de entidades estándar en `homeassistant/sensor/#` y `homeassistant/binary_sensor/#` (Batería, Voltaje Solar, SNR, RSSI, Saltos y Salud del Puente).
- **🩺 Motor de Diagnósticos Preflight (`src/preflight.py`)**:
  - Verificaciones automáticas previas al arranque (Broker Mosquitto TCP, Base de datos SQLite WAL, Puerto Serial / TCP).
- **🔌 API REST JSON & WebSocket Hub**: Endpoints completos con soporte CORS preflight `OPTIONS` y WebSockets en tiempo real.
- **Decodificador Nativo CayenneLPP (`src/sensor_decoder.py`)**: Deserialización determinista de telemetría ambiental (temperatura, humedad, presión, GPS, acelerómetro y voltaje).
- **Directorio Dinámico de Nodos (`src/contact_manager.py`)**: Registro en memoria `NodeRegistry` con resolución de alias y claves públicas en $O(1)$.
- **Store & Forward Transaccional con TTL**: Persistencia en SQLite en modo `WAL` (`Write-Ahead Logging`), purga por expiración y deduplicación LRU en memoria RAM.
- **LoRa TX Rate Limiter con Cola de Prioridades**: Espaciado adaptativo según el cálculo analítico de tiempo en el aire LoRa de Semtech (`estimate_lora_airtime_ms`).
- **Serial Watchdog Activo**: Detección automática de bloqueos silenciosos del puerto USB y autorrecuperación suave.
- **Suite Exhaustiva de 117 Pruebas Automatizadas (100% Superadas)**: Pruebas unitarias, concurrencia multihilo, simulación de flapping de red, fallas de hardware, fuzzing de payloads, endpoints web, WebSocket en vivo y **E2E con Playwright** (escritorio y móvil).

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
│   ├── admin_handler.py              # Comandos de administración RF y repetidores remotos
│   ├── bridge_core.py                # Orquestador central MeshCoreBridge (facade/composition root)
│   ├── contact_manager.py            # Registro dinámico de nodos, métricas top y libreta
│   ├── ha_discovery.py               # Generador de MQTT Auto-Discovery para Home Assistant
│   ├── health_reporter.py            # Reporte periódico de salud en meshcore/bridge/health
│   ├── mqtt_client.py                # Cliente MQTT asíncrono puenteado con Store & Forward
│   ├── mqtt_dispatcher.py            # Despachador de mensajes MQTT entrantes (TX/Admin)
│   ├── preflight.py                  # Motor de diagnósticos previos al arranque
│   ├── protocol_types.py             # Dataclasses inmutables y tipadas con CRC-16 y OpCodes
│   ├── rate_limiter.py               # Rate Limiter con PriorityQueue y LoRa Airtime
│   ├── repeater_manager.py           # Gestor de repetidores remotos y RF sniffer
│   ├── rx_router.py                  # Enrutador de eventos LoRa/RF → MQTT + WebSocket
│   ├── sensor_decoder.py             # Decodificador CayenneLPP para sensores ambientales
│   ├── serial_driver.py              # Adaptadores de comunicación serial, TCP y Watchdog
│   ├── store_forward.py              # SQLiteStoreAndForward con transacciones WAL y deduplicación
│   ├── virtual_mesh_adapter.py       # Emulador de hardware Heltec v4 y topología de 8 nodos
│   └── web/                          # Subsistema del Servidor Web y Cliente SPA
│       ├── __init__.py               # Exportaciones de MeshCoreWebServer y WebAPIRouter
│       ├── api_router.py             # Enrutador REST API para contactos, canales, repetidores y HA
│       ├── http_server.py            # Servidor HTTP 1.1 y WebSocket Hub asíncrono
│       └── static/                   # Assets estáticos de la interfaz web
│           ├── index.html            # Maquetación semántica SPA accesible (WCAG 2.2)
│           ├── css/app.css           # Sistema de diseño Cyberpunk Slate en Vanilla CSS
│           └── js/app.js             # Lógica reactiva Vanilla JS y WebSocket
├── scripts/                          # Herramientas y simuladores
│   ├── simulate_heltec_v4_mesh.py    # Simulador en vivo de hardware Heltec v4 y red LoRa
│   └── inspect_web.py                # Automatización de capturas Playwright Desktop/Mobile
├── docs/                             # Documentación técnica completa
│   ├── ARCHITECTURE.md               # Diagramas Mermaid v3.0, clases y flujos
│   ├── PROTOCOL_SPEC.md              # Especificación de tramas binarias y contratos JSON
│   └── reference_analysis/           # Análisis técnico de repositorios MeshCore
├── reference/                        # Repositorios de referencia analizados (SSoT)
└── tests/                            # 117 Pruebas unitarias, fuzzing, concurrencia y E2E
```

---

## 📡 Mapa de Tópicos MQTT para n8n y Home Assistant

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
| `homeassistant/sensor/#` | Auto-Discovery | Bridge ➔ HA | Configuración MQTT Discovery de sensores de nodos. |
| `homeassistant/binary_sensor/#` | Auto-Discovery | Bridge ➔ HA | Sensor de conectividad Online/Offline del Bridge. |

---

## ⚡ Instalación y Despliegue en 1 Comando

### En Linux (Orange Pi / Raspberry Pi / Ubuntu / Debian):
```bash
sudo bash install.sh
# Con tooling de desarrollo/auditoría (pytest, mypy, ruff, bandit, playwright):
sudo bash install.sh --dev
```

### En Windows (PowerShell):
```powershell
.\install.ps1 -InstallDeps -Run
# Con tooling de desarrollo/auditoría:
.\install.ps1 -InstallDev
```

### Ejecutar Verificación Completa de Calidad (`bridge_test_runner`):
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py
```

### Ejecutar Auditorías Especializadas (Seguridad, API, Clean Code, Frontend):
```bash
python .agents/skills/security-code-auditor/scripts/run_security_audit.py   # Bandit + SQLi + Traversal + XSS
python .agents/skills/api-design-testing/scripts/validate_api_contract.py   # Contratos REST y códigos HTTP
python .agents/skills/clean-code-solid/scripts/detect_code_smells.py       # God Class / SOLID / Métricas
python .agents/skills/html-css-modern-js/scripts/lint_frontend_standards.py # HTML5 / CSS3 / JS moderno
python .agents/skills/python-patterns-typing/scripts/verify_python_standards.py # Tipado estricto PEP 8
```

### Ejecutar Simulación Interactiva en Vivo (Heltec v4 + 8 Nodos LoRa):
```bash
# Ejecución continua con servidor Web en http://localhost:8085:
python scripts/simulate_heltec_v4_mesh.py --live
```

### Ejecutar Suite E2E & Automatización Visual con Playwright:
```bash
# Ejecutar suite de pruebas de integración en navegador real:
pytest -v tests/test_e2e_playwright.py
```
