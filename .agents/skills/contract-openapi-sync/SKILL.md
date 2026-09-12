---
name: contract-openapi-sync
description: >-
  Validador estático de paridad de contratos entre endpoints REST y eventos WebSockets en Python
  (src/web/controllers/) y las llamadas fetch() / listeners en la SPA JavaScript (src/web/static/js/).
  Previene desincronizaciones de contrato, nombres de campo erróneos y rutas 404/422.
---

# Contract & API Parity Sync Skill

Esta skill garantiza la consistencia bidireccional entre la interfaz web en JavaScript y los controladores REST / WebSockets en Python.

---

## 1. Capacidades

1. **Auditoría de Rutas REST**:
   - Extrae todas las rutas y métodos HTTP (`GET`, `POST`, `PUT`, `DELETE`) registrados en `src/web/api_router.py` y `src/web/controllers/`.
   - Extrae todas las llamadas `fetch('/api/...')` en los módulos JavaScript (`chat.js`, `nodes.js`, `settings.js`, etc.).
   - Alerta si el frontend intenta invocar una ruta no implementada en el backend (potencial error 404).
2. **Detección de Rutas Huérfanas**:
   - Identifica endpoints del backend que nunca son consumidos por el cliente web ni por integraciones documentadas.
3. **Validación de Payloads de Eventos WebSocket**:
   - Comprueba que los tipos de eventos emitidos por `WebSocketServer` (`EVENT_TYPE_PACKET`, `EVENT_TYPE_NODE_UPDATE`, etc.) tengan manejadores correspondientes en el despachador de eventos del frontend.

---

## 2. Ejecución del Verificador de Paridad

```bash
python .agents/skills/contract-openapi-sync/scripts/verify_api_parity.py
```
