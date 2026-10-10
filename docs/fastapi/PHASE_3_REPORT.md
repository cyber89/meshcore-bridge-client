# FastAPI: registro REST preparatorio de fase 3

> Snapshot histórico de preparación. El checkout posterior selecciona ASGI y retiró el servidor nativo (`933ccce`). Véanse la [auditoría actual](../audits/2026-10-09-layer-audit.md) y la [fase 6 rectificada](PHASE_6_REPORT.md). Las puertas de ejecución continúan pendientes.

Fecha: 2026-10-09. Base: `42f7104` y checkout con cambios anteriores conservados.
Estado: **seis lotes JSON registrados en el código del candidato inactivo**,
con revisión estática. No se ha importado, construido ni ejecutado la aplicación.
La fábrica del core sigue seleccionando `MeshCoreWebServer` y
`application_contract_ready=False` permanece explícito.

Este informe conserva el alcance histórico de fase 3. La preparación posterior
de WS/SPA/teselas está documentada en [fase 4](PHASE_4_REPORT.md); los hashes
de su registro son snapshots de cada etapa, no una afirmación de identidad del árbol actual.

## Entrega y coordinación

El líder integró tres especialistas de catálogo, seguridad y revisión de
compatibilidad. Se aplicaron las skills de Python, contratos API, seguridad,
gobernanza ADR y verificación; la instrucción del usuario de continuar sin
suites prevalece sobre ejecución de QA. La propiedad de archivos se separó y
el líder revisó directamente código, diff y metadatos.

| Componente | Propósito |
| --- | --- |
| [asgi_route_catalog.py](../../src/web/asgi_route_catalog.py) | Declaraciones Python inmutables de operaciones y modelos descriptivos, sin depender de documentación JSON en runtime |
| [asgi_routes.py](../../src/web/asgi_routes.py) | Seis APIRouter, alias, adaptación del target y fallback REST |
| [api_error_policy.py](../../src/web/api_error_policy.py) | Redacción selectiva de respuestas de fallo del candidato |
| [api_router.py](../../src/web/api_router.py) | Corrección compartida del catch global y los errores de enteros |
| [asgi_server.py](../../src/web/asgi_server.py) | Instala los lotes sólo en la fábrica opcional |
| [Registro estático](PHASE_3_ROUTE_REGISTRY.json) | Conteos, operaciones, alias, hashes y alcance de preparación |

| Lote | Operaciones canónicas | Alcance |
| --- | ---: | --- |
| 3.1 Sistema | 11 | Estado, salud/diagnósticos, preflight, reportes/export, logs y nivel |
| 3.2 Red | 8 | Nodos, LQI, analítica/reset, RF y airtime |
| 3.3 Contactos/canales | 17 | CRUD, import/export, share, sync, discovered/accept y eliminación individual |
| 3.4 Historial/mapas | 10 | Paquetes/export/borrado, mensajes, telemetría, logs y estado/recarga de mapas |
| 3.5 Servicios | 6 | Configuración, presets y prueba MQTT externa |
| 3.6 Radio/admin | 38 | TX, configuración/nodo y administración/repetidores |

Son 90 operaciones JSON sobre 69 patrones canónicos. Se reutilizan los 39 alias
del dispatcher para 50 combinaciones adicionales: **140 operaciones JSON y
108 patrones**. La operación binaria de tiles elevará el conjunto funcional a
141/109 cuando se porte en fase 4; no se cuenta como completada aquí.
Los seis lotes se preparan secuencialmente en el registro y conservan sus puertas
de ejecución pendientes. No se acepta un lote por disponer de una declaración.

## Contrato del adaptador

Cada endpoint tiene únicamente `Request` como parámetro; FastAPI no infiere
coerciones de body/query o validaciones de rol. El adaptador toma el diccionario
JSON del estado que suministra el guard de ingreso de fase 1 y llama **una vez**
al router prestado con método y target originales. No vuelve a leer/parsing el
cuerpo ni reconstruye query desde `request.query_params`.

Los DTO identifican el contrato descriptivo de cada operación. Se conserva el
mapping original, sin `model_validate` o `model_dump` por solicitud: incluso
`Any` puede encontrar otra guarda de recursión/serialización en Pydantic. No se
introduce esa diferencia antes de los controladores. La exportación preparatoria
de fase 2 permanece disponible para futura QA, sin afirmar round-trip universal.

Se reutiliza `WebAPIRouter.handle_request`; no se reescriben ni duplican los diez
controladores, buffers, canales, mapas, locks, radio o MQTT. El router conserva
prioridad de body, repetición/vacíos de query, aliases y la lectura especial de
query de LogsController. Las respuestas usan `legacy_json_response`, sin
`response_model` filtrante ni otra semántica TX. No se introduce `202`, se
mantienen espera/timeout y códigos actuales, salvo los textos redactados abajo.

FastAPI/Starlette resuelven normalmente una ruta decodificada. La subclase local
`_RawTargetAPIRoute` compara el path codificado original en una copia superficial
del scope, preservando el contexto efectivo de los routers incluidos de
FastAPI 0.143.0. El Request conserva su scope original. Esto evita reconocer
rutas distintas de las admitidas por el dispatcher y su política de auth raw.
Si el transporte omite `raw_path`, el fallback de ASGI no puede reconstruir la
codificación original. El `root_path` vacío vigente es el alcance preparado;
proxy/root_path alternativo o montaje dentro de otra aplicación necesitan revisión.

