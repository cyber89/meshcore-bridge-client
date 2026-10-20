# Sistema Documental de MeshCore Bridge

Índice maestro de especificaciones vivas, arquitectura, decisiones y registros de auditoría de **MeshCore Bridge**.

---

## 🏛️ Estructura y Gobernanza Documental

El repositorio organiza su documentación bajo el principio de **separación estricta entre la verdad actual (*Living Documentation*) y la trazabilidad histórica (*Decision Logs & Audit Trails*)**:

```text
docs/
├── AI_REFERENCE.md                 <- Referencia de alta densidad e inferencia para modelos de IA y agentes
├── [Living Documentation]          <- Especificaciones canónicas del sistema en producción (SSoT)
│   ├── ARCHITECTURE.md             <- Arquitectura general en 5 capas y ciclo asíncrono
│   ├── PROTOCOL_SPEC.md            <- Protocolo binario LoRa, framing y opcodes oficiales
│   ├── SYSTEM_LAYERS_MANUAL.md     <- Manual exhaustivo de subsistemas y componentes
│   ├── CODE_EXPLANATION.md         <- Guía técnica de lectura del código fuente
│   ├── DEPLOYMENT_GUIDE.md         <- Guía de despliegue en Linux (systemd), SBC y Windows
│   ├── N8N_WORKFLOW_GUIDE.md       <- Integración MQTT y automatizaciones n8n
│   ├── STORAGE.md                  <- Persistencia SQLite transaccional, migración y backups
│   ├── FRONTEND_DELIVERY.md        <- Empaquetado web, minificación y caché HTTP
│   ├── TESTING.md                  <- Entorno de QA, aislamiento de suites y fixtures
│   ├── TEST_INVENTORY.md           <- Inventario catalogado de pruebas automatizadas
│   ├── PROJECT_KNOWLEDGE.md        <- Mapa de conocimiento y procedencia de referencias
│   └── PROJECT_INVENTORY.json      <- Snapshot reproducible de hashes e inventario
├── adr/                            <- Registros de Decisiones de Arquitectura (0001 - 0018)
├── audits/                         <- Informes de auditoría fechados (YYYY-MM-DD-*.md)
├── plans/                          <- Planes de modernización e integración completados o activos
├── fastapi/                        <- Documentación, fases y contratos del subsistema ASGI
├── reference_analysis/             <- Análisis técnico del firmware C++, SDK y CLI oficiales
└── diagrams/                       <- Diagramas interactivos autónomos (Archify SVG/HTML)
```

> [!IMPORTANT]
> **Regla de Gobernanza de Almacenamiento**:
> 1. **Documentación Viva**: La raíz de `docs/` contiene **únicamente** especificaciones canónicas vigentes.
> 2. **Decisiones**: Todo cambio arquitectónico estructural requiere un ADR numerado secuencialmente en `docs/adr/`.
> 3. **Auditorías y Revisiones**: Cualquier informe puntual, análisis de seguridad o revisión debe almacenarse en `docs/audits/` bajo el formato `YYYY-MM-DD-<nombre>.md`. Nunca se dejan auditorías en la raíz del proyecto ni sueltas en `docs/`.
> 4. **Planes de Trabajo**: Los planes de integración o modernización se almacenan en `docs/plans/`.

---

## 🗺️ Rutas de Lectura por Rol

