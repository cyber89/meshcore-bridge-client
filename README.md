# MeshCore Universal Bridge: LoRa Companion USB <-> MQTT <-> n8n

Puente bidireccional asíncrono, resiliente y de grado industrial para conectar nodos de radio **MeshCore Companion USB (v1.17+)** (**Heltec**, **LilyGO TTGO**, **RAKwireless WisBlock**, **Seeed Studio**, **Raspberry Pi RP2040**) con un broker **MQTT (Mosquitto)** y flujos de automatización en **n8n**.

---

## 📻 Dispositivos LoRa Compatibles

- **Heltec Automation**: WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule.
- **LilyGO (TTGO)**: T-Beam (v1.1/v1.2/Supreme), T-Echo (nRF52840), T3S3, T-Deck, LoRa32.
- **RAKwireless WisBlock**: RAK4631 (nRF52840), RAK11200, RAK11310 (RP2040), WisMesh Hub/Pocket.
- **Seeed Studio**: SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / Xiao nRF52840.
- **Raspberry Pi**: Pico / Pico W con shield LoRa SX1262 / RP2040.

---

## 🚀 Características Principales

- **Conexión Serial Asíncrona Resiliente**: Reconexión automática ante desconexiones USB o reinicios de nodo con `asyncio`.
- **Integración con MeshCore v1.17**: Manejo de eventos nativos de canal, mensajes directos (DMs), anuncios de nodos y telemetría (batería, voltaje, temperatura, RSSI, SNR, saltos).
- **Publicación MQTT Híbrida**: Publica en tópicos específicos (`meshcore/rx/public`, `meshcore/rx/channel/...`, `meshcore/rx/direct/...`, `meshcore/rx/telemetry`) y en un tópico unificado (`meshcore/rx/all`).
- **Transmisión Bidireccional (TX) con ACKs**: Acepta texto plano o JSON con `request_id` y emite confirmación de entrega en `meshcore/tx/status`.
- **Suite Administrativa por MQTT**: Comandos `get_config`, `get_contacts`, `set_name`, `set_tx_power`, `req_telemetry` y `reboot` a través de `meshcore/admin/cmd` y `meshcore/admin/status`.
- **Last Will and Testament (LWT)**: Publicación retenida de estado `online` / `offline` en `meshcore/bridge/state`.
- **Buffer Persistente SQLite Store-and-Forward (Cero Pérdida de Datos)**: Retención de mensajes en base de datos SQLite local (`WAL mode`) durante caídas de MQTT, resistente a reinicios y cortes eléctricos.
- **LoRa TX Rate Limiter**: Control de congestión RF con espaciado de transmisión (`TX_INTERVAL_SEC=1.0s`).
- **Serial Watchdog Activo**: Detección automática de bloqueos silenciosos del chip USB y autorrecuperación.
- **Telemetría de Salud en Vivo**: Publicación en tiempo real de estadísticas de rendimiento en `meshcore/bridge/health`.
- **Suite Exhaustiva de 28 Pruebas Automatizadas (100% Superadas)**: Pruebas unitarias, concurrencia multihilo, simulación de flapping de red, fallas de hardware, fuzzing de payloads, inyección SQL y matriz de flujos n8n.

---

## 📁 Estructura del Proyecto

```
meshcore-bridge/
├── config.py                         # Carga de variables de entorno y configuración
├── meshcore_bridge.py                # Script principal del servicio bridge (SQLite, Rate Limiter, Watchdog)
├── requirements.txt                  # Dependencias Python
├── .env.example                      # Plantilla de configuración con variables de SQLite y resiliencia
├── install.sh                        # Script de despliegue y actualización en 1 comando (--update / --uninstall)
├── meshcore-bridge.service           # Archivo de servicio systemd para Linux
├── n8n_workflow_meshcore.json        # Workflow exportable listo para importar en n8n
├── docs/
│   ├── DEPLOYMENT_GUIDE.md           # Guía paso a paso de despliegue en Linux / systemd
│   └── CODE_EXPLANATION.md           # Explicación técnica y arquitectura del código
├── tests/
│   ├── test_bridge_logic.py          # Pruebas de parsing y deduplicación
│   ├── test_store_and_forward.py     # Pruebas de buffer persistente SQLite y reinicios
│   ├── test_tx_rate_limiter.py       # Pruebas de rate limiter LoRa y ACKs
│   ├── test_serial_watchdog.py       # Pruebas del watchdog serial
│   ├── test_e2e_simulation.py        # Simulación End-to-End completa
│   ├── test_stress_flood.py          # Pruebas de estrés y ráfagas masivas
│   ├── test_fuzzing_and_edge_cases.py# Fuzzing de entradas, inyección SQL y valores extremos
│   ├── test_concurrency_and_flapping.py # Concurrencia multihilo y micro-cortes de red
│   └── test_n8n_parser_matrix.py     # Matriz de deserialización y deduplicación n8n
└── README.md                         # Este archivo
```

---

## 📡 Mapa de Tópicos MQTT

| Tópico | Tipo | Dirección | Descripción |
| :--- | :--- | :--- | :--- |
| `meshcore/bridge/state` | Estado | Bridge ➔ Broker | Estado `online`/`offline` (Retained LWT). |
| `meshcore/rx/all` | Stream | Bridge ➔ Broker | **Tópico unificado**: Todos los eventos RX normalizados en JSON. |
| `meshcore/rx/public` | RX | Bridge ➔ Broker | Mensajes recibidos en el canal público (Canal 0). |
| `meshcore/rx/channel/ch_<idx>` | RX | Bridge ➔ Broker | Mensajes recibidos en canal secundario `<idx>`. |
| `meshcore/rx/direct/<sender_id>`| RX | Bridge ➔ Broker | Mensajes directos (DMs) recibidos. |
| `meshcore/rx/telemetry` | Telemetría | Bridge ➔ Broker | Batería, voltaje y métricas RF de nodos. |
| `meshcore/rx/nodes` | Anuncios | Bridge ➔ Broker | Nodos descubiertos y presencia en la malla. |
| `meshcore/tx` | TX | n8n ➔ Bridge | Petición para transmitir mensaje por RF. |
| `meshcore/tx/status` | ACK | Bridge ➔ n8n | Confirmación de transmisión RF (`sent`/`error`). |
| `meshcore/admin/cmd` | Admin | n8n ➔ Bridge | Comandos de control (`get_config`, `set_name`, etc.). |
| `meshcore/admin/status` | Admin | Bridge ➔ n8n | Resultado de comandos administrativos. |

---

## ⚡ Inicio Rápido

### Despliegue Automatizado en 1 Comando (Recomendado en Linux / Armbian):
```bash
# Instalación completa desde cero:
sudo bash install.sh

# O si ya lo tenías instalado, actualizar código sin borrar tu configuración:
sudo bash install.sh --update
```
*Este comando instala dependencias, configura Mosquitto, detecta el puerto del Heltec y activa el servicio systemd automáticamente.*

---

### Despliegue Manual:
1. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configurar variables**:
   ```bash
   cp .env.example .env
   ```
3. **Ejecutar**:
   ```bash
   python meshcore_bridge.py
   ```

Consulta la [Guía de Despliegue](docs/DEPLOYMENT_GUIDE.md) para más detalles.

5. **Para detalles técnicos y flujo de concurrencia**:
   Consulta la [Explicación del Código](docs/CODE_EXPLANATION.md).
