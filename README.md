# MeshCore Universal Bridge & Web Station v3.0 Pro

Puente bidireccional asíncrono, resiliente y de grado industrial para conectar transceptores de radio **MeshCore Companion USB / TCP (v1.17+)** (**Heltec v2/v3/v4**, **LilyGO T-Beam/T-Echo**, **RAKwireless WisBlock**, **Seeed Studio**, **Raspberry Pi RP2040**) con **MQTT (Mosquitto)**, flujos de automatización en **n8n**, y una **Estación Web SPA Reactiva Moderna (HTML5, Vanilla CSS, ES6+)** con **Centro de Control de Repetidores**, **Consola CLI Interactiva**, **Autenticación API Key** y **Paleta de Comandos (`Ctrl+K`)**.

---

## 📻 Dispositivos LoRa Compatibles

- **Heltec Automation**: WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket.
- **Seeed Studio**: SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield LoRa SX1262 / RP2040.
- **Puertos Remotos TCP**: Conexión transparente por red `tcp://host:port` (MeshCore sobre TCP/WiFi/Ethernet).

---

## 🚀 Características Principales (v3.0 Pro)

- **🌐 Cliente Web Station SPA Integrado (`http://<IP>:8080`)**:
  - Interfaz ultraligera sin dependencias pesadas (< 10 MB RAM, arranque instantáneo en < 50ms).
  - Cumplimiento **WCAG 2.2 AA** con navegación 100% por teclado, foco visible `:focus-visible` y `prefers-reduced-motion`.
  - **Paleta de Comandos (`Ctrl+K` / `⌘K`)**: Acceso rápido a cualquier sección, comandos de administración y descubrimiento.
  - **WebSocket Hub RFC 6455 Resiliente**:
    - Reconexión con retroceso exponencial (*exponential backoff*).
    - Soporte automático *Same-Origin* y subredes LAN privadas (`192.168.*`, `10.*`, `172.16-31.*`).
    - *Heartbeat* bidireccional (Ping/Pong cada 15s) para mantener viva la conexión a través de routers y firewalls.
    - Indicador de estado de conexión visual (`⬤ Conectado` / `⬤ Reconectando…`).
  - **Gestión Unificada del Directorio de Nodos**:
    - Deduplicación estricta de la Estación Base local (aparece exactamente una vez con distintivo *Base Station*).
    - Fusión inteligente de alias, nombres y prefijos de claves públicas en $O(1)$.
  - **Mensajería Multi-Canal y DMs Aislados**:
    - Transmisión inmediata en canales públicos (Canales 0..7) con confirmación RF `✓ TX`.
    - Mensajes directos (DMs) punto a punto con seguimiento de ACK por radio (25s) y acuse `✓✓ Entregado`.
  - **Centro de Control de Repetidores LoRa**:
    - 📋 *Telemetría de Hardware*: Batería, voltaje solar, SNR, RSSI y tiempo activo (*uptime*).
    - 📻 *Ajustes de Radio RF*: Frecuencia, potencia TX (dBm), Spreading Factor (SF7..SF12) y ancho de banda.
    - 🌐 *Vecinos y Topología*: Tabla de vecinos directos con sondeo `discover.neighbors` y acceso directo a chat DM.
    - 💻 *Terminal Interactiva*: Consola CLI con historial de comandos (`ArrowUp`/`ArrowDown`), botones rápidos y ejecución de comandos directos.
  - **Mapa GPS Interactivo** (Leaflet) con detección de coordenadas en tiempo real de nodos y routers, con soporte de mapas locales *offline*.
  - **📈 Tablero de Métricas Avanzadas**: Top Nodos por Tráfico, Top Repetidores por Calidad de Enlace y Rendimiento del Puente.
- **🔐 Seguridad y Control de Acceso**:
  - Autenticación opcional mediante cabecera `X-Api-Key` (`BRIDGE_API_KEY`) para proteger endpoints mutantes y transmisión RF.
  - Gestión visual de API Key en **⚙️ Ajustes ➔ 🔐 Seguridad & API**.
  - Servidor TCP Companion con límite de conexiones concurrentes (`MAX_COMPANION_CLIENTS`), lista blanca de IPs y token de autenticación.
  - Políticas de seguridad CORS estrictas y cabeceras CSP (*Content-Security-Policy*).
  - Sanitización HTML contra ataques XSS y 100% consultas SQL parametrizadas en SQLite.