Se desactiva `redirect_slashes`. Un `BaseRoute` HTTP al final del **router raíz**
admite `/api/` raw y todos los verbos, salvo el prefijo de tiles. Un match FULL
vence a matches PARTIAL previos: métodos no admitidos, HEAD, rutas desconocidas
y variantes de slash pasan por las decisiones `404`/`405` de cada familia.
No se añade `Allow` por el fallback del framework ni se convierte HEAD en GET;
la capa exterior suprime el cuerpo conservando longitud de representación.
Los textos de ciertos `404` se redactan expresamente en la política siguiente.

La lectura de FastAPI 0.143 confirmó que `include_router` conserva ramas
incluidas y omite contextos para tipos BaseRoute no soportados. Por eso el
fallback se añade directamente al root, antes del primer uso. No debe reubicarse
en un APIRouter incluido ni encapsular esta app como un router incluido sin
revisar esa limitación. Los alias quedan fuera del esquema; los dos parámetros
dinámicos reciben metadatos de path/string sin restricciones nuevas. El cuerpo,
query, respuestas y documentación autenticada completos son trabajo de fase 5;
este registro no acredita un OpenAPI completo o válido en ejecución.

## Redacción explícita y límites

Hay dos cambios compartidos con el servidor actual: el catch global REST devuelve
un `500` fijo y registra sólo clase de excepción/evento fijo, sin query, texto
de excepción o traceback; los errores de enteros conservan coerción, rango y
código pero omiten el valor recibido. Son correcciones de seguridad deliberadas,
no cambios de validación. Las respuestas de controladores se mantienen fuera
de la nueva política cuando se usa el servidor nativo.

El candidato aplica además una política selectiva a HTTP de fallo y wrappers
`error`/`failed`/`partial`. Trece códigos conocidos tienen detail/message públicos
fijos: command_failed/partial, sync_failed, read_unconfirmed, unsupported_parameter,
auth_failed, invalid_log_level, tx_submission_failed/transmission_failed,
reload_failed, route_not_found, services_route_not_found y preset_not_found.
También se fija el mensaje de `500`. Se conservan HTTP status y error code,
type/title/timestamp, `partial`, `applied`, `config`, `action`,
`dispatched_commands`, `target_node` y otros contenedores.

Las extensiones de fallos pasan una vez por el redactor canónico de credenciales
y comandos, después por la protección de nombres sensibles adicionales y textos
de diagnóstico anidados. Se preserva `has_pin` generado, presencia de campos,
bytes y floats salvo secretos enmascarados. MQTT puede devolver HTTP `200` con
wrapper `error`: se conserva `200`, `data.ok` y métricas, redactando su diagnóstico.
Los éxitos, configuración y exportaciones no pasan por esta política.

**No es redacción global:** logs internos de servicios, serial/config, TX,
persistencia/import de contactos/canales y errores de mutación todavía pueden
contener detalles de excepción. Textos arbitrarios bajo campos desconocidos,
`result`/`target_node` y salidas exitosas administrativas requieren revisión
adicional antes de adopción. El recorrido de extensiones también tiene los
límites de recursión de Python; no se certifica resistencia a árboles arbitrarios.
El snapshot de fase 2 conserva sus hashes/líneas históricos; el registro nuevo
documenta las fuentes de esta continuación, sin reescribir la evidencia anterior.

## Impacto de malla y puerta pendiente

1. **Airtime:** la capa de registro no envía paquetes ni inicia consultas. Al
   activarse, cada solicitud utiliza exactamente la operación existente; TX,
   ping/traceroute/admin, config y servicios mantienen sus efectos actuales y
   limitadores/cooldowns. No hay tráfico nuevo por registrar rutas.
2. **Feedback/reintentos:** se preservan guardas LOCAL/REPEATER, origen propio,
   admisión, deduplicación y serialización. No se añade reintento, envío doble,
   timer o publicación MQTT adicional. La configuración de servicios conserva
   sus efectos indirectos actuales, sin prometer que todo comando pase por TX.
3. **Guardado/timers:** se presta el mismo estado y no se reconstruyen schedulers,
   RepeaterManager o canales. Se conservan timestamps/cooldowns persistidos y
   límites vigentes; no se fija unilateralmente ningún intervalo o umbral.

La comprobación permitida consiste en fuentes/wheels, AST con gramática 3.10,
comparación del catálogo/inventario, hashes, referencias, nombres y diff. No se
ejecutaron suites/cobertura, mypy, Ruff, imports del candidato, registro de rutas,
handlers, servicios, navegador, radio o broker. Tampoco se reprodujo reinicio
de una estación: esa comprobación requiere un entorno virtual autorizado.

Resultado estructural final: cinco módulos Python propios admitidos por gramática
3.10; catálogo coincidente con los 90 pares/DTO de fase 2; 140 nombres de ruta
únicos tras prefijar alias; ocho hashes coherentes, trece códigos de redacción y
168 enlaces locales existentes en ocho documentos. Sin incidencias estructurales;
no acredita instalación, matching, efectos o seguridad en ejecución.

Antes de aceptar los lotes: verificar contratos de body/query, encoded/slash,
todos los verbos y alias, auth raw, efectos/cola/TX, roles, fallos parciales,
textos redactados, `204`/HEAD/headers y redacción de logs; además lifecycle,
instalación/imports y puertas previas. WebSocket, SPA/assets/tiles, documentación,
ownership definitivo, perfiles, rollback y adopción permanecen en fases 4–6.
