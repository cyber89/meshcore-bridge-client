# Fase 1: seguridad perimetral del candidato ASGI

Fecha: 2026-10-09. Base: `e8a7030` y checkout existente. Preparación autorizada,
conservando la instrucción de continuar **sin ejecutar suites**. El líder integra
especialistas de política, middleware y transporte; revisión cruzada de lectura.

Estado: controles escritos para el candidato, **sin activación ni aceptación
operativa**. No se instaló el extra web, no se importó la aplicación y no se
arrancaron servicios, estación virtual, navegador, radio o broker.

## Componentes y orden

| Componente | Responsabilidad |
| --- | --- |
| [access_policy.py](../../src/web/access_policy.py) | Política neutral de credenciales, Origin, rutas protegidas, límites y headers, basada en el servidor vigente |
| [asgi_http.py](../../src/web/asgi_http.py) | Cabeceras crudas antes de H11, deadline, una petición por conexión, abort de cuerpo y adaptación de métodos |
| [asgi_security.py](../../src/web/asgi_security.py) | Inspección, cuerpo acotado, auth, CORS/HEAD, errores de ingreso y reservas WS |
| [asgi_logging.py](../../src/web/asgi_logging.py) | Logger privado por instancia, sin query en mensajes de upgrade ni valores crudos de excepciones |
| [asgi_websocket.py](../../src/web/asgi_websocket.py) | Backend SansIO fijado y política local de logs, sin modificar credenciales o logger global |
| [asgi_server.py](../../src/web/asgi_server.py) | Fábrica FastAPI protegida, configuración explícita HTTP/WS y lifecycle de la entrega anterior |

HTTP: cabeceras crudas → parsing H11 → inspector sobre path sin query y peer →
cuerpo → OPTIONS/tiles → autenticación sobre ruta cruda, antes de aliases → app.
WS: parsing del backend → inspector → Origin → reserva de cupo → autenticación →
app o rechazo antes de aceptar. No hay endpoints de negocio, WS, SPA ni OpenAPI.

La subclase FastAPI coloca el guard **fuera** de `ServerErrorMiddleware`. Añadirlo
sólo con `add_middleware` dejaría sin el wrapper de headers los 500 generados por
el framework. Se inspeccionó el hook en FastAPI 0.143.0 y Starlette 1.7.0; su orden
y los hooks Uvicorn 0.54.0 necesitan revisión al cambiar esas versiones.
La configuración desactiva `Server`/`Date` automáticos del backend, además de
proxy headers y access log HTTP; conserva el conjunto de cabeceras explícito.

## Política conservada

- `X-Api-Key` no vacía tiene prioridad; una incorrecta no se sustituye con query
  correcta. Query requiere exactamente un `api_key` con decodificación estricta.
  Comparación UTF-8 con `hmac.compare_digest`; Bearer no se incorpora.
- La clave y allowlist se leen del entorno por decisión. Sin clave se conserva el
  bypass de desarrollo. Las lecturas sensibles, prefijos administrativos y
  mutaciones mantienen el guard de la [línea base](WEB_CONTRACT_BASELINE.md).
- OPTIONS conserva 204 sin auth; tiles GET públicos y otros métodos 405 antes de
  auth. Los métodos se normalizan como el servidor actual, antes de H11 y en el
  scope virtual, manteniendo el tratamiento HEAD por el parser.
- Origin REST rechazado omite ACAO; WS rechazado responde 403. Se conserva la
  política amplia de Host/allowlist/localhost/IP privadas, incluidos sus defectos
  de parsing IPv6 y rangos. No se presenta como endurecimiento de allowlist.
- Cabeceras normales: nosniff, DENY, Referrer-Policy, Connection close; HTML añade
  la CSP vigente. CORS normal y preflight conservan sus diferencias de métodos y
  cabeceras. Preflight y el 413 mantienen sus excepciones a la construcción normal.
- El inspector sigue siendo heurístico. No inspecciona aquí query o cuerpo JSON
  como contenido malicioso ni certifica seguridad integral. Los logs del candidato
  omiten query, cabeceras y cuerpo de la petición en sus eventos de rechazo.

## Lectura y recursos

El protocolo cuenta request line y líneas de cabecera originales hasta 65.536
bytes, excluyendo la línea vacía final, antes de alimentar H11. El timer es el
deadline existente de 10 s; no se rearma por fragmento. Se cancela al completar,
rechazar, hacer upgrade, perder la conexión o apagar. El buffer de ingreso no
promueve cuerpo coalescido a cabecera; tras upgrade lo entrega al protocolo WS.
Un primer ciclo HTTP fuerza cierre y no despacha una segunda petición pipelined.

