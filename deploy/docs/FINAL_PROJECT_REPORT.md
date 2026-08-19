# MeshCore Bridge v3.0 - Reporte Integral de Ingeniería y Auditoría de Sistema

> **Documento Consolidado de Arquitectura, Especificación de Protocolo, Seguridad Informática y Calidad de Código**  
> **Fecha de Publicación**: Agosto 2026  
> **Estado**: Producción (Ready for Deployment)  
> **Clasificación**: Grado Industrial / Telecomunicaciones & IoT  

---

## 1. Resumen Ejecutivo

**MeshCore Universal Bridge v3.0** es una solución integral y asíncrona diseñada para interconectar transceptores de radio LoRa bajo firmware **MeshCore Companion USB (v1.17+)** con plataformas de automatización empresarial (**n8n**), brokers **MQTT (Mosquitto)** y estaciones de control visual mediante una **Aplicación Web SPA Ligera en Tiempo Real**.

El sistema garantiza:
- **Cero Bloqueo en Bucle de Eventos**: Arquitectura 100% reactiva nativa en `asyncio`.
- **Resiliencia Extrema ante Fallos**: Persistencia Store & Forward transaccional en SQLite (modo `WAL`), purga por TTL y deduplicación en memoria RAM.
- **Control de Emisión LoRa**: Rate Limiter con cola de prioridades y cálculo analítico de tiempo en el aire de Semtech (`Airtime Estimator`).
- **Soberanía y Bajo Consumo**: Servidor web asíncrono embebido sin dependencias pesadas (< 10 MB RAM, arranque en < 50ms) apto para microcomputadores (Orange Pi Zero 2W, Raspberry Pi 3/4/5).
- **Accesibilidad y Seguridad Rigurosa**: Cumplimiento WCAG 2.2 AA (foco visible, navegación por teclado, regiones ARIA), análisis estático Bandit SAST (0 vulnerabilidades) y prevención OWASP Top 10.

---

## 2. Matriz de Compatibilidad de Hardware LoRa

| Fabricante | Modelos Compatibles | Chipsets / MCUs | Interfaz / Baudrate |
| :--- | :--- | :--- | :--- |
| **Heltec Automation** | WiFi LoRa 32 (v2/v3/v4), Wireless Stick, Wireless Tracker, Wireless Paper, Capsule | ESP32-S3, SX1262 | USB-CDC (115200 8N1) |
| **LilyGO (TTGO)** | T-Beam (v1.1/v1.2/Supreme), T-Echo, T3S3, T-Deck, LoRa32 | ESP32, nRF52840, SX1262/SX1276 | USB-UART / CP210x |
| **RAKwireless** | WisBlock Core (RAK4631, RAK11200, RAK11310), WisMesh Hub/Pocket | nRF52840, RP2040, SX1262 | USB-CDC nativo |
| **Seeed Studio** | SenseCAP Indicator / Tracker, Wio-E5, Xiao ESP32-S3 / nRF52840 | SAMD21, ESP32-S3, STM32WLE5 | USB-CDC (115200) |
| **Raspberry Pi** | Pico / Pico W con transceiver SX1262 / SX1276 | RP2040 (Dual ARM Cortex-M0+) | USB-CDC UART |

---

## 3. Protocolo de Ejecución de Agentes & Skills (`.agents/skills/`)

El desarrollo y mantenimiento del proyecto está gobernado por 5 agentes especializados con responsabilidades delimitadas formalmente en `AGENTS.md`:

```mermaid
graph TD
    A1["Agente 1: Protocol & Firmware Investigator"] -->|SSoT Binary Structs & OpCodes| A2["Agente 2: Python Bridge Architect"]
    A2 -->|Async Core & REST API| A4["Agente 4: Web UI/UX Architect"]
    A2 & A4 -->|SAST Audit & Hardening| A5["Agente 5: Security Auditor"]
    A2 & A4 & A5 -->|Continuous Verification & Fuzzing| A3["Agente 3: QA & Fuzzing Agent"]
```