- **🩺 Motor de Diagnósticos Preflight (`src/preflight.py`)**:
  - Verificaciones automáticas previas al arranque (Broker Mosquitto TCP, Puerto Serial / TCP, Servidor Companion).
- **Decodificador Nativo CayenneLPP (`src/sensor_decoder.py`)**:
  - Soporte para `pycayennelpp>=2.0.0` (v2.4.0) con deserialización determinista de temperatura, humedad, presión, GPS, acelerómetro, luminosidad y voltaje.
- **LoRa TX Rate Limiter con Cola de Prioridades y Airtime Tracking**:
  - Espaciado adaptativo según el cálculo analítico de tiempo en el aire LoRa de Semtech (`estimate_lora_airtime_ms`).
- **Persistencia en SQLite WAL (`data/meshcore_buffer.db`)**:
  - Cola Store & Forward no bloqueante para reintentos y tolerancia a caídas de red.
- **Serial Watchdog Activo**:
  - Detección automática de bloqueos silenciosos del puerto USB y reconexión automática con estabilización USB CDC.

---

## 📁 Estructura del Proyecto

```
meshcore-bridge/
├── config.py                         # Carga, tipado y validación estricta de variables de entorno
├── meshcore_bridge.py                # Entrypoint raíz ejecutable
├── requirements.txt                  # Dependencias Python de producción (pycayennelpp, paho-mqtt, pyserial-asyncio)
├── pyproject.toml                    # Configuración estricta de pytest, mypy y ruff
├── .env.example                      # Plantilla completa de configuración de entorno
├── .env                              # Archivo de variables de entorno activo
├── install.sh                        # Script de instalación y despliegue para Linux / Raspberry Pi
├── install.ps1                       # Script de instalación y ejecución para Windows PowerShell
├── meshcore-bridge.service           # Archivo de servicio systemd para Linux
├── n8n_workflow_meshcore.json        # Flujo de automatización exportable para n8n
├── src/                              # Código fuente modular de producción
│   ├── __init__.py                   # Exportaciones públicas del paquete
│   ├── __main__.py                   # Entrypoint 'python -m src'
│   ├── admin_handler.py              # Comandos de administración RF y repetidores remotos
│   ├── bridge_core.py                # Orquestador central MeshCoreBridge (facade/composition root)
│   ├── contact_manager.py            # Registro dinámico de nodos, métricas top y libreta
│   ├── deduplicator.py               # Deduplicador de paquetes en RAM con ventana deslizante TTL
│   ├── event_utils.py                # Extractor canónico de remitentes y utilidades de eventos
│   ├── health_reporter.py            # Reporte periódico de salud en meshcore/bridge/health
│   ├── lqi_engine.py                 # Motor de cálculo de calidad de enlace LQI (SNR/RSSI/Hops)
│   ├── mqtt_client.py                # Cliente MQTT asíncrono con soporte ReasonCodes v2.x
│   ├── mqtt_dispatcher.py            # Despachador de mensajes MQTT entrantes (TX/Admin)
│   ├── preflight.py                  # Motor de diagnósticos previos al arranque
│   ├── protocol_types.py             # Dataclasses inmutables y tipadas con CRC-16 y OpCodes
│   ├── rate_limiter.py               # Rate Limiter con PriorityQueue y LoRa Airtime Tracker
│   ├── repeater_manager.py           # Gestor de repetidores remotos y telemetría
│   ├── rx_router.py                  # Enrutador de eventos LoRa/RF → MQTT + WebSocket
│   ├── sensor_decoder.py             # Decodificador CayenneLPP para sensores ambientales
│   ├── serial_driver.py              # Adaptadores de comunicación serial, TCP y Watchdog
│   ├── tcp_companion_server.py       # Servidor TCP para Companion Apps oficiales (Android/iOS/CLI)
│   ├── virtual_mesh_adapter.py       # Emulador de hardware Heltec v4 y topología de nodos
│   └── web/                          # Subsistema del Servidor Web y Cliente SPA
│       ├── __init__.py               # Exportaciones de MeshCoreWebServer y WebAPIRouter
│       ├── api_router.py             # Enrutador REST API para contactos, canales y repetidores
│       ├── http_server.py            # Servidor HTTP 1.1 y WebSocket Hub asíncrono
│       └── static/                   # Assets estáticos de la interfaz web
│           ├── index.html            # Maquetación semántica SPA accesible (WCAG 2.2)
│           ├── css/app.css           # Sistema de diseño Cyberpunk Slate en Vanilla CSS
│           └── js/app.js             # Lógica reactiva Vanilla JS y WebSocket
├── scripts/                          # Herramientas de despliegue y simuladores
│   ├── sync_deploy.py                # Generador del paquete de distribución autónomo (/deploy/)
│   ├── simulate_mesh_network.py      # Simulación determinista multi-nodo de red LoRa
│   ├── simulate_heltec_v4_mesh.py    # Simulador en vivo de hardware Heltec v4 y red LoRa
│   └── inspect_web.py                # Automatización de capturas Playwright Desktop/Mobile
├── docs/                             # Documentación técnica completa
│   ├── ARCHITECTURE.md               # Diagramas de arquitectura v3.0, clases y flujos
│   ├── PROTOCOL_SPEC.md              # Especificación de tramas binarias y contratos JSON
│   ├── DEPLOYMENT_GUIDE.md           # Guía paso a paso de instalación en Linux/Raspberry Pi
│   ├── CODE_EXPLANATION.md           # Explicación detallada de módulos y patrones
│   └── AGENT_ACTIVITY_REPORT.md      # Registro de actividad y cambios multi-agente
├── deploy/                           # Paquete autónomo de instalación en producción
└── tests/                            # Suites de pruebas automatizadas (bajo demanda)
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
# Para actualizar una instalación existente conservando .env y base de datos:
sudo bash install.sh --update
```

