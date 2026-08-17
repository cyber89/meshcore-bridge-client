---
name: api-design-testing
description: >-
  Diseño, especificación OpenAPI/Swagger, estándares RESTful (RFC 7807 Problem Details),
  manejo estricto de códigos HTTP (200, 201, 204, 400, 404, 413, 422), idempotencia, CORS y tests de endpoints.
---

# REST API Design & Testing Skill

Esta skill define los estándares de diseño, arquitectura y validación de endpoints REST y WebSocket en sistemas de telecomunicaciones y automatización.

## Estándares de Diseño RESTful
1. **Convenciones de URIs y Recursos**:
   - Nombres en plural para colecciones (`/api/nodes`, `/api/contacts`, `/api/channels`).
   - Identificadores de recursos jerárquicos (`/api/contacts/{public_key}`).
   - Subrecursos y acciones específicas (`/api/admin/repeater/{node_id}/cmd`, `/api/sniffer/control`).

2. **Mapeo Riguroso de Códigos de Estado HTTP**:
   - `200 OK`: Operación de lectura o procesamiento exitoso con payload de retorno.
   - `201 Created`: Recurso creado exitosamente (ej. nuevo contacto o canal).
   - `204 No Content`: Operación completada con éxito sin cuerpo de retorno (ej. CORS Preflight OPTIONS).
   - `400 Bad Request`: Payload malformado o campos requeridos ausentes.
   - `404 Not Found`: Recurso o ruta no existente.
   - `413 Payload Too Large`: Cuerpo de solicitud superior a `MAX_BODY_SIZE`.
   - `422 Unprocessable Entity`: Formato JSON válido pero semántica de negocio errónea (ej. clave pública LoRa con longitud inválida).
   - `500 Internal Server Error`: Fallo no controlado en el servidor.

3. **Estructura de Errores Estandarizada (RFC 7807)**:
   ```json
   {
     "error": "NombreDelError",
     "message": "Descripción legible para humanos",
     "status": 400,
     "timestamp": 1771345678.12
   }
   ```

4. **Cabeceras Obligatorias**:
   - `Content-Type: application/json; charset=utf-8`
   - `Access-Control-Allow-Origin: *`
   - `Access-Control-Allow-Methods: GET, POST, OPTIONS, DELETE`
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`

## Herramientas de Verificación
```bash
python .agents/skills/api-design-testing/scripts/validate_api_contract.py
```
