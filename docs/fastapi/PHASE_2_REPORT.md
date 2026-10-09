# FastAPI: preparación de DTO y errores de fase 2

Fecha: 2026-10-09. Base: `9eead69` y checkout con cambios anteriores conservados.
Estado: **preparación escrita y revisión estática**. La aceptación de ejecución
de fases 1 y 2 continúa pendiente; el usuario pidió continuar sin suites.
ASGI sigue inactivo, sin endpoints de negocio, WS, SPA o documentación pública.

## Entrega y reunión técnica

El líder integró tres especialistas: modelos Python, inventario de contratos y
revisión de seguridad. Se utilizaron las skills de Python, contratos API,
seguridad, gobernanza ADR y verificación con el alcance permitido por el usuario.
El reparto de archivos evitó ediciones concurrentes; el líder revisó las fuentes
y concilió la documentación.

| Archivo | Propiedad y propósito |
| --- | --- |
| [request_models.py](../../src/web/request_models.py) | Especialista Python: DTO por familia/operación y esquema documental Problem Details |
| [Inventario](PHASE_2_REQUEST_INVENTORY.json) | Especialista contratos: operación, función, campos observados y reglas de entrada |
| [Casos sanitizados](PHASE_2_COMPATIBILITY_CASES.json) | Líder con revisión: ejemplos esperados por lectura, sin ejecutar |
| [asgi_errors.py](../../src/web/asgi_errors.py) | Líder: JSON sin filtro y errores seguros del framework |
| [asgi_server.py](../../src/web/asgi_server.py) | Líder: registra handlers únicamente en la fábrica candidata |

La decisión técnica es conservar el contrato de entrada antes de endurecerlo.
Un modelo con `int`/`bool`/regex obligatorios cambiaría coerciones, prioridad y
códigos que hoy decide cada operación. Los modelos preparatorios emplean `Any`
para valores externos y `extra="allow"`; no constituyen validación exhaustiva
del dominio. La validación y las restricciones de identidad, rol, bytes UTF-8,
capacidad de canales y parámetros de firmware permanecen en los controladores,
servicios y SDK actuales. No se permite enviar RF por superar un DTO.

## Presencia, coerción y respuestas

`to_legacy_body()` usa `model_dump(mode="python", exclude_unset=True)`: conserva
valores suministrados, incluidos `null`, falsos, listas, objetos y campos extra;
no añade defaults ausentes ni elimina `None`. No garantiza orden original de
claves. Sólo se destina a mappings procedentes de JSON, no a objetos arbitrarios
internos. No se usa `strict=True`, normalización, validación anidada o límite
global de caracteres. El uso efectivo en endpoints y su comprobación se difieren
a las fases de rutas y QA.

El inventario distingue cuerpo de query. El router combina query con
`keep_blank_values=True`, mantiene repetidos como listas y conserva un campo del
cuerpo incluso si vale `null`. `LogsController` vuelve a leer la query original
con `parse_qs` **sin** `keep_blank_values`, selecciona el primer valor restante
y no consume el cuerpo combinado. El futuro adaptador debe conservar el target
original para esos lectores y para auth; los DTO no sustituyen ese procesamiento.

Los ejemplos incluyen destino ausente frente a nulo, prioridad de `to`, valores
sin recortar, `int(True)`/`int(2.9)`, parámetros repetidos, extras anidados y campos
de fallo parcial. Son expectativas derivadas de fuentes, **no resultados de
ejecución ni pruebas aprobadas**. Se conservan `400` para LOCAL/REPEATER y
`400`/`422` por validación actual. No se introduce `202`, otro timeout TX,
`Retry-After`, nuevos límites o reintentos.

`legacy_json_response()` conserva `json.dumps(indent=2, default=str)`, UTF-8 y
`application/json`. Para `204` emite cuerpo vacío, `Content-Length: 0` y ningún
Content-Type. La supresión de cuerpo HEAD y headers de seguridad/CORS permanecen
en el middleware exterior. No usa `jsonable_encoder` ni filtra resultados;
`partial`, `applied`, `config`, `action`, `dispatched_commands`, `target_node` y
datos dinámicos llegan completos. El esquema `ProblemDetailsDTO` sirve para
documentación futura; **no** se conecta como `response_model` ni serializador de
respuestas existentes. Tampoco se utiliza para auth o tiles.

