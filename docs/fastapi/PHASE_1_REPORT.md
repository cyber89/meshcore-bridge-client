# FastAPI: base opcional de infraestructura de fase 1

Fecha local: 2026-10-08. Continuación de [fase 0](PHASE_0_REPORT.md).
Estado actualizado el 2026-10-09: **infraestructura y seguridad perimetral
preparatorias escritas y revisadas estáticamente**; integración y aceptación
operativa pendientes. No se declara
la fase 1 aprobada en ejecución ni se activa el candidato.

## Cambios y propiedad

| Archivo | Cambio | Propietario |
| --- | --- | --- |
| [pyproject.toml](../../pyproject.toml) | Extra opcional `web` con cuatro pins candidatos; core y Python mínimo conservados | Instalación |
| [requirements-web.txt](../../requirements-web.txt) | Manifest explícito core + web derivado; no lock transitivo | Instalación |
| [server_protocol.py](../../src/web/server_protocol.py) | Seam neutral de lifecycle, bridge prestado, router e historial/difusión | Backend |
| [asgi_server.py](../../src/web/asgi_server.py) | Fábrica vacía y adaptador Uvicorn en el loop activo; no conexión al core | Backend |
| [bridge_core.py](../../src/bridge_core.py) | Anotación neutral e import concreto después de `WEB_ENABLED` | Líder |
| [src/__init__.py](../../src/__init__.py), [web/__init__.py](../../src/web/__init__.py) | Exports web históricos diferidos mediante `__getattr__` | Líder |
| [Fixture](../../tests/test_bridge_core_comprehensive.py) | Cambia el punto de patch al módulo de la clase diferida; expectativas conservadas | Líder |

La preparación no instala los candidatos en el entorno existente. Los comandos
habituales de instalación y la fábrica del core siguen utilizando el servidor
HTTP/WS vigente. El extra sólo declara dependencias para integración posterior.
Su rango dev `websockets>=15.0.0` admite el pin candidato 16.1.1; no se ha resuelto
ni comprobado aquí todo el extra QA en conjunto.

## Contrato del adaptador preparatorio

`create_asgi_app(router)` recibe la instancia existente, comparte `api_ctx` y
conserva referencias prestadas. No crea bridge, radio, MQTT, mapas ni tareas al
importar el módulo. El lifespan se limita a web; el adaptador no cierra el mapa
prestado, cuya propiedad debe conciliarse al hacer el corte definitivo.

La app está deliberadamente vacía: sin endpoints de negocio, WS, SPA, tiles,
OpenAPI, Swagger ni ReDoc. `application_contract_ready=False` declara ese estado.
La llegada del listener a readiness no acredita contratos funcionales. No hay
fallback silencioso ni selección de ASGI mediante configuración de producción.

El servidor utiliza `Server.serve()` en el loop del propietario, un worker,
sin reload, adaptadores de `h11` y `websockets-sansio`, lifespan explícito y
`proxy_headers=False`. La subclase localizada para Uvicorn 0.54.0 deja las señales
al core. El arranque espera readiness del listener/lifespan y observa terminación
temprana de la tarea; convierte `SystemExit` de Uvicorn dentro de esa tarea en un
fallo ordinario. Cancelaciones conservan su propagación.

El wrapper de lifespan conserva la tarea creada antes de cualquier espera: la
revisión encontró que registrarla únicamente al entrar en el contexto FastAPI
dejaba una ventana de cancelación. Esta adaptación reproduce el arranque de
`LifespanOn` del wheel fijado y necesita revisar API/fuente y repetir verificación
autorizada si cambia la versión de Uvicorn.

`shutdown_budget_s` es obligatorio: el futuro propietario deberá pasar el
presupuesto actual de 1,5 s del core. El adaptador comparte cleanup, solicita salida,
cierra admisión y aplica un deadline conjunto; ante cancelación fuerza cierre de
listeners/conexiones y cancela sus tareas. Conserva referencias y callbacks que
recuperan excepciones. Una tarea que resista cancelación impide reinicio; no se
promete eliminarla mágicamente ni se extiende el presupuesto del propietario.

Un fallo posterior se registra en `failure` y puede observarse por `wait_closed()`
o callback `on_failure`. La futura integración deberá conectar esa supervisión
al lifecycle del core; actualmente no hay adaptación de producción conectada.
`broadcast_event` registra el historial una vez; su entrega WS queda para fase 4.
`bridge=router.bridge` conserva el fallback de logs CLI sin duplicar el propietario.

## Revisión técnica y pendientes

El líder revisó directamente los diffs y el código. El reviewer de seguridad y
contratos contrastó fuentes de Uvicorn y consumidores del proyecto, y señaló:

- Ventana de lifespan huérfano antes de entrar en el contexto ASGI: tarea retenida
  desde su creación en el wrapper localizado.
- Default de confianza en proxy de Uvicorn: desactivado expresamente.
- Dependencia CLI de `web_server.bridge`: referencia prestada conservada.
- Matices REST sobre alias cartográfico, código TX oculto y `408 Unknown`:
  registrados en la línea base, sin alterar funciones de negocio.

La inspección de la entrega inicial del 2026-10-08 usó AST con gramática 3.10 de los siete archivos Python propios,
correspondencia de manifests, 157 enlaces locales de ocho documentos y whitespace
documenta estructura y sintaxis. La comparación de los 95 hashes de fase 0 sólo
encontró los cuatro archivos previstos modificados por esta fase; los cambios
anteriores del checkout conservan su contenido. **No prueba** imports transitivos,
tipado estricto, ausencia de carreras, bind, lifespan, señales o apagado real.
No se ejecutaron suites, cobertura, mypy, Ruff ni navegador, conforme al usuario.
El fixture se adaptó por lectura; no se afirma que esté aprobado en ejecución.

La continuación de seguridad del 2026-10-09 se documenta en
[PHASE_1_SECURITY_REPORT.md](PHASE_1_SECURITY_REPORT.md): auth, Origin, headers,
lectura, reservas WS y privacidad de logs están conectados al candidato inactivo.

Antes de aceptar fase 1 y portar DTO/rutas:

1. Verificar en ejecución las políticas trasladadas REST/WS de autenticación,
   Origin/CORS, inspector, límites de lectura y cabeceras del
   [catálogo web](WEB_CONTRACT_BASELINE.md), incluidas diferencias registradas.
2. Decidir el ownership definitivo de mapas, tareas y canales conforme al
   [contrato interno](INTERNAL_CONTRACT_BASELINE.md), evitando duplicación.
3. Cuando se autorice ejecución, verificar arranque cancelado/fallido, puerto
   ocupado, lifespan fallido, señales, stop concurrente/repetido, cleanup y
   supervisión posterior con loopback y recursos temporales.
4. Comprobar imports headless y funcionamiento con los candidatos instalados en
   un entorno aislado; comparar recursos sin inventar presupuestos numéricos.

No se retira el servidor anterior, no se añade tráfico RF, no se rearman timers
de radio y no se cambian límites/intervalos de la malla. Las fases 2 a 6 siguen
pendientes en [PROYECTO.md](../../PROYECTO.md).