| Rol / Objetivo | Documentos Clave de Entrada |
|---|---|
| **Arquitectura y Core** | [CONTEXT.md](../CONTEXT.md) • [AGENTS.md](../AGENTS.md) • [ARCHITECTURE.md](ARCHITECTURE.md) • [SYSTEM_LAYERS_MANUAL.md](SYSTEM_LAYERS_MANUAL.md) |
| **Protocolo y Radio LoRa** | [PROTOCOL_SPEC.md](PROTOCOL_SPEC.md) • [reference_analysis/](reference_analysis/01_FIRMWARE_C_CPP.md) • [ADR 0002](adr/0002-lora-airtime-guardrails.md) |
| **Despliegue y Operación** | [README del Proyecto](../README.md) • [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) • [STORAGE.md](STORAGE.md) • [N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md) |
| **Frontend Web SPA** | [FRONTEND_DELIVERY.md](FRONTEND_DELIVERY.md) • [plans/FRONTEND_MODERNIZATION_PLAN.md](plans/FRONTEND_MODERNIZATION_PLAN.md) • [ADR 0012](adr/0012-bootstrap-5-frontend-architecture.md) |
| **QA y Verificación** | [TESTING.md](TESTING.md) • [TEST_INVENTORY.md](TEST_INVENTORY.md) |
| **Modelos de IA y Agentes** | [AI_REFERENCE.md](AI_REFERENCE.md) • [CONTEXT.md](../CONTEXT.md) • [AGENTS.md](../AGENTS.md) |

---

## 📚 1. Especificaciones Canónicas (Living Documentation)

1. **[AI_REFERENCE.md](AI_REFERENCE.md)**: **Referencia determinista de navegación, contratos, símbolos e invariantes para modelos de IA y agentes autónomos**.
2. **[README del Proyecto](../README.md)**: Visión general, instalación, despliegue como servicio y configuración principal (en inglés).
3. **[AGENTS.md](../AGENTS.md)**: Protocolo de orquestación multi-agente, gobernanza de cambios, reglas de exclusión y checklist de impacto en la malla LoRa.
4. **[CONTEXT.md](../CONTEXT.md)**: Lenguaje ubicuo, modelo de dominio canónico, clasificación estricta de roles (`CLIENT`, `REPEATER`, `ROOM`, `SENSOR`) e invariantes.
5. **[ARCHITECTURE.md](ARCHITECTURE.md)**: Arquitectura en 5 capas, servidor FastAPI / Uvicorn ASGI de producción, WebSocket Hub y ciclo de vida asíncrono.
6. **[PROTOCOL_SPEC.md](PROTOCOL_SPEC.md)**: Especificación formal del protocolo MeshCore, framing Companion oficial, framing raw propio y contratos binarios.
7. **[SYSTEM_LAYERS_MANUAL.md](SYSTEM_LAYERS_MANUAL.md)** y **[CODE_EXPLANATION.md](CODE_EXPLANATION.md)**: Manual detallado de subsistemas, módulos, estrategias de enrutamiento y persistencia.
8. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: Guía completa de despliegue en Linux (systemd), Raspberry Pi / Orange Pi y Windows.
9. **[STORAGE.md](STORAGE.md)**: Persistencia transaccional SQLite, fuentes de verdad, importación y copias de seguridad.
10. **[FRONTEND_DELIVERY.md](FRONTEND_DELIVERY.md)**: Build JS/CSS minimizado, compresión gzip previa y presupuesto de CPU en entrega web.
11. **[N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md)**: Integración con automatizaciones n8n y esquemas de mensajería MQTT.
12. **[TESTING.md](TESTING.md)** y **[TEST_INVENTORY.md](TEST_INVENTORY.md)**: Entorno de QA, aislamiento de suites de prueba, fixtures y comandos reproducibles.
13. **[PROJECT_KNOWLEDGE.md](PROJECT_KNOWLEDGE.md)**: Mapa de conocimiento del proyecto y procedencia de fuentes de referencia.

---

## 🏛️ 2. Registros de Decisiones de Arquitectura (ADRs)

Los ADRs documentan de forma inmutable las decisiones arquitectónicas fundamentales tomadas a lo largo de la evolución del proyecto:

| ADR | Título | Estado |
|---|---|---|
| **[ADR 0001](adr/0001-strict-repeater-contact-exclusion.md)** | Exclusión Estricta de Repetidores en Contactos | Vigente |
| **[ADR 0002](adr/0002-lora-airtime-guardrails.md)** | Protecciones de Airtime en la Malla LoRa | Vigente |
| **[ADR 0003](adr/0003-asyncio-serial-resilience.md)** | Resiliencia del Driver Serie con AsyncIO | Vigente |
| **[ADR 0004](adr/0004-airtime-duty-cycle-alerting-and-persistence.md)** | Alertas de Duty Cycle y Persistencia de Airtime | Vigente |
| **[ADR 0005](adr/0005-json-atomic-persistence-over-sqlite.md)** | Persistencia Atómica JSON frente a SQLite | Sustituido por ADR 0017 |
| **[ADR 0006](adr/0006-tcp-companion-server-proxy.md)** | Servidor Proxy TCP Companion | Vigente |
| **[ADR 0007](adr/0007-decoupling-local-beacon-telemetry.md)** | Desacoplamiento de Beacon Local y Telemetría | Vigente |
| **[ADR 0008](adr/0008-automatic-rtc-clock-synchronization.md)** | Sincronización Automática de Reloj RTC | Vigente |
| **[ADR 0009](adr/0009-official-companion-protocol-layers.md)** | Capas del Protocolo Companion Oficial | Vigente |
| **[ADR 0010](adr/0010-duty-cycle-configurable-budget.md)** | Presupuesto Configurable de Duty Cycle | Vigente |
| **[ADR 0011](adr/0011-staged-asgi-migration.md)** | Migración Escalonada a FastAPI/Uvicorn ASGI | Vigente |
| **[ADR 0012](adr/0012-bootstrap-5-frontend-architecture.md)** | Frontend Bootstrap 5 | Vigente |
| **[ADR 0013](adr/0013-python-3-14-modernization.md)** | Propuesta histórica de Python 3.14 | Sustituida por ADR 0016 |
| **[ADR 0014](adr/0014-python-3-15-baseline.md)** | Decisión histórica CPython 3.15.0 | Sustituida por ADR 0016 |
| **[ADR 0015](adr/0015-python-3-14-8-baseline.md)** | Decisión histórica CPython 3.14.8 | Sustituida por ADR 0016 |
| **[ADR 0016](adr/0016-python-3-12-baseline.md)** | Mínimo CPython 3.12 y versión recomendada 3.13.5 (sin máximo) | Vigente |
| **[ADR 0017](adr/0017-sqlite-station-browser-cache.md)** | SQLite y caché de navegador (sustituye ADR 0005) | Vigente |
| **[ADR 0018](adr/0018-personal-station-authentication.md)** | Autenticación de la estación personal | Vigente |

---

## 📋 3. Planes de Modernización e Integración (`docs/plans/`)

Documentos de planificación paso a paso para la adopción de nuevas capacidades:

- 🔒 **[Plan de Autenticación de Estación Personal](plans/AUTHENTICATION_PLAN.md)** y **[Diseño y Recuperación](plans/LOGIN_DESIGN_AND_RECOVERY.md)**.
- 💾 **[Plan de Integración de Almacenamiento SQLite](plans/STORAGE_INTEGRATION_PLAN.md)**.
- 🎨 **[Plan de Modernización del Frontend](plans/FRONTEND_MODERNIZATION_PLAN.md)**.
- 📶 **[Plan de Actualización por Capas a MeshCore 1.18](plans/MESHCORE_1_18_UPGRADE_PLAN.md)**.

---

## 🛡️ 4. Historial de Auditorías y Revisiones (`docs/audits/`)

Informes técnicos fechados que documentan la verificación estática, hallazgos de seguridad y evolución del código:

- 🛡️ **[Auditoría por capas 2026-10-09](audits/2026-10-09-layer-audit.md)** (y [JSON complementario](audits/2026-10-09-layer-audit.json)).
- 📶 **MeshCore 1.18 (Octubre 2026)**:
  - [Ledger de integración y entrega conjunta](audits/2026-10-15-meshcore-1.18-integration.md)
  - [Auditoría de protocolo y fuentes](audits/2026-10-15-meshcore-1.18-protocol.md)
  - [Auditoría backend](audits/2026-10-15-meshcore-1.18-backend.md)
  - [Auditoría web y seguridad](audits/2026-10-15-meshcore-1.18-web.md)
  - [Verificación de capas 2 y 3](audits/2026-10-16-meshcore-1.18-layers-2-3.md)
  - [Selector de transporte Companion TCP/Serial](audits/2026-10-17-companion-connection.md)
  - [Preferencias de firmware locales](audits/2026-10-17-firmware-preferences.md) y [remotas](audits/2026-10-17-remote-firmware-preferences.md)
  - [Gestión WiFi Companion](audits/2026-10-17-firmware-wifi.md)
  - [Pausa manual en administración](audits/2026-10-17-meshcore-1.18-manual-admin.md)
  - [Suscripciones a sensores (0x08 / 0x09)](audits/2026-10-17-sensor-subscriptions.md)
