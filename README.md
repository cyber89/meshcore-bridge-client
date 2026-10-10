# MeshCore Universal Bridge & Web Station v3.0 Pro

Puente asíncrono bidireccional para conectar transceptores LoRa **MeshCore Companion (USB / TCP)** con **FastAPI ASGI**, **MQTT**, automatizaciones **n8n / Home Assistant** y una **SPA Web en HTML5, Vanilla CSS y JavaScript**.

El servidor web seleccionado por el core es FastAPI/Uvicorn ASGI; el servidor HTTP nativo fue retirado y no existe conmutación automática hacia él. El servicio incorpora un proxy TCP Companion para aplicaciones móviles oficiales. La auditoría del 2026-10-09 revisa código y documentación sin ejecutar suites: la selección del backend no acredita paridad operativa, rendimiento ni compatibilidad de cada plataforma.

---

## 📻 Dispositivos LoRa Compatibles

Compatible con el ecosistema de hardware oficial soportado por el firmware MeshCore Companion:

- **Heltec Automation**: WiFi LoRa 32 (v2, v3, v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1, v1.2, Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub y Pocket.
- **Seeed Studio**: SenseCAP Indicator, SenseCAP Tracker, Wio-E5, Xiao ESP32-S3, Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield SX1262 / RP2040.
- **Puertos Remotos TCP**: Conexión directa y transparente sobre red local o VPN (`tcp://host:port`).

---

## 🚀 Características Principales

### 🌐 Servidor Web (`http://<IP>:8080`)
- **Pila ASGI de Producción (Uvicorn 0.54 + FastAPI 0.143 + Pydantic 2.14)**:
  - Rutas REST registradas en FastAPI que reciben `Request` y delegan en los controladores existentes. Los DTO Pydantic describen campos para OpenAPI; conservan `Any` y campos extra, y no validan ni filtran las solicitudes en ejecución.
  - Documentación interactiva de la API OpenAPI 3.1 autónoma y offline:
    - **Visor propio**: `http://<IP>:8080/docs`
    - **Alias del mismo visor**: `http://<IP>:8080/redoc`
    - **Esquema OpenAPI JSON**: `http://<IP>:8080/openapi.json`
- **WebSocket Hub Resiliente (RFC 6455)**:
  - Actualización en vivo de chat, telemetría, sniffer y estado de la red.
  - Reconexión con *exponential backoff* y latidos *heartbeat* periódicos (Ping/Pong cada 15s).
  - Política Origin compatible con el servidor anterior: permite orígenes configurados, coincidencia con Host, loopback y subredes LAN privadas. No constituye una política estricta de mismo origen.

El visor es HTML/CSS/JS local, de consulta; no incorpora los paquetes Swagger UI o ReDoc ni ejecuta operaciones del catálogo. Con `BRIDGE_API_KEY`, el esquema requiere `X-Api-Key` y la pantalla permite introducirla en memoria del visor.

### 📱 Servidor TCP Companion para App Móvil Oficial (`puerto 5000`)
- Permite conectar la **aplicación oficial MeshCore para Android/iOS** o herramientas CLI al transceptor compartido y coordina los comandos mediante el arbitraje Companion.
- Lista blanca opcional de IPs permitidas y token de autenticación.

### 🔄 Integración MQTT Dual (Comunitaria y Domótica)
- **Broker Externo / Comunitario**: Reenvío pasivo de telemetría y anuncios a redes comunitarias como LetsMesh.net con privacidad por geofuzzing.
- **Broker Local (n8n & Home Assistant)**: Tópicos estructurados para automatizaciones en tiempo real, alarmas y sensores con acuses de recibo (ACK).

### 💬 Mensajería y Red LoRa
- **Canales Públicos y Privados**: Soporte de canal primario (Canal 0) y canales secundarios con cifrado AES-128.
- **Mensajería Directa (DM)**: Enrutamiento punto a punto con seguimiento de confirmación de entrega (`✓✓ Entregado`).
- **Directorio Canónico de Nodos**: Separación estricta de infraestructura (los repetidores nunca aparecen en la libreta de contactos ni reciben chat de texto; la estación local no puede ser bucle de envío).
- **Consola de Repetidores**: Lectura y ajuste remoto de parámetros RF (frecuencia, potencia TX, Spreading Factor, ancho de banda), telemetría de batería y voltaje solar, tabla de vecinos y terminal interactiva.

### 🛡️ Protecciones de la Malla y Calidad de Señal
- **Rate Limiter Priorizado y Airtime Tracker**: Espaciado de TX y estimación de airtime; en estado crítico puede descartar prioridad `LOW`. No bloquea toda transmisión ni certifica cumplimiento regulatorio.
- **Deduplicador en Memoria**: Eliminación de ecos y tormentas de retransmisión con ventana deslizante TTL.
- **Decodificador Nativo CayenneLPP**: Extracción de temperatura, humedad, presión barométrica, GPS y aceleración sin dependencias externas pesadas.
- **Mapas Offline MBTiles**: Servicio de archivos XYZ y cartografía MBTiles local para uso sin acceso a Internet.

---

## 📁 Estructura del Proyecto

```
meshcore-bridge/
├── config.py                         # Variables de entorno y validación seleccionada de configuración
├── meshcore_bridge.py                # Punto de entrada ejecutable principal
├── requirements.txt                  # Dependencias de producción (MQTT, SDK, FastAPI, Uvicorn)
├── pyproject.toml                    # Metadatos del proyecto y configuración estricta de QA
├── .env.example                      # Plantilla documentada de variables de entorno
├── install.sh                        # Instalador y actualizador para Linux / Raspberry / Orange Pi
├── install.ps1                       # Instalador y ejecutor para Windows PowerShell
├── meshcore-bridge.service           # Definición de servicio systemd para Linux
├── n8n_workflow_meshcore.json        # Flujo de automatización exportable para n8n
├── src/                              # Código fuente modular de producción
│   ├── bridge_core.py                # Orquestador central MeshCoreBridge (Fachada del sistema)
│   ├── contact_manager.py            # Registro canónico de nodos y libreta de contactos
│   ├── deduplicator.py               # Deduplicador de tramas LoRa en memoria
│   ├── diagnostics.py                # Métricas de salud y subsistema de diagnóstico
│   ├── lqi_engine.py                 # Motor de cálculo de calidad de enlace LQI (SNR/RSSI/Hops)
│   ├── mqtt_client.py                # Cliente MQTT asíncrono con reconexión automática
│   ├── mqtt_dispatcher.py            # Despachador de mensajes MQTT entrantes
│   ├── packet_buffer.py              # Búfer circular de paquetes para sniffer y auditoría
│   ├── preflight.py                  # Verificación diagnóstica previa al arranque
│   ├── protocol_types.py             # Enums canónicos y contratos de tramas MeshCore
│   ├── rate_limiter.py               # Cola de prioridad TX y monitor de airtime
│   ├── repeater_manager.py           # Gestor administrativo de repetidores remotos
│   ├── rx_router.py                  # Enrutador reactivo de eventos LoRa hacia MQTT y WebSocket
│   ├── sensor_decoder.py             # Decodificador de telemetría CayenneLPP
│   ├── serial_driver.py              # Controlador de comunicación serie y watchdog USB
│   ├── tcp_companion_server.py       # Servidor TCP Companion para apps Android/iOS/CLI
│   ├── admin/                        # Ejecutores de comandos administrativos (Command Pattern)
│   ├── routers/                      # Estrategias de enrutamiento por tipo de paquete (Strategy Pattern)
│   └── web/                          # Subsistema Web (FastAPI ASGI)
│       ├── api_router.py             # Enrutador unificado de la API REST
│       ├── asgi_server.py            # Servidor FastAPI / Uvicorn ASGI de producción
│       ├── asgi_routes.py            # Adaptadores de rutas REST modulares
│       ├── asgi_ws_hub.py            # Hub de WebSockets resiliente
│       ├── asgi_docs.py              # Esquema OpenAPI y visor propio offline
│       ├── map_tile_service.py       # Servicio local de teselas de mapas offline MBTiles
│       ├── controllers/              # Controladores REST modulares
│       ├── docs_ui/                  # Frontend estático offline de la documentación OpenAPI
│       └── static/                   # SPA accesible en Vanilla HTML5, CSS y JavaScript
├── docs/                             # Documentación técnica y especificaciones
│   ├── README.md                     # Índice maestro de documentación
│   ├── ARCHITECTURE.md               # Arquitectura del sistema y diseño en 5 capas
│   ├── PROTOCOL_SPEC.md              # Especificación técnica del protocolo y tramas
│   ├── DEPLOYMENT_GUIDE.md           # Guía completa de instalación y producción
│   ├── N8N_WORKFLOW_GUIDE.md         # Guía de integración con n8n y esquemas MQTT
│   ├── TESTING.md                    # Guía de pruebas automatizadas y QA
│   ├── adr/                          # Registros de Decisiones de Arquitectura (ADR 0001 - 0011)
│   ├── fastapi/                      # Informes de migración por fases FastAPI ASGI
│   └── diagrams/                     # Diagramas interactivos de arquitectura (Archify)
├── CONTEXT.md                        # Lenguaje ubicuo e invariantes de dominio (SSoT)
└── tests/                            # Suites de pruebas automatizadas (pytest)
```

---

## ⚡ Instalación Rápida

### En Linux (Debian / Ubuntu / Raspberry Pi / Orange Pi)

El instalador raíz `install.sh` automatiza la creación del entorno virtual, instalación de dependencias y configuración del servicio `systemd`:

```bash
# 1. Clonar el repositorio
git clone https://github.com/cyber89/meshcore-bridge-client.git /opt/meshcore-bridge
cd /opt/meshcore-bridge

# 2. Ejecutar el instalador
sudo bash install.sh

# 3. Para actualizar una instalación existente conservando datos y .env:
sudo bash install.sh --update
```

### En Windows (PowerShell)

```powershell
.\install.ps1 -InstallDeps -Run
```

### Manualmente con Entorno Virtual de Python:

```bash
# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\Activate.ps1

# Instalar dependencias de producción
pip install -r requirements.txt

# Iniciar el puente
python meshcore_bridge.py
```

---

## ⚙️ Configuración (`.env`)

Copia la plantilla `.env.example` a `.env` y ajusta los parámetros necesarios:

| Variable | Valor por Defecto | Descripción |
| :--- | :--- | :--- |
| `SERIAL_PORT` | `AUTO` | Puerto serie USB (`/dev/ttyACM0`, `COM3`, o `AUTO`) o túnel TCP (`tcp://host:port`). |
| `BAUD_RATE` | `115200` | Velocidad en baudios para la conexión serial. |
| `WEB_ENABLED` | `true` | Habilita la interfaz web y la API REST. |
| `WEB_PORT` | `8080` | Puerto HTTP para la SPA, API REST y WebSockets. |
| `BRIDGE_API_KEY` | *(opcional)* | Clave de seguridad para autenticar peticiones REST mutantes y visor de docs. |
| `TCP_SERVER_ENABLED` | `true` | Habilita el servidor TCP Companion para apps móviles MeshCore. |
| `TCP_SERVER_PORT` | `5000` | Puerto de escucha para conexiones Companion (Android / iOS / CLI). |
| `MQTT_BROKER` | `127.0.0.1` | Dirección IP del broker MQTT local. |
| `MQTT_PORT` | `1883` | Puerto del broker MQTT local. |
| `TOPIC_PREFIX` | `meshcore` | Prefijo raíz de los tópicos MQTT. |
| `DATA_DIR` | `data` | Carpeta de persistencia para canales, nodos, airtime y teselas. |
| `LOG_LEVEL` | `INFO` | Nivel de detalle de registros (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 🌐 Endpoints y Rutas Principales

| Recurso | URL / Método | Descripción |
| :--- | :--- | :--- |
| **Interfaz Web SPA** | `GET http://<IP>:8080/` | Panel de control completo (Chat, Nodos, Repetidores, Mapas, Métricas). |
| **Visor OpenAPI** | `GET http://<IP>:8080/docs` | Visor propio offline para consultar el contrato. |
| **Alias del visor** | `GET http://<IP>:8080/redoc` | La misma interfaz; no es el paquete ReDoc. |
| **OpenAPI JSON** | `GET http://<IP>:8080/openapi.json` | Especificación canónica OpenAPI 3.1.0 para generadores de clientes. |
| **WebSocket Hub** | `ws://<IP>:8080/ws` | Flujo bidireccional en tiempo real de eventos, chat y telemetría. |
| **TCP Companion** | `tcp://<IP>:5000` | Interfaz TCP directa para la aplicación oficial de MeshCore. |
| **Salud del Sistema** | `GET /api/health` | Estado del bridge, transceptor, estadísticas y uptime. |
| **Nodos y Contactos** | `GET /api/contacts` | Listado normalizado de contactos (excluye repetidores). |
| **Transmitir Mensaje** | `POST /api/tx` | Envío de mensajes de canal o directos (DM). |
| **Administrar Repetidor** | `POST /api/admin/repeater` | Despacho de comandos administrativos remotos. |

---

## 📡 Tópicos MQTT para Automatización (n8n & Home Assistant)

| Tópico | Dirección | Contenido |
| :--- | :--- | :--- |
| `meshcore/bridge/state` | Bridge ➔ Broker | Estado del servicio (`online` / `offline` vía LWT retenido). |
| `meshcore/bridge/health`| Bridge ➔ Broker | Métricas periódicas de salud, nodos activos y cola TX. |
| `meshcore/rx/all` | Bridge ➔ Broker | **Stream unificado**: Todos los paquetes recibidos en formato JSON normalizado. |
| `meshcore/rx/public` | Bridge ➔ Broker | Mensajes recibidos en el canal público (Canal 0). |
| `meshcore/rx/direct/+` | Bridge ➔ Broker | Mensajes directos (DMs) recibidos por remitente. |
| `meshcore/rx/telemetry` | Bridge ➔ Broker | Telemetría de batería, voltaje, solar y sensores CayenneLPP. |
| `meshcore/tx` | n8n ➔ Bridge | Petición para transmitir un mensaje por la radio LoRa. |
| `meshcore/tx/status` | Bridge ➔ n8n | Confirmación de transmisión y acuse de recibo (`sent`, `ack`, `error`). |

---

## 🧪 Pruebas y Aseguramiento de Calidad

> **Nota de protocolo**: Conforme a [`AGENTS.md`](AGENTS.md), las suites de pruebas automatizadas no se ejecutan automáticamente durante tareas de desarrollo rutinarias para proteger la estabilidad operativa. Se ejecutan únicamente bajo demanda explícita.

Para ejecutar la verificación de calidad en un entorno de desarrollo:

```bash
# Ejecutar suite de pruebas pytest
python -m pytest tests -ra

# Verificación de tipos estricta con mypy
python -m mypy --strict src

# Linter y análisis estático con ruff
python -m ruff check src

# Verificación de integridad documental y enlaces
python scripts/validate_project_docs.py
```

---

## 📄 Licencia

Este proyecto se distribuye bajo la Licencia MIT. Consulta el archivo de licencia para más detalles.