El guard valida Content-Length/Transfer-Encoding, comprueba el límite de 1 MiB
antes de extender el acumulador y usa un único deadline de 10 s para lectura del
cuerpo completo. JSON debe ser objeto; ausencia/longitud cero conserva `{}`.
La decodificación acotada se deriva a un thread, sin I/O, estado de radio o disco.
Cancelar el await no detiene mágicamente una función CPU que ya esté en ese thread.
El parseo conserva el 400 de JSON inválido o profundamente anidado.

`meshcore_body_bytes` y `meshcore_body_json` quedan en `scope.state` para la fase 2;
el receive se reproduce al consumidor sin leer o reconstruir servicios. Timeout
o cuerpo incompleto usa `meshcore.http.abort`: marca el ciclo desconectado antes
de abortar el transporte. No fabrica un 408 ni un fallback 500. Un caller ASGI en
memoria necesita ese hook para el cierre silencioso; si falta, recibe una excepción
controlada sin datos de la petición.

El cupo WS conserva 32 y ahora incluye handshakes pendientes. Comprobar e
incrementar sin await en el único loop evita la carrera de la línea base; `finally`
libera la reserva tras rechazo, excepción, cancelación o fin de la app. No se
inventan colas, límites RF ni intervalos. Se configura 1 MiB de **mensaje** en
SansIO, sin confundirlo con el límite de **frame** del servidor anterior. La
compresión WS y los timers automáticos de ping del backend quedan desactivados;
la equivalencia del heartbeat, idle, frames y mensajes pertenece a fase 4.

## Privacidad de los logs del transporte

La fuente de Uvicorn 0.54.0 muestra tres mensajes INFO de upgrade/denial que
incluyen path y query en `uvicorn.error`, incluso con `access_log=False`. El
adapter por conexión elimina la query únicamente del argumento de esos mensajes,
conservando el scope original para autenticación. También bloquea TRACE/DEBUG de
cabeceras/tramas del backend y su flag de debug precalculado.

Los errores del protocolo conservan tipo y frames de traceback, omitiendo el
mensaje de excepción y el valor de retornos ASGI inválidos. La misma política se
aplica al logger que H11 entrega al ciclo HTTP antes de programar su tarea ASGI.
No se cambian handlers o niveles globales. Esto cubre los caminos inspeccionados;
no acredita redacción universal de logs de negocio, dependencias o instrumentación.

## Revisión, diferencias y aceptación pendiente

Los revisores encontraron y corrigieron: headers omitidos en el 400 previo a
middleware; métodos lowercase/HEAD incoherentes con H11; RecursionError de JSON
que escapaba a 500; logs WS con query; y excepciones HTTP sin redacción. El líder
revisó código y diffs, sintaxis 3.10, imports nominales contra wheels y enlaces.
No ejecutó pytest, cobertura, mypy, Ruff, navegador ni handshakes/HTTP virtuales.
La lectura no demuestra ausencia de carreras ni cumplimiento medido del deadline.

Recibo estático de esta entrega: seis módulos Python analizados con gramática
3.10, 168 enlaces locales de nueve documentos sin destinos ausentes ni fences
desbalanceados, símbolos/configuración nominales contrastados con el wheel fijado
y diff propio sin incidencias de whitespace. La comparación de los 95 hashes de
fase 0 conserva los mismos cuatro cambios de la entrega inicial; los archivos
anteriores ajenos a FastAPI inspeccionados conservan su contenido.

Diferencias explícitas del candidato:

1. La reserva de cupo incluye pendientes y evita un defecto de concurrencia previo.
2. H11/SansIO validan framing y handshake con sus reglas; no se promete aceptar
   toda petición malformada que aceptaba el parser propio. HEAD omite bodies,
   incluidos algunos errores que el parser anterior enviaba con cuerpo.
3. El 413 vacío y los denial WS se encuadran mediante el backend; su equivalencia
   de bytes/headers necesita QA. Sin extensión `websocket.http.response`, el
   fallback rechaza sin aceptar y devuelve 403, sin acreditar paridad 401/429.
4. Los logs de protocolo pierden query y valores de excepciones para proteger las
   credenciales; siguen conservando camino sin query, tipo y frames.

Antes de adoptar: ejecutar casos aislados de fragmentación/coalescencia, límite
exacto/excedido, slow headers/body, cancelación, métodos/HEAD, framing 413,
Origin/clave inválida, cupo concurrente, rechazo WS y ausencia de secretos en logs.
También comprobar lifespan, bind, señales, apagado y recursos de la entrega inicial.
Las suites permanecen suspendidas por instrucción del usuario.

Ownership permanece explícito: el router/contexto/mapa prestados son de la
composición actual; ASGI no los reconstruye ni cierra el mapa. Antes del corte
de producción debe transferirse su cierre al propietario compartido, evitando
que detener el adaptador anterior invalide el mapa prestado al candidato.
El servidor predeterminado y los formatos persistidos siguen vigentes. Las
fases 2–6 y las puertas operativas se mantienen en [PROYECTO.md](../../PROYECTO.md).
