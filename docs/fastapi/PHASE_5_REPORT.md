# FastAPI: OpenAPI, documentación local y verificación de fase 5

> Snapshot histórico de preparación. El checkout posterior selecciona ASGI y retiró el servidor nativo (`933ccce`). Véanse la [auditoría actual](../audits/2026-10-09-layer-audit.md) y la [fase 6 rectificada](PHASE_6_REPORT.md). Las puertas de ejecución continúan pendientes.

Fecha: 2026-10-09. Base documental: fase 4 publicada en `f5e9f79` y checkout
con cambios anteriores conservados. Estado: **especificación OpenAPI 3.1.0 y visor
local offline preparados y revisados estáticamente para el candidato inactivo**.
La selección del core permanece en `MeshCoreWebServer`; `application_contract_ready=False`
no se eleva por disponer de esquemas o de un visor. Las puertas de aceptación y adopción
siguen pendientes.

## Coordinación y propiedad

El líder coordina especialistas de contratos OpenAPI, interfaz de documentación,
seguridad perimetral y gobernanza documental, e integra generadores, rutas y
registros estáticos. Se aplican las skills de Python, contratos API, seguridad,
UI/UX y gobernanza documental. La instrucción del usuario de continuar sin suites
mantiene suspendida la QA ejecutable. Los especialistas no publican commits ni
cambian el frontend operativo, datos de radio, dependencias o selección del servidor.

| Componente | Propiedad y responsabilidad |
| --- | --- |
| [asgi_openapi.py](../../src/web/asgi_openapi.py) | Especialista OpenAPI: generador diferido de especificación 3.1.0, esquemas DTO y metadatos |
| [asgi_openapi_catalog.py](../../src/web/asgi_openapi_catalog.py) | Especialista de contratos: catálogo de 90 operaciones observadas, políticas y evidencias |
| [asgi_docs.py](../../src/web/asgi_docs.py) | Especialista de rutas: adaptador de documentación, autenticación por cabecera y entrega local |
| [docs_ui/](../../src/web/docs_ui/) | Especialista UI/UX: visor local Vanilla HTML/CSS/JS autónomo, sin CDN ni librerías externas |
| [asgi_security.py](../../src/web/asgi_security.py) | Especialista de seguridad: Content-Security-Policy estricta y estado de respuesta documental |
| [asgi_server.py](../../src/web/asgi_server.py) | Líder: integración de rutas de documentación en la fábrica ASGI antes del catchall estático |
| [asgi_routes.py](../../src/web/asgi_routes.py) | Líder: enriquecimiento de metadatos de operaciones REST a partir del catálogo OpenAPI |
| [PHASE_4_REPORT.md](PHASE_4_REPORT.md) | Informe y registros de WebSocket, SPA y cartografía de la fase previa |
| [PHASE_5_DOCUMENTATION_REGISTRY.json](PHASE_5_DOCUMENTATION_REGISTRY.json) | Registro estático de contratos, archivos, hashes y puertas de aceptación |

El core, bridge, adaptadores de radio, registros de nodos y configuración se **mantienen
desacoplados**. La especificación OpenAPI se construye de forma diferida (`lazy`) sin
instanciar modelos de negocio ni consultar la radio. El adaptador de documentación
posee exclusivamente su caché en memoria y bloqueo de hilo; no accede al bus MQTT
ni genera llamadas a los controladores de la aplicación.

## OpenAPI 3.1.0 y catálogo de operaciones

La especificación generada cumple con el estándar **OpenAPI 3.1.0** y utiliza el dialecto
JSON Schema 2020-12. El documento describe 70 rutas OpenAPI representativas (69 canónicas
JSON y 1 ruta binaria de teselas cartográficas), abarcando 90 operaciones canónicas y
documentando las 50 operaciones de alias mediante extensiones `x-meshcore-aliases`.

1. **Esquemas de Entrada y DTOs:**
   Se incorporan 25 esquemas Pydantic v2 en `components.schemas` derivados de los modelos
   preparados en la fase 2 ([`request_models.py`](../../src/web/request_models.py)), más
   dos esquemas de transporte abiertos (`LegacyJSONResponse` y `CompatibilityErrorResponse`).
   Los DTOs conservan su carácter descriptivo y permisivo, sin imponer validaciones
   restrictivas en el despacho de compatibilidad.

2. **Respuestas y Códigos de Estado Observados:**
   Cada operación declara sus códigos de estado contrastados con la evidencia de los
   controladores: 200, 204, 400, 401, 403, 404, 405, 413, 500 y rangos `4XX`/`5XX`
   para comandos administrativos que preservan códigos remotos de firmware. Los errores
   RFC 7807 Problem Details se documentan bajo `application/json`.

3. **Extensiones de Observación e Invariantes:**
   La raíz del esquema incluye `x-meshcore-observation`, que explicita las discrepancias
   y reglas observadas: ausencia de filtrado estricto de respuestas en modo compatibilidad,
   precedencia de parámetros de ingreso, redacción de errores de seguridad y separación
   de WebSockets y activos estáticos de las rutas REST.

## Visor local de documentación y modelo de seguridad

Para garantizar el funcionamiento en puertas de enlace LoRa autónomas desplegadas en
campo sin conectividad a Internet, el visor de documentación prescinde totalmente de
CDNs y de paquetes Swagger UI / ReDoc externos:

1. **Recursos Propios Autónomos:**
   El visor reside en [`src/web/docs_ui/`](../../src/web/docs_ui/) con tres archivos fijos:
   `index.html` (3,139 bytes), `docs.css` (3,776 bytes) y `docs.js` (12,735 bytes).
   Se sirven desde el adaptador con nombres estáticos, sin resolución dinámica de rutas
   del sistema de archivos ni riesgo de Directory Traversal.

2. **Autenticación Estricta por Cabecera:**
   Cuando `BRIDGE_API_KEY` está configurada, el acceso a `/docs`, `/redoc` y `/openapi.json`
   exige la cabecera `X-Api-Key`. Para los endpoints de documentación se **rechaza intencionadamente
   el parámetro query `api_key`**, evitando que las credenciales queden registradas en el
   historial del navegador, registros de proxy o URLs compartidas.

3. **Formulario de Credenciales sin Divulgación (Shell 401):**
   Una navegación ordinaria del navegador a `/docs` no adjunta encabezados personalizados.
   Ante la ausencia de la clave, el servidor responde con HTTP 401 sirviendo el shell HTML
   con un formulario local de clave. El JavaScript del cliente realiza la petición autenticada
   explícitamente, manteniendo la clave únicamente en memoria y borrándola al cerrar el visor.

4. **Cabeceras de Seguridad y Aislamiento:**
   - **Content-Security-Policy:** Se inyecta una política restrictiva en respuestas HTML:
     `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
   - **Control de Caché:** Todas las respuestas de documentación emiten `Cache-Control: no-store, Vary: X-Api-Key`
     para prevenir el almacenamiento en cachés intermedias.

5. **Política de Solo Lectura:**
   El visor es estrictamente de inspección y lectura. No incluye controles de ejecución
   interactiva ("Try it out") ni emite peticiones REST de mutación o conexiones WebSocket,
   imposibilitando la transmisión accidental de paquetes por radio desde la interfaz.

## Impacto en malla

1. **Airtime:** No se genera transmisión de paquetes de radio. La generación de la
   especificación y la entrega de activos documentales operan exclusivamente en el subsistema
   HTTP local en memoria y disco.
2. **Feedback y reintentos:** La documentación no registra suscripciones WebSocket,
   publicaciones MQTT ni disparadores de eventos hacia n8n o servicios externos.
3. **Invariantes de red (SSoT):** La documentación refleja fielmente la exclusión de
   dispositivos repetidores de la libreta de contactos (`/api/contacts`) y la prohibición
   de bucles locales de mensajería hacia el nodo base local.

## Evidencia estática y aceptación pendiente

La revisión realizada comprende el análisis sintáctico AST bajo gramática Python 3.10,
cotejo de hashes SHA-256, verificación de referencias cruzadas y comprobación estática
de los 10 archivos modificados y creados en la etapa:

- `src/web/asgi_openapi.py` (17,824 bytes, sha256: `b43ab22d6e4b514e552bf477e362f86df0677873892d4674b53917746226e1bc`)
- `src/web/asgi_openapi_catalog.py` (42,120 bytes, sha256: `fe4c9d0dc9dce3ec091a9208c2175d031b8972dc770f794c1b158ee608632b64`)
- `src/web/asgi_docs.py` (6,292 bytes, sha256: `241f9760e29ec1a83fea89bf117000f6f5ceaecf5b586a309a60d92d2cfc9d84`)
- `src/web/docs_ui/index.html` (3,139 bytes, sha256: `3d79214a2c0c86b2923f16ce84109f544210faaa622ab4c69f12a98b8312f345`)
- `src/web/docs_ui/docs.css` (3,776 bytes, sha256: `895a4f12a6ea2992084bd2697898a1f7dc6a0083cbd7f7847b713c2992028b2d`)
- `src/web/docs_ui/docs.js` (12,735 bytes, sha256: `380298987822055c399411dc63511648e6075b84687e25b96444ff7dbc45e622`)
- `src/web/docs_ui/README.md` (1,653 bytes, sha256: `d123f348d639a0137ee4d1da1a098d62658db277d22c6d66845547d638e444f8`)
- `src/web/asgi_security.py` (19,252 bytes, sha256: `a169bd3e818f0d332433b479e0a5a36d6a69bdc17c3293d56b0490a7e54a5628`)
- `src/web/asgi_routes.py` (6,734 bytes, sha256: `9911c0fb2284dd83cd333b51b162d42e8fb2bfd07d3472e56f39ad8f58946a48`)
- `src/web/asgi_server.py` (17,190 bytes, sha256: `2c4bfe4f49b1e953f00a1e86d351855539d10904357c674c395249d56bd1a6bf`)

El [registro documental](PHASE_5_DOCUMENTATION_REGISTRY.json) conserva el detalle estructurado
de todas las operaciones, esquemas y archivos.

**Puertas de Aceptación Pendientes:**
Permanecen explícitamente registradas 16 puertas de verificación operativa para su ejecución
cuando el usuario lo autorice de forma expresa: verificación funcional en navegador aislado,
auditoría de autenticación y cabeceras CSP, pruebas de carga y renderizado en SBCs, paridad
REST/WS completa con la suite automatizada y aprobación formal de adopción de la fase 6.
El candidato ASGI permanece inactivo en la configuración predeterminada del bridge.