### En Windows (PowerShell):
```powershell
.\install.ps1 -InstallDeps -Run
```

### Iniciar el Bridge Manualmente:
```bash
python -m src
# O usando el archivo raíz:
python meshcore_bridge.py
```

### Ejecutar Simulación Interactiva en Vivo (Heltec v4 + 8 Nodos LoRa):
```bash
# Servidor web simulado en http://localhost:8085:
python scripts/simulate_heltec_v4_mesh.py --live
```

---

## ⚙️ Variables de Entorno Principales (`.env`)

| Variable | Por Defecto | Descripción |
| :--- | :--- | :--- |
| `SERIAL_PORT` | `AUTO` | Puerto serie USB (`/dev/ttyACM0`, `COM3` o `AUTO`). |
| `BAUD_RATE` | `115200` | Velocidad de comunicación en baudios. |
| `MQTT_BROKER` | `127.0.0.1` | Dirección IP o host del broker Mosquitto. |
| `MQTT_PORT` | `1883` | Puerto TCP del broker MQTT. |
| `TOPIC_PREFIX`| `meshcore` | Prefijo raíz de tópicos MQTT. |
| `WEB_ENABLED` | `true` | Habilitar/Deshabilitar servidor web SPA integrado. |
| `WEB_PORT` | `8080` | Puerto HTTP para la interfaz web y API REST. |
| `BRIDGE_API_KEY` | *(vacía)* | Clave de autenticación API para el frontend/REST. |
| `BRIDGE_ALLOWED_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | Orígenes CORS (LAN autorizada automáticamente). |
| `TCP_SERVER_ENABLED` | `true` | Habilitar servidor TCP Companion. |
| `TCP_SERVER_PORT` | `5000` | Puerto TCP para Companion Apps (Android/iOS). |
| `MAX_COMPANION_CLIENTS` | `8` | Límite de conexiones simultáneas TCP companion. |
| `LORA_DEFAULT_SF` | `11` | Spreading Factor por defecto (SF7 a SF12). |
| `LORA_DEFAULT_BW_KHZ` | `250.0` | Ancho de banda LoRa en kHz. |
| `TX_INTERVAL_SEC` | `1.0` | Espaciado mínimo entre paquetes RF (Rate Limiter). |
| `SQLITE_DB_PATH` | `data/meshcore_buffer.db` | Ruta del archivo de persistencia SQLite. |
| `LOG_LEVEL` | `INFO` | Nivel de registro (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

