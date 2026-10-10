# ADR 0011: Migración gradual y adopción del transporte FastAPI ASGI

- **Estado**: ASGI adoptado en código y transporte nativo retirado; aceptación operativa pendiente.
- **Lectura**: Contexto y decisión iniciales son históricos. La evolución actual al final prevalece para describir la implementación.
- **Fecha**: 2026-10-08
- **Autores**: Líder e investigadores de backend, contratos, seguridad e instalación
- **Base**: `457903d` y árbol de trabajo existente

## Contexto y Problema

[PROYECTO.md](../../PROYECTO.md) propone migrar el transporte web a FastAPI.
El servidor actual integra HTTP, WS y estáticos; el router conserva contexto,
canales, historiales y mapas utilizados también por el core. La migración no puede
duplicar el bridge ni romper contratos REST/WS o instalar dependencias por sorpresa.
El usuario pidió comenzar las fases secuencialmente y continuar sin suites.

## Factores de Decisión

- Python 3.10 mínimo, headless y dependencias opcionales.
- Paridad REST/WS/SPA y propiedad única de radio, MQTT y estado de negocio.
- Señales del core y límite actual de cierre por subsistema de 1,5 s.
- Evidencia binaria de seis destinos, separada de evidencia operativa ausente.
- Cambios anteriores en el checkout que deben conservarse fuera de esta entrega.

## Decisión

Preparar un seam neutral y un adaptador ASGI opcional usando FastAPI 0.143.0,
Uvicorn 0.54.0, Pydantic 2.14.0 y websockets 16.1.1. Declarar esos candidatos en
el extra `web`, sin activar ASGI en la fábrica del bridge. Diferir imports concretos
del servidor actual y conservar exports de compatibilidad. La fábrica ASGI recibirá
el router existente; no creará radio, MQTT o schedulers.

El servidor actual continúa siendo el predeterminado. El adaptador inicial no
contiene endpoints de negocio, WS ni SPA; no se ofrece como sustituto operativo.
Seguridad perimetral, DTO, rutas, WS, documentación e instaladores se trasladarán
en las fases de [PROYECTO.md](../../PROYECTO.md), conservando sus puertas.

No ejecutar suites por instrucción expresa del usuario. Lectura de fuentes,
análisis sintáctico y revisión de metadatos documentan preparación; no reemplazan
las puertas de ejecución para adoptar o retirar un servidor.

## Consecuencias

El core conserva estado y lifecycle; headless puede evitar imports del servidor
concreto, aunque la ausencia de imports transitivos aún requiere comprobación en
ejecución. Los manifiestos opcionales permiten preparar integración futura sin
alterar la instalación habitual. Temporalmente hay dos adaptadores; sólo el actual
está conectado al core. Las bibliotecas candidatas no se instalaron en su entorno.

Riesgos de señales, bind, lifespan, cancelación y cierre quedan registrados en los
[contratos internos](../fastapi/INTERNAL_CONTRACT_BASELINE.md) y el
[informe de fase 1](../fastapi/PHASE_1_REPORT.md). La aceptación de producción
queda pendiente de paridad y verificación autorizada; no se aprueba por disponer
de wheels ni por publicar esta preparación.

## Evolución del 2026-10-09

Se preparó la [seguridad perimetral ASGI](../fastapi/PHASE_1_SECURITY_REPORT.md):
política neutral de credenciales/Origin/headers, guard de body y reservas WS,
protocolo H11 con límite/deadline de cabeceras y logs de protocolo por instancia
sin query o valores de excepciones. El orden del middleware cubre también headers
de los 500 del framework. Las diferencias de framing, handshake y reserva se
registran expresamente; no se certifica paridad mediante lectura. La fábrica sigue
seleccionando el servidor anterior y las suites permanecen suspendidas.

### Preparación de fase 2

Se añadieron [DTO y errores](../fastapi/PHASE_2_REPORT.md): modelos de frontera
permisivos que conservan presencia, valores y extras; esquema Problem Details
documental sin filtro de respuestas; serialización JSON compatible y handlers
del framework con mensajes seguros. El inventario relaciona operaciones con
fuentes y modelos. No se activan endpoints ni imports del candidato en producción.

Los controladores mantienen validación, coerción y dominio. Sus errores
retornados y logs pueden incluir detalles que los handlers no interceptan;
la fase de rutas debe abordar esa redacción expresamente. Las puertas de
ejecución y la adopción siguen pendientes, sin relajar la instrucción del usuario.

### Preparación de fase 3