### Inventario de Habilidades Especializadas (Skills)
1. **`python-patterns-typing`**: Estándares PEP, `mypy --strict`, `@dataclass(slots=True, frozen=True)` y protocolos estructurales.
2. **`clean-code-solid`**: Principios SOLID, reducción de complejidad ciclomática y detección AST de *Code Smells*.
3. **`api-design-testing`**: Estándares RESTful, mapeo riguroso de códigos HTTP (200, 201, 204, 400, 413, 422) y errores RFC 7807.
4. **`web-ui-design-system`**: Tokens de diseño, paleta armónica HSL, grilla espacial de 8pt y contraste accesible WCAG 2.2 AA ($\ge 4.5:1$).
5. **`html-css-modern-js`**: Estándares de frontend moderno (HTML5 semántico, CSS Grid/Flexbox, async/await, WebSockets resilientes).
6. **`security-code-auditor`**: Orquestador de análisis SAST con Bandit, prevención de inyecciones SQL, Directory Traversal y XSS.
7. **`bridge-test-runner`**: Orquestador unificado de calidad (Ruff + Mypy Strict + Pytest).
8. **`lora-frame-validator`**: Análisis y validación de tramas binarias LoRa y cálculo de CRC-16.
9. **`meshcore-source-inspector`**: Extractor AST de structs binarios en firmware C/C++ y SDK Python.

---

## 4. Arquitectura del Sistema y Módulos

```mermaid
flowchart TB
    subgraph HardwareLayer["Capa Hardware LoRa"]
        DEV["Dispositivo MeshCore USB"]
    end

    subgraph SerialLayer["Sub-sistema Serial (/src/serial_driver.py)"]
        ADAPTER["BaseSerialAdapter (SDK / Raw Framing Fallback)"]
        WATCHDOG["SerialWatchdog (Monitoreo Activo & Keepalive)"]
        DEV <==> ADAPTER
        WATCHDOG -.->|Supervisa| ADAPTER
    end

    subgraph CoreLayer["Orquestador Central (/src/bridge_core.py)"]
        CORE["MeshCoreBridge (Reactor Asíncrono)"]
        REGISTRY["NodeRegistry (/src/contact_manager.py)"]
        REPEATER["RepeaterManager (/src/repeater_manager.py)"]
        LPP["CayenneLPPDecoder (/src/sensor_decoder.py)"]
        CORE <==> REGISTRY
        CORE <==> REPEATER
        CORE <==> LPP
    end

    subgraph ResilienceLayer["Capa de Resiliencia (/src/store_forward.py & /src/rate_limiter.py)"]
        DEDUP["PacketDeduplicator (RAM Window)"]
        SQLITE[("SQLiteStoreAndForward (Modo WAL + TTL)")]
        TX_QUEUE["TxRateLimiter (PriorityQueue + Airtime)"]
        CORE <==> DEDUP
        CORE <==> SQLITE
        CORE <==> TX_QUEUE
    end

    subgraph NetworkLayer["Capa de Red & Web (/src/mqtt_client.py & /src/web/)"]
        MQTT["AsyncBridgeMQTTClient"]
        HTTP_SRV["MeshCoreWebServer (HTTP 1.1 + WebSocket Hub)"]
        API_ROUTER["WebAPIRouter (REST API)"]
        CORE <==> MQTT
        CORE <==> HTTP_SRV
        HTTP_SRV --> API_ROUTER
    end

    subgraph Clients["Consumidores y Usuarios"]
        MOSQUITTO["Broker Mosquitto"]
        N8N["Automatización n8n"]
        BROWSER["Cliente Web SPA (Navegador / Móvil)"]
        MQTT <==> MOSQUITTO <==> N8N
        HTTP_SRV <==> BROWSER
    end

    ADAPTER <==> CORE
```

---

## 5. Especificación de Protocolo y Mensajería