- 🎨 **Revisiones de Interfaz y Frontend**:
  - [Auditoría de JavaScript Frontend (2026-10-18)](audits/2026-10-18-js-frontend-audit.md)
  - [Revisión visual de CSS y accesibilidad (2026-10-18)](audits/2026-10-18-css-visual-review.md)
  - [Mejoras en visualización de chat (2026-10-18)](audits/2026-10-18-chat-reading-improvements.md)
  - [Corrección de arranque y sesión autenticada (2026-10-18)](audits/2026-10-18-auth-startup-fix.md)
  - [Refinamiento de diálogo y toasts (2026-10-17)](audits/2026-10-17-dialog-toast-refinement.md)
  - [Refinamiento visual web (2026-10-17)](audits/2026-10-17-web-visual-refinement.md)
  - [Auditoría del login en navegador (2026-10-12)](audits/2026-10-12-login-browser-audit.md)

---

## 🚀 5. Subsistema FastAPI / Uvicorn ASGI (`docs/fastapi/`)

Informes de preparación e implementación de la pila web ASGI:

- 📜 **[Propuesta y evaluación histórica de FastAPI](fastapi/HISTORICAL_PROPOSAL.md)**
- **[Fase 0: Auditoría y Viabilidad](fastapi/PHASE_0_REPORT.md)**
- **[Fase 1: Servidor ASGI Base y Ciclo de Vida](fastapi/PHASE_1_REPORT.md)** y **[Seguridad ASGI](fastapi/PHASE_1_SECURITY_REPORT.md)**
- **[Fase 2: DTOs Pydantic y Política de Errores RFC 7807](fastapi/PHASE_2_REPORT.md)**
- **[Fase 3: Rutas REST Modulares](fastapi/PHASE_3_REPORT.md)**
- **[Fase 4: WebSocket Hub, Assets SPA y Servicio MBTiles](fastapi/PHASE_4_REPORT.md)**
- **[Fase 5: OpenAPI 3.1.0 y Visor de Solo Lectura](fastapi/PHASE_5_REPORT.md)**
- **[Fase 6: Perfiles de Instalación y Resiliencia en Producción](fastapi/PHASE_6_REPORT.md)**

---

## 🗺️ 6. Diagramas de Arquitectura (`docs/diagrams/`)

Diagramas interactivos en HTML autónomo + SVG:

- 🗺️ **[Arquitectura General del Sistema](diagrams/meshcore_architecture.html)**
- ⚡ **[Pipeline de Paquetes Raw a IP](diagrams/meshcore_packet_pipeline.html)**
- ⏱️ **[Secuencia Operativa Bidireccional](diagrams/meshcore_rx_tx_sequence.html)**

---

## 🔬 7. Análisis de Referencias Oficiales (`docs/reference_analysis/`)

Análisis detallado de las bases de código originales en `/reference/`:

- [01. Firmware oficial MeshCore C/C++](reference_analysis/01_FIRMWARE_C_CPP.md)
- [02. SDK oficial de MeshCore en Python](reference_analysis/02_PYTHON_SDK.md)
- [03. CLI oficial y gestión remota de repetidores](reference_analysis/03_CLI_AND_REPEATER_MANAGEMENT.md)
- [04. Guía de integración de referencias para agentes](reference_analysis/04_INTEGRATION_GUIDE_FOR_AGENTS.md)