## Errores, secretos y alcance

Los handlers registrados en el candidato reutilizan el helper de siete campos
`type/title/status/detail/error/message/timestamp`:

- Una excepción explícita de compatibilidad transporta status/mensajes/código
  elegidos por el adaptador. Sus textos deben ser públicos y revisados.
- `RequestValidationError` tiene un fallback `422` con mensaje fijo. No se lee
  `errors()`, `body`, `input`, `ctx` o texto de excepción; no se convierte por
  ello toda validación de negocio en `422`.
- `HTTPException` devuelve un fallback seguro. `404`/`405` tienen códigos
  canónicos y mensajes fijos; otros status se conservan con texto genérico,
  sin reflejar detail o headers arbitrarios. No añade Allow/Retry-After.
- Una excepción ordinaria propagada genera `500` con mensaje fijo, sin
  `str(exception)`. Se registra `Exception`, no `BaseException`, manteniendo
  fuera las cancelaciones. Starlette vuelve a lanzar después de responder;
  el protocolo candidato conserva su logger sanitizado por instancia.

Los mensajes `404`/`405` del framework no reproducen todos los mensajes de
fallback por familia del router. Al portar rutas se deberán usar las respuestas
de esas familias y sus alias; no se acredita paridad por registrar estos handlers.
Los errores de ingreso de fase 1 conservan sus envoltorios propios, por ejemplo
`{error: Unauthorized}`, JSON malformado, límites y rechazo WS antes de aceptar.

`repr`, `str` y representación enriquecida de los DTO omiten valores conocidos
y extras; `hide_input_in_errors=True` añade una defensa de representación, pero
no autoriza publicar `ValidationError.errors()`. Los DTO no deben incorporarse
a logs ni ejemplos con credenciales.

**Pendiente explícito para fase 3:** el router actual captura excepciones y
devuelve `500` con `str(e)`, además de logs que interpolan la excepción. Esas
respuestas no pasan por un handler de excepción ASGI. También hay errores
retornados de otras operaciones con detalles dinámicos; no se declara redacción
global por este cambio. `_parse_bounded_int` refleja el valor rechazado en un
`400`, por lo que también requiere revisión explícita de redacción. La integración
deberá revisar esos caminos y las salidas
de configuración/admin/servicios sin perder códigos o extensiones ni añadir
logs que contengan secretos. Los handlers HTTP tampoco sustituyen el protocolo
de errores WebSocket de fase 4.

## Evidencia y puerta pendiente

Se inspeccionaron fuentes del proyecto y APIs de los wheels Pydantic 2.14.0,
FastAPI 0.143.0 y Starlette 1.7.0 mediante ZIP/AST, sin importar ni instalar esos
paquetes. La comprobación final de AST con gramática Python 3.10, estructura JSON,
referencias locales y diff sólo acredita esos artefactos. El inventario conserva
procedencia y límites de extracción; parámetros de comandos abiertos y campos
consumidos indirectamente no constituyen un esquema cerrado.

La comprobación final encontró tres módulos Python sintácticamente compatibles
con gramática 3.10, 26 clases, 90 pares método/ruta únicos, 69 rutas, 39 alias y
50 operaciones de alias, 16 hashes y 80 referencias de funciones coherentes,
23 ejemplos documentales y 150 enlaces locales existentes en siete documentos.
El conjunto de operaciones coincide con el catálogo de fase 0 por lectura de
filas; no hubo incidencias estructurales. Esto no ejecuta ninguno de los casos.

No se ejecutaron pytest/cobertura, mypy, Ruff, navegador, handlers, DTO, imports
del candidato o servicios. No se modificó el servidor predeterminado, controles
de negocio, frontend, referencias, datos operativos o parámetros de radio.

La aceptación requiere comprobaciones autorizadas de presencia/coerción/extras,
errores de negocio y framework, `204`/HEAD/headers, respuestas parciales y secretos,
junto a las puertas operativas pendientes de fase 1. La fase siguiente prepara
las rutas por lotes, preservando contexto y controllers; esto no aprueba la
adopción de producción ni el retiro del servidor anterior.