Se añadieron [seis lotes REST](../fastapi/PHASE_3_REPORT.md) al candidato, con
90 operaciones JSON canónicas y 50 de alias, sin activar su fábrica en el core.
Los endpoints Request-only prestan el dispatcher/contexto y conservan target y
body originales. Se adaptan matching raw y fallback de métodos/slashes a la
fuente de FastAPI 0.143.0, sin duplicar controladores o efectos.

La redacción selectiva del candidato conserva códigos/extensiones de fallo;
el catch global y errores de enteros compartidos eliminan textos de excepción
y valores recibidos. Son correcciones explícitas de seguridad. No se afirma
redacción global de logs o salidas arbitrarias. Tiles, WS, SPA, OpenAPI completo,
puertas operativas y adopción permanecen pendientes en el plan.

### Preparación de fase 4

La [fase 4](../fastapi/PHASE_4_REPORT.md) registra WS en cualquier ruta, SPA/estáticos
y teselas en la fábrica inactiva. El hub conserva bienvenida, métricas y heartbeat
JSON, historial una vez y orden por cliente. Se prestan mapas/estado sin cerrar
el servicio del router. El propietario aporta un plazo de cierre común a hub,
Uvicorn y lifespan; métricas y ping idle heredados no consultan radio ni MQTT.

Se reservan las rutas de docs con 404 y se refuerza pertenencia del fallback
index.html. El backend valida RFC y admite fragmentación; su contrapresión,
timing de chunks y buffers no equivalen al framing nativo. Estas diferencias,
workers de filesystem pendientes y puertas de ejecución se registran expresamente.
La preparación no decide adopción ni retira el servidor actual; las suites siguen suspendidas.

### Preparación de fase 5

La [fase 5](../fastapi/PHASE_5_REPORT.md) prepara la especificación OpenAPI 3.1.0 diferida
y el visor local de documentación offline en `/docs`, `/redoc` y `/openapi.json`.
Se describe el catálogo completo de 70 rutas (69 JSON y 1 de teselas), 90 operaciones
canónicas, 50 alias y 25 esquemas DTO. El visor reside en recursos locales propios sin
dependencias de CDN; implementa autenticación estricta por cabecera `X-Api-Key`, rechazo
de credenciales en URLs, CSP restrictivo y política de solo lectura sin herramientas de
ejecución que puedan emitir transmisiones LoRa accidentales.

El candidato ASGI permanece inactivo en la configuración predeterminada del bridge.
Las puertas operativas, suites de pruebas automatizadas y adopción en producción continúan
pendientes para la fase 6, respetando la instrucción de suspender ejecución de suites.

### Evolución de fase 6 y auditoría por capas

El checkout selecciona `AsgiWebServer` en `bridge_core.py`; `933ccce` retiró
`src/web/http_server.py`. No hay selector ni fallback nativo. Se reutiliza el router
con controladores y estado existente: no es otro servidor HTTP. REST, WS, SPA,
teselas y documentación local están registrados en la composición ASGI.

`requirements.txt` instala la pila web y `requirements-web.txt` es un shim de
compatibilidad. El checker distingue los cuatro mínimos core de seis pins web:
FastAPI 0.143.0, Uvicorn 0.54.0, Pydantic 2.14.0, websockets 16.1.1,
Starlette 1.7.0 y h11 0.16.0. Headless (`WEB_ENABLED=false`) evita construir el
servidor; el perfil del checker no cambia esa configuración ni demuestra ausencia
de imports transitivos.

Se retiran garantías anteriores sobre RSS, viabilidad SBC, reducción neta de
líneas y rollback atómico global. La actualización escalonada intenta revertir
componentes; no es una transacción indivisible. El presupuesto web comparte un
plazo; el cierre de todos los subsistemas no tiene una garantía global de 1,5 s.
Los workers de disco no se pueden detener forzosamente al cancelar al solicitante.

La [auditoría actual](../audits/2026-10-09-layer-audit.md) registra propiedad y cierre
de tareas, mapas y escrituras, saneamiento de errores y eliminación de símbolos
sin consumidores encontrados. No se añaden consultas RF, timers ni intervalos.
El callback de fallo web comunica terminación al propietario sin reinicio automático.

Los DTO son metadatos permisivos para OpenAPI; los controladores mantienen la
validación. `/docs` y `/redoc` sirven un visor propio offline de solo lectura, no
bundles Swagger/ReDoc. Generación, paridad, autenticación, cancelación, recursos e
instalación en ejecución continúan pendientes por la instrucción de no ejecutar suites.
