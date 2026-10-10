# Documentación de MeshCore Bridge

Índice maestro de especificaciones, arquitectura y guías operativas de **MeshCore Bridge**.

---

## 📚 Documentación Vigente y Contratos de Dominio

1. **[README del Proyecto](../README.md)**: Visión general, instalación, despliegue como servicio y configuración principal.
2. **[AGENTS.md](../AGENTS.md)**: Protocolo de orquestación multi-agente, gobernanza de cambios, reglas de exclusión y checklist de impacto en la malla LoRa.
3. **[CONTEXT.md](../CONTEXT.md)**: Modelo de dominio canónico, lenguaje ubicuo, clasificación estricta de nodos (CLIENT, REPEATER, ROOM, SENSOR) e invariantes inmutables.
4. **[PROTOCOL_SPEC.md](PROTOCOL_SPEC.md)**: Especificación formal del protocolo MeshCore, framing Companion oficial, framing raw propio y contratos binarios.
5. **[ARCHITECTURE.md](ARCHITECTURE.md)**: Arquitectura en 5 capas, servidor FastAPI / Uvicorn ASGI de producción, WebSocket Hub y ciclo de vida asíncrono.
6. **[SYSTEM_LAYERS_MANUAL.md](SYSTEM_LAYERS_MANUAL.md)** y **[CODE_EXPLANATION.md](CODE_EXPLANATION.md)**: Manual detallado de subsistemas, módulos, estrategias de enrutamiento y persistencia.
7. **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**: Guía completa de despliegue en Linux (systemd), Raspberry Pi / Orange Pi y Windows.
8. **[N8N_WORKFLOW_GUIDE.md](N8N_WORKFLOW_GUIDE.md)**: Integración con automatizaciones n8n y esquemas de mensajería MQTT.
9. **[TESTING.md](TESTING.md)** y **[TEST_INVENTORY.md](TEST_INVENTORY.md)**: Entorno de QA, aislamiento de suites de prueba, fixtures y comandos reproducibles.
10. **[PROJECT_KNOWLEDGE.md](PROJECT_KNOWLEDGE.md)**: Mapa de conocimiento del proyecto y fuentes de referencia.
11. **[FRONTEND_DELIVERY.md](FRONTEND_DELIVERY.md)**: Build JS/CSS minimizado, gzip previo y presupuesto de CPU de compresión web.

---

## 🏛️ Registros de Decisiones de Arquitectura (ADRs)

Los ADRs documentan las decisiones arquitectónicas fundamentales tomadas a lo largo de la evolución del proyecto:

- **[ADR 0001: Exclusión Estricta de Repetidores en Contactos](adr/0001-strict-repeater-contact-exclusion.md)**
- **[ADR 0002: Protecciones de Airtime en la Malla LoRa](adr/0002-lora-airtime-guardrails.md)**
- **[ADR 0003: Resiliencia del Driver Serie con AsyncIO](adr/0003-asyncio-serial-resilience.md)**
- **[ADR 0004: Alertas de Duty Cycle y Persistencia de Airtime](adr/0004-airtime-duty-cycle-alerting-and-persistence.md)**
- **[ADR 0005: Persistencia Atómica JSON frente a SQLite](adr/0005-json-atomic-persistence-over-sqlite.md)**
- **[ADR 0006: Servidor Proxy TCP Companion](adr/0006-tcp-companion-server-proxy.md)**
- **[ADR 0007: Desacoplamiento de Beacon Local y Telemetría](adr/0007-decoupling-local-beacon-telemetry.md)**
- **[ADR 0008: Sincronización Automática de Reloj RTC](adr/0008-automatic-rtc-clock-synchronization.md)**
- **[ADR 0009: Capas del Protocolo Companion Oficial](adr/0009-official-companion-protocol-layers.md)**
- **[ADR 0010: Presupuesto Configurable de Duty Cycle](adr/0010-duty-cycle-configurable-budget.md)**
- **[ADR 0011: Migración Escalonada a FastAPI/Uvicorn ASGI](adr/0011-staged-asgi-migration.md)**
- **[ADR 0012: Frontend Bootstrap 5](adr/0012-bootstrap-5-frontend-architecture.md)**
- **[ADR 0013: Propuesta histórica de Python 3.14, sustituida](adr/0013-python-3-14-modernization.md)**
- **[ADR 0014: Decisión histórica CPython 3.15.0, sustituida](adr/0014-python-3-15-baseline.md)**
- **[ADR 0015: Baseline CPython 3.14.8 y estabilización de dependencias](adr/0015-python-3-14-8-baseline.md)**

---

## Auditoría actual

- [Reunión técnica y auditoría por capas del 2026-10-09](audits/2026-10-09-layer-audit.md): implementación, correcciones y evidencia estática; QA en ejecución pendiente.
- [Plan y evolución FastAPI](../PROYECTO.md): distingue propuesta histórica de transporte seleccionado.

## 🚀 Migración FastAPI / Uvicorn ASGI

Los informes de preparación son snapshots históricos; la auditoría actual y la fase 6 rectificada describen la evolución. Las comprobaciones estáticas no certifican ejecución. Los informes de la pila FastAPI ASGI residen en [`docs/fastapi/`](fastapi/):

- **[Fase 0: Auditoría y Viabilidad](fastapi/PHASE_0_REPORT.md)**
- **[Fase 1: Servidor ASGI Base y Ciclo de Vida](fastapi/PHASE_1_REPORT.md)** y **[Seguridad ASGI](fastapi/PHASE_1_SECURITY_REPORT.md)**
- **[Fase 2: DTOs Pydantic y Política de Errores RFC 7807](fastapi/PHASE_2_REPORT.md)**
- **[Fase 3: Rutas REST Modulares](fastapi/PHASE_3_REPORT.md)**
- **[Fase 4: WebSocket Hub, Assets SPA y Servicio MBTiles](fastapi/PHASE_4_REPORT.md)**
- **[Fase 5: OpenAPI 3.1.0 y Visor de Solo Lectura](fastapi/PHASE_5_REPORT.md)**
- **[Fase 6: Perfiles de Instalación y Resiliencia en Producción](fastapi/PHASE_6_REPORT.md)**

---

## 🗺️ Diagramas de Arquitectura (Archify)

Los diagramas interactivos en HTML autónomo + SVG residen en [`docs/diagrams/`](diagrams/):

- 🗺️ **[Arquitectura General del Sistema](diagrams/meshcore_architecture.html)**
- ⚡ **[Pipeline de Paquetes Raw a IP](diagrams/meshcore_packet_pipeline.html)**
- ⏱️ **[Secuencia Operativa Bidireccional](diagrams/meshcore_rx_tx_sequence.html)**

---

## 📡 Gobernanza y Reglas de la Malla LoRa

1. **Recepción Pasiva Preferida**: Priorizar siempre la telemetría pasiva sobre sondeos o consultas activas que consuman airtime RF.
2. **Exclusión de Repetidores y Estación Local**: Los repetidores de infraestructura nunca se incluyen en la libreta de contactos ni reciben mensajería de chat/DM. La estación local tampoco puede ser remitente o destinataria de bucles locales.
3. **Persistencia de Timers**: Los timestamps de enfriamiento (*cooldowns*) deben persistirse en disco (`repeater_cooldowns.json`) para evitar ráfagas tras guardar configuraciones o reiniciar el servicio.