### 5.1 Framing Serial UART
Toda trama binaria sin procesar se delimita mediante bytes de inicio y fin con escape de bytes (*Byte Stuffing*):
* `SOF`: `0x7E` (Inicio de trama)
* `EOF`: `0x7F` (Fin de trama)
* `ESC`: `0x7D` (Byte de escape; el byte siguiente se transmite como `b ^ 0x20`)
* `CRC`: Verificación mediante CRC-16-CCITT (`Poly: 0x1021`, `Init: 0xFFFF`).

### 5.2 Decodificación Ambiental CayenneLPP (`src/sensor_decoder.py`)
Deserialización de canales estándar IPSO:
* **Temperatura (Tipo 103)**: Signed int16 / 10.0 ($^\circ\text{C}$).
* **Humedad Relativa (Tipo 104)**: Unsigned int8 / 2.0 ($\%$).
* **Presión Barométrica (Tipo 115)**: Unsigned int16 / 10.0 ($\text{hPa}$).
* **Voltaje (Tipo 116)**: Unsigned int16 / 100.0 ($\text{V}$).
* **GPS (Tipo 136)**: 9 bytes con Latitud, Longitud ($0.0001^\circ$) y Altitud ($0.01\text{m}$).
* **Acelerómetro (Tipo 113)**: 6 bytes con $X, Y, Z$ ($0.001\text{G}$).

---

## 6. Cliente Web Station SPA & Endpoints REST

La estación web (`http://<IP>:8080` o `http://<IP>:8085`) provee **11 paneles operativos**:
1. **💬 Chat Multicanal**: Canal Público 0, Canales Privados 1..7 (Cifrado AES) y Mensajes Directos (DMs) aislados.
2. **📻 Centro de Control de Repetidores LoRa**:
   - 📋 *Info de Nodo*: Batería, voltaje solar, SNR, RSSI y uptime.
   - 📻 *Ajustes de Radio RF*: Frecuencia, potencia TX (dBm), Spreading Factor (SF7-SF12) y ancho de banda.
   - 🌐 *Vecinos y Malla*: Tabla de vecinos directos con sondeo `discover.neighbors` y acceso directo a DM.
   - 💻 *Consola Terminal Interactiva*: Stream en vivo y botones de comando rápido (`stats-radio`, `stats-core`, `stats-packets`, `neighbors`, `reboot`).
3. **🗺️ Mapa GPS en Vivo**: Localización espacial de nodos y routers con marcadores interactivos (Leaflet).
4. **📡 Directorio de Nodos**: Registro en tiempo real de nodos activos, calidad de enlace (SNR/RSSI), saltos y batería.
5. **🕵️ RF Packet Sniffer & Analizador Wire (`0x88 LOG_DATA`)**: Interceptación de tramas LoRa en el aire con modal de volcado hexadecimal y JSON estructurado.
6. **📈 Tablero de Métricas Avanzadas & Tops**: Top Nodos por Tráfico y Calidad SNR.
7. **📊 Sensores Ambientales**: Visualización de lecturas CayenneLPP en tarjetas agrupadas.
8. **👥 Libreta de Contactos y Claves**: Gestión de claves públicas, alias y conmutación instantánea a chat DM.
9. **🏠 Integración Home Assistant**: Estado de sincronización MQTT Discovery y re-anuncio forzado.
10. **📜 Consola de Logs del Sistema**: Terminal en vivo con filtro por severidad (`INFO`, `WARN`, `ERROR`), buscador y exportación en `.json`.
11. **⚙️ Configuración de Radio Local & Diagnósticos Preflight**: Verificación previa al arranque de infraestructura (Mosquitto, SQLite WAL, serial/TCP).

