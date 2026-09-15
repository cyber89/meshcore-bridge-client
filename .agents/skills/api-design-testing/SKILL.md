---
name: api-design-testing
description: >-
  Diseño, especificación OpenAPI/Swagger, estándares RESTful (RFC 7807 Problem Details),
  manejo estricto de códigos HTTP (200, 201, 204, 400, 401, 403, 404, 413, 422, 429),
  idempotencia, CORS, OpenAPI 3.1, rate limiting y pruebas automatizadas de contratos.
---

# REST API Design & Testing Skill

Esta skill define los estándares de diseño, arquitectura y validación de endpoints REST y eventos WebSocket en sistemas embebidos, telecomunicaciones y automatización.

## Estándares de Diseño RESTful y OpenAPI 3.1
1. **Convenciones de URIs y Recursos**:
   - Nombres en plural para colecciones (`/api/nodes`, `/api/contacts`, `/api/channels`).
   - Identificadores de recursos jerárquicos (`/api/contacts/{public_key}`).
   - Subrecursos y acciones específicas (`/api/admin/repeater/{node_id}/cmd`, `/api/sniffer/control`).
   - Parámetros de consulta para filtrado y paginación (`/api/nodes?type=repeater&limit=50`).

2. **Mapeo Riguroso de Códigos de Estado HTTP**:
   - `200 OK`: Operación de lectura o procesamiento exitoso con cuerpo de respuesta JSON.
   - `201 Created`: Recurso creado exitosamente (ej. nuevo contacto o canal).
   - `204 No Content`: Operación completada con éxito sin cuerpo de retorno (ej. CORS Preflight OPTIONS).
   - `400 Bad Request`: Payload malformado o campos requeridos ausentes.
   - `401 Unauthorized`: Token o autenticación administrativa faltante o inválida.
   - `403 Forbidden`: Acción rechazada por políticas de seguridad o reglas de dominio (ej. enviar chat a un repetidor).
   - `404 Not Found`: Recurso o ruta no existente.
   - `413 Payload Too Large`: Cuerpo de solicitud superior al límite configurado (`MAX_BODY_SIZE`).
   - `422 Unprocessable Entity`: Formato sintáctico JSON válido pero semántica de negocio errónea.
   - `429 Too Many Requests`: Tasa de peticiones o airtime excedido (incluye cabeceras de reintento).
   - `500 Internal Server Error`: Fallo no controlado en el servidor.

3. **Estructura Canónica de Errores (RFC 7807 Problem Details)**:
   ```json
   {
     "type": "https://meshcore.local/errors/validation-failed",
     "title": "Unprocessable Entity",
     "status": 422,
     "detail": "La clave pública proporcionada no tiene una longitud hexadecimal válida de 64 caracteres.",
     "instance": "/api/contacts/invalid_key",
     "timestamp": 1789429700.15
   }
   ```

4. **Cabeceras Obligatorias y de Seguridad**:
   - `Content-Type: application/json; charset=utf-8`
   - `Access-Control-Allow-Origin: *`
   - `Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE`
   - `Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With`
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

5. **Paridad Bidireccional de Contratos**:
   - Toda llamada `fetch()` en el cliente frontend (`src/web/static/js/`) debe tener una ruta coincidente 1:1 en los controladores de backend (`src/web/controllers/`).
   - Todo evento emitido en WebSockets (`ws.send()`) debe ser parseado deterministamente sin lanzar excepciones no controladas.

## Herramientas de Verificación
```bash
python .agents/skills/api-design-testing/scripts/validate_api_contract.py
python tests/tools/verify_api_parity.py
```

