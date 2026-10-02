---
name: contract-openapi-sync
description: Revisar compatibilidad REST y WebSocket entre Python y la SPA de MeshCore Bridge; usar comparación léxica de rutas como señal parcial y pruebas aisladas para contratos reales.
---

# Contratos Python y SPA

Leer [AGENTS.md](../../../AGENTS.md) y [TESTING.md](../../../docs/TESTING.md).
El servidor y enrutador son propios: comparar src/web/api_router.py, controllers,
src/web/static/js/core/websocket.js y módulos consumidores.

- Registrar ruta, método, autorización, parámetros, esquema de respuesta y códigos
  de estado. No considerar una ruta válida sólo porque contiene un prefijo conocido.
- Para eventos WS, comparar type, campos obligatorios, formatos y handlers del
  EventBus. No inventar constantes o generar OpenAPI sin inspeccionar implementación.
- Mantener aliases documentados y consumidores MQTT/n8n cuando cambie el contrato.
- Verificar rechazo LOCAL/REPEATER, secretos enmascarados, IDs de mensajes y ACKs.

```bash
python .agents/skills/contract-openapi-sync/scripts/verify_api_parity.py
```

El helper extrae algunas cadenas de rutas mediante regex y compara prefijos con
límites de segmento. Falla si no detecta entradas o existen discrepancias. No extrae
todos los métodos ni valida payloads, campos, WS o endpoints huérfanos. Su resultado
es coincidencia léxica, no paridad completa. Para comprobar esos contratos, usar
tests REST/WS aislados cuando el usuario autorice suites; la autorización se mantiene
durante la tarea. Reportar alcance y pendientes en el ledger.