### Endpoints REST API
- `GET /api/status`: Estado general, uptime, enlaces y profundidad de colas.
- `GET /api/nodes` & `GET /api/contacts`: Directorio de nodos y contactos.
- `POST /api/contacts`: Alta y edición de contactos.
- `GET /api/channels` & `POST /api/channels`: Gestión de canales cifrados AES.
- `POST /api/tx`: Transmisión RF hacia canales públicos, secundarios o DMs.
- `POST /api/trace`: Lanzamiento de trazado de ruta de radio (Traceroute multi-hop).
- `GET /api/analytics`: Métricas y rankings top en tiempo real.
- `POST /api/sniffer/control` & `GET /api/sniffer/packets`: Control y consulta del interceptor de paquetes RF.
- `POST /api/admin/command` & `POST /api/admin/repeater`: Envío de comandos a nodos locales y repetidores distantes.
- `GET /api/ha/status` & `POST /api/ha/publish`: Estado y publicación de Home Assistant Discovery.
- `GET /api/preflight`: Diagnósticos de infraestructura (Mosquitto, SQLite WAL, puerto serial/TCP).
- `GET /api/system/logs`: Historial de eventos y logs del sistema.
- `OPTIONS *`: CORS preflight retornando `204 No Content`.

---

## 7. Auditoría de Seguridad Informática & Mitigaciones OWASP

Ejecutada mediante la skill `security-code-auditor` y validada con `bandit`:

1. **Inmunidad contra Inyección SQL**: 100% de sentencias en `src/store_forward.py` usan consultas preparadas parametrizadas (`?`).
2. **Aislamiento de Rutas (Directory Traversal)**: Validación estricta con `.resolve()` en `src/web/http_server.py` confinando el acceso a `src/web/static/`. Además, rechazo explícito `403 Forbidden` de rutas con segmentos `..`, barras inversas `\`, marcadores URL-encoded (`%2e`/`%2f`) y patrones `....`.
3. **Protección contra Ataques DoS**: Límite estricto `MAX_BODY_SIZE = 1 MB` con respuesta `413 Payload Too Large`.
4. **Cabeceras de Hardening HTTP**: Inclusión de `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: strict-origin-when-cross-origin`.
5. **Sanitización XSS**: Función obligatoria `escapeHtml()` en `src/web/static/js/app.js` neutralizando código malicioso en el DOM.

---

## 8. Matriz de Calidad y Verificación Unificada (`bridge_test_runner`)

```
=================================================================
 MESHCORE BRIDGE - REPORTE DE VERIFICACIÓN Y CALIDAD
 Estado General: [EXITOSO] ✅
=================================================================

[✅ PASS] ruff (Linter & Style)
  Resumen:  0 advertencias / 0 errores de estilo en src/ y tests/.

[✅ PASS] mypy (Static Type Checker)
  Resumen:  100% tipado estricto (--strict) en los 21 archivos de producción.

[✅ PASS] pytest / Playwright E2E (Test Runner)
  Resumen:  117/117 pruebas unitarias, de integración, E2E y de seguridad superadas.

[✅ PASS] Skills Custom Validation:
  - python-patterns-typing: 100% funciones con anotaciones de tipo completas.
  - clean-code-solid: Refactor aplicado (facade desacoplado; API pública intacta).
  - api-design-testing: 100% contratos de endpoints REST verificados.
  - html-css-modern-js: Semántica HTML5, Vanilla CSS Grid y ES6+ conforme.
  - security-code-auditor: Cero vulnerabilidades Bandit SAST, SQLi, Traversal y XSS.
=================================================================
```

---

## 9. Instrucciones de Despliegue en Producción

### En Linux (Orange Pi / Raspberry Pi / Ubuntu / Debian):
```bash
sudo bash install.sh
```

### En Windows (PowerShell):
```powershell
.\install.ps1 -InstallDeps -Run
```

### Simulación en Vivo (Heltec v4 + 8 Nodos LoRa):
```bash
python scripts/simulate_heltec_v4_mesh.py --live
```

### Verificación Continua de Calidad:
```bash
python .agents/skills/bridge-test-runner/scripts/run_checks.py
```
