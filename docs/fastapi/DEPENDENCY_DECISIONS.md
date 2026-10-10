# Fase 0: dependencias, instalación y compatibilidad

**Evolución 2026-10-10:** el baseline actual es Python estable >=3.14.8 y
websockets 17.2. Los destinos 3.10/3.12 siguientes son históricos, ya no soportados.
Consulte el [informe de modernización](../PYTHON_314_MODERNIZATION_REPORT.md).

Este documento conserva las decisiones y seis resoluciones de fase 0 como
evidencia histórica. El estado de adopción e instalación vigente se describe en
la evolución de auditoría al final y en [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md).
Las referencias a perfiles opcionales y tareas pendientes de las primeras fases
deben leerse en la fecha de esas fases, no como selector actual de servidor.

Fecha: 2026-10-08. Responsable: agente de release, integrado por el líder de la
migración. Skill aplicada: `installer-release-maintenance`. Esta decisión prepara
la implementación. La fase 1 declara un extra web opcional y su manifest derivado;
las dependencias core, el manifest habitual y los instaladores mantienen el
comportamiento existente. No se instalaron los candidatos en el entorno operativo
ni se arrancaron servicios, radio o suites para esta revisión.

## Alcance acordado

El usuario respondió «no importa» a la selección de equipos y límites de recursos.
Se adopta una matriz de evaluación concreta, sin inferir soporte universal ni un
presupuesto de RAM/CPU/arranque:

| Destino de resolución | Intérprete | ABI/arquitectura | Alcance |
| --- | --- | --- | --- |
| Windows x64 | CPython 3.10 y 3.12 | `cp310`/`cp312`, `win_amd64` | Dependencias binarias; falta ejecución en cada destino |
| Linux x64 con glibc >=2.17 | CPython 3.10 y 3.12 | `cp310`/`cp312`, `manylinux2014_x86_64` | Dependencias binarias; falta ejecución en cada destino |
| Linux ARM64 con glibc >=2.17 | CPython 3.10 y 3.12 | `cp310`/`cp312`, `manylinux2014_aarch64` | Dependencias binarias; falta ejecución en cada destino |

Python 3.10 sigue siendo el mínimo del proyecto. Linux musl, ARM de 32 bits,
Windows ARM64, macOS, PyPy y otras versiones de Python no están acreditados por
esta matriz. Los modelos de SBC mencionados en la guía de despliegue tampoco
quedan certificados por disponer de wheels ARM64. No se altera la especificación
`requires-python >=3.10` como efecto de una revisión documental.

## Conjunto candidato y evidencia

La entrada es [candidate.in](dependencies/candidate.in). Es un conjunto de
evaluación fechado, no una autorización para actualizar producción:

| Dependencia directa | Versión evaluada | Motivo |
| --- | --- | --- |
| FastAPI | 0.143.0 | Frontera REST/ASGI; METADATA exige Python >=3.10 |
| Uvicorn | 0.54.0 | Servidor integrado en el loop existente; Python >=3.10 |
| Pydantic | 2.14.0 | DTO de la frontera web; Python >=3.10 |
| websockets | 16.1.1 | Backend WS de producción explícito; Python >=3.10 |
| meshcore | 2.3.8 | Mantener la versión instalada del SDK durante la evaluación |
| paho-mqtt | 2.1.0 | Mantener la versión instalada durante la evaluación |
| pyserial | 3.5 | Mantener la versión instalada durante la evaluación |
| python-dotenv | 1.2.3 | Mantener la versión instalada durante la evaluación |

Las versiones proceden del METADATA descargado, no de una suposición sobre
«latest». La resolución usa `uv 0.12.24` local al directorio de artefactos, con
marcadores del destino, y entrega estos seis conjuntos:

- [Windows / CPython 3.10](dependencies/win-cp310.txt) y [3.12](dependencies/win-cp312.txt).
- [Linux x64 / CPython 3.10](dependencies/linux-x64-cp310.txt) y [3.12](dependencies/linux-x64-cp312.txt).
- [Linux ARM64 / CPython 3.10](dependencies/linux-arm64-cp310.txt) y [3.12](dependencies/linux-arm64-cp312.txt).

Los `compile.log` en `artifacts/fastapi-phase0/<destino>/` registran 34 paquetes
para Windows 3.10, 32 para Windows 3.12, 26 para Linux 3.10 y 24 para Linux 3.12.
El [recibo de resolución binaria](dependencies/resolution.json), cuya marca
`generated_at_utc` identifica la ejecución de la auditoría, registra los seis destinos con
`issues=[]`. Incluye hash de la entrada y de cada manifest, nombre/versión/archivo,
SHA-256 y tags de cada wheel, plataformas aceptadas por destino, bytes descargados,
`Requires-Python`, `Requires-Dist` y entorno de marcadores. La auditoría se ejecutó
con CPython 3.12.14 local y
[`audit_fastapi_phase0.py`](../../scripts/audit_fastapi_phase0.py), sin instalar
ni importar los candidatos. La revisión comprueba identidad del nombre/versión
del archivo contra METADATA, presencia y versiones fijadas, tags nominales,
restricciones de Python y clausura de dependencias para cada entorno declarado.

Los tags del destino se seleccionaron en las descargas `pip --only-binary=:all:`.
El auditor también compara los tags del nombre de cada wheel contra los tags
CPython/ABI/plataforma compatibles con el destino. Para el piso glibc 2.17 de
Linux x64 admite los tags manylinux compatibles de glibc anterior; no requiere
que un wheel declare exactamente manylinux2014. No ejecuta las extensiones nativas
ni reproduce el cargador del destino. El recibo declara el índice público
`https://pypi.org/simple`, y los logs de descarga se conservan bajo
`artifacts/fastapi-phase0/`; no se registran URLs individuales por wheel.
Los hashes describen los archivos descargados, sin autenticación independiente
del editor. La matriz de
wheels queda acreditada en ese alcance; runtime, ABI en ejecución, ciclo de vida
del bridge y rendimiento siguen expresamente sin verificar.

La primera resolución con `pip` y parámetros de destino se descarta como evidencia
de cierre: evaluó algunos marcadores en el host Windows/Python 3.12, omitió
`exceptiongroup` y `async-timeout` para destinos 3.10 y arrastró WinRT a Linux.
Conservar el log histórico no lo convierte en un resultado aprobado.

### Transitivas que cambian el análisis

La lectura con `zipfile` del METADATA de wheels, sin importar esos paquetes,
confirma las siguientes relaciones:

| Paquete padre | Restricción observada | Resultado candidato / consecuencia |
| --- | --- | --- |
| FastAPI 0.143.0 | `starlette>=0.46.0`, `pydantic>=2.9.0` | Starlette 1.7.0 y Pydantic 2.14.0; la combinación exige validación de contratos |
| FastAPI 0.143.0 | `opentelemetry-api>=1.44.0` | API 1.45.1 es obligatoria incluso sin extras; no se añadió un exporter ni SDK |
| Starlette 1.7.0 | `anyio>=4.0.0,<5` | AnyIO 4.15.1 |
| Pydantic 2.14.0 | `pydantic-core==2.50.0` | Extensión nativa exacta; auditar wheel por destino |
| AnyIO 4.15.1 | `exceptiongroup>=1.0.2` si Python <3.11 | 1.3.1 sólo para 3.10 |
| meshcore 2.3.8 | `bleak`, `pycayennelpp`, `pycryptodome`, `pyserial-asyncio-fast` | Son transitivas del SDK aunque el bridge tenga su propio decodificador |
| Bleak 3.0.2 | `async-timeout>=3.0.0` si Python <3.11 | 5.0.1 sólo para 3.10 |
| Bleak 3.0.2 | WinRT si `sys_platform=='win32'`; dbus-fast si Linux | WinRT 3.2.1 en Windows; dbus-fast 5.0.26 para Linux 3.10 y 5.2.0 para Linux 3.12 |

La variante dbus-fast demuestra por qué no debe reutilizarse un lock de 3.12 en
3.10. PyCryptodome, pydantic-core, websockets y los bindings de plataforma del SDK
requieren revisar artefactos binarios. No fijar esas transitivas manualmente contra
la restricción del padre. Los seis `.txt` son snapshots de resolución por destino,
no locks de instalación con hashes; la futura instalación reproducible requiere
constraints/locks y verificación de hashes acordes con su formato.

### Comprobación estática adicional para Python 3.10

Se analizaron con `ast.parse(feature_version=(3, 10))` 332 archivos `.py` de los
wheels: Uvicorn (45), Starlette (36), FastAPI (52), AnyIO (46), Pydantic (105) y
websockets (48). No aparecieron errores de sintaxis para esa gramática. Esto usa
el parser del intérprete local; no equivale a ejecutar cada import en Python 3.10.

La inspección de los usos/imports relevantes aporta evidencia adicional:

- Uvicorn importa `assert_never` de `typing_extensions` bajo Python <3.11, usa
  `asyncio.wait_for` para cierre y conserva implementación de `asyncio_run` para
  3.10 en `_compat.py`; `asyncio.Runner` está en la rama >=3.11.
- Starlette importa `BaseExceptionGroup` desde `exceptiongroup` bajo 3.11 y
  `Self` de `typing_extensions` en su TestClient bajo 3.11. AnyIO aplica esos
  backports, incluido un Runner propio para 3.10 en el backend asyncio.
- Pydantic importa `Self` y `assert_never` desde `typing_extensions` en los
  archivos observados. La resolución incorpora `typing-extensions==4.16.0`.
- websockets importa `asyncio.timeout`/`timeout_at` en su módulo de compatibilidad
  sólo bajo Python >=3.11; en 3.10 usa su implementación incluida de
  `async_timeout`. Esa copia interna no elimina la dependencia externa de Bleak.

La búsqueda AST no detectó llamadas directas `asyncio.TaskGroup` ni
`asyncio.timeout` en esos archivos; la importación con alias de timeout está
condicionada como se describe arriba. El análisis sintáctico tampoco detectó
`except*`, que la gramática 3.10 rechazaría. Estos resultados cubren esas señales
concretas, no todos los caminos de runtime ni las extensiones nativas.

## Decisión de perfiles para las fases siguientes

Se adopta [`pyproject.toml`](../../pyproject.toml) como fuente canónica de
dependencias **directas**. La fase 1 incorpora `project.optional-dependencies.web`
con los cuatro pins de la tabla y
[`requirements-web.txt`](../../requirements-web.txt), derivado de ese extra y
con referencia al core en `requirements.txt`. Este perfil prepara la instalación
explícita de core + ASGI; no activa otro servidor, modifica el perfil predeterminado
del instalador ni instala paquetes en esta tarea. Se comprueba la igualdad de
los cuatro pins por lectura TOML/requirements. Separar:

1. Core: dependencias actuales de radio/MQTT/persistencia.
2. Extra `web`: FastAPI, Uvicorn, Pydantic y backend websockets explícito.
3. Desarrollo/QA: herramientas de pruebas y análisis, fuera de producción.

El extra `dev` vigente contiene `websockets>=15.0.0`: acepta 16.1.1, por lo que
la combinación `dev,web` no enfrenta un conflicto entre esas dos declaraciones.
Esto no acredita la resolución conjunta de todas las dependencias de QA ni su
compatibilidad en runtime. El extra `dev` conserva su declaración actual.

La instalación habitual conservará la SPA habilitada: el instalador predeterminado
deberá instalar core + web. Un perfil headless explícito podrá instalar sólo core.
La opción `WEB_ENABLED=False` controla carga y arranque; por sí sola no elimina
paquetes de un entorno que ya tiene web instalado. Ambas propiedades se documentan
y se comprueban por separado. No se agrega un fallback silencioso cuando se pide
web y faltan dependencias.

Durante la implementación podrá mantenerse `requirements.txt` como manifest
derivado de core + web para conservar el comando habitual de instalación y añadir
uno derivado de core para headless. El nombre y generación definitivos se fijan
con el cambio de packaging; esa reorganización del perfil predeterminado todavía
no está implementada. `requirements-web.txt` es el perfil opcional de preparación
añadido en la fase 1. Usar los pins candidatos iniciales para el extra web hasta terminar
la integración, y renovar por una resolución y revisión deliberadas. Esto no
convierte los rangos `>=` del core actual en pins.

Usar FastAPI y Uvicorn mínimos, sin `fastapi[standard]` ni `uvicorn[standard]`:
los extras incorporan otras herramientas, motores, watchers y dependencias que
no son requisitos demostrados del bridge. Seleccionar `http='h11'` y
`ws='websockets-sansio'` expresamente en la integración candidata. La fuente de
Uvicorn 0.54.0 ya selecciona SansIO con websockets instalado en modo `auto`, pero
un backend explícito hace visible el contrato y evita variaciones por el entorno.

### Instaladores y comprobador: trabajo pendiente concreto

La lectura de los archivos vigentes confirma:

- `install.sh` instala `requirements.txt` al instalar y actualizar, incluida la
  copia preparada en staging. Las variantes deben conservar datos y validar el
  perfil tanto en staging como en el entorno final antes de arrancar servicios.
- `install.ps1` decide si instala a partir de `scripts/check_runtime_dependencies.py`.
  El comprobador actual conoce únicamente cuatro paquetes core. Añadir FastAPI a
  `requirements.txt` sin ampliar el comprobador permitiría omitir su instalación.
- El comprobador debe recibir/derivar el perfil elegido y comprobar distribución,
  versión e imports del backend correspondiente con el mismo intérprete del
  launcher. El perfil core no deberá importar ASGI para comprobar core.
- Headless exige imports diferidos en la fase 1. Los perfiles, coherencia de
  manifests, instaladores y documentación de despliegue deben quedar cerrados
  antes del cambio predeterminado de la fase 6. La fase 2 necesita que el extra web
  sea instalable para poder integrar ASGI; no basta con aplazar todo a release.

Ningún instalador ni el comprobador que importa dependencias se ejecutó durante
esta revisión.

## Hallazgos del servidor candidato que condicionan la fase 2

Fuentes inspeccionadas dentro de `uvicorn-0.54.0-py3-none-any.whl`,
`websockets-16.1.1-...whl` y `starlette-1.7.0-py3-none-any.whl`:

| Contrato | Evidencia de fuente | Obligación de integración |
| --- | --- | --- |
| Señales | `uvicorn/server.py:88` llama `capture_signals()`; 332–349 instala handlers, los restaura y reemite señales capturadas | El core conserva propiedad de señales. Usar un adaptador localizado para desactivar esa captura, manteniendo `serve()`; el antiguo override `install_signal_handlers()` no cubre esta versión |
| Readiness | `server.py:115` inicia lifespan; listeners se crean antes de `started=True` en 205 | `start()` termina cuando listeners y lifespan están listos; observar también la terminación temprana de la tarea de serve. Crear una tarea no es readiness |
| Fallo de arranque | `server.py:118` y 192 llaman `sys.exit(STARTUP_FAILURE)` ante lifespan fallido/bind estándar fallido | Traducir `SystemExit` dentro de la tarea supervisada en error de arranque del adaptador. Un `except Exception` no basta; cancelar debe seguir propagándose |
| Lifespan | `uvicorn/lifespan/on.py:58` trata error como fallo con `lifespan='on'`; `auto` puede tratar excepciones como protocolo no soportado | Habilitar lifespan explícito y limitarlo a recursos web. No crear radio, MQTT o schedulers en la fábrica |
| Apagado | `server.py:297` limita espera de conexiones/tareas; 309–311 espera lifespan después | `timeout_graceful_shutdown` no limita por sí solo todo el cierre. Integrar presupuesto global existente, limpieza y supervisión; no introducir aquí segundos nuevos |
| Backend WS | `websockets_sansio_impl.py:105` llama `ServerProtocol(extensions=..., max_size=..., logger=...)`; firma presente en `websockets/server.py:78` | Correspondencia estática favorable con 16.1.1; falta handshake/intercambio/cierre reales autorizados |
| Rechazo antes de aceptar | `websockets_sansio_impl.py:265` anuncia `websocket.http.response`, 476 y 528 manejan su start/body; Starlette `websockets.py:189` tiene `send_denial_response()` | Hay soporte estructural para conservar HTTP 401/429 del WS. Comprobar cuerpos/headers/status al migrar, antes de `accept()` |

La captura de `BaseException` dentro del servidor y del backend ASGI no justifica
suprimir cancelaciones en el bridge. El wrapper debe distinguir fallo de arranque,
cancelación y error posterior; conservar referencias y recuperar excepciones.
`workers=1`, `reload=False` y `await Server.serve()` en el loop del bridge evitan
duplicar la propiedad del hardware. No llamar `uvicorn.run()` ni `asyncio.run()`
desde ese loop.

## Estado de aceptación

**Candidato acreditado por resolución y descarga binaria en los seis destinos;
integración y QA pendientes.** Las resoluciones, el recibo binario y las
correspondencias de API por lectura permiten continuar con la fase 1 y preparar
el extra opcional para la fase 2.
No se declara aquí funcionamiento, rendimiento, ahorro de memoria ni compatibilidad
del hardware. Los presupuestos de recursos quedan sin fijar por la respuesta del
usuario, y el presupuesto de apagado requiere conciliar los valores ya existentes.
La ejecución de suites, instalación de producción y transmisión RF siguen siendo
acciones separadas del análisis de dependencias.

## Evolución preparatoria de fase 4 — 2026-10-09

El candidato conserva los mismos pins; no se instaló ni importó el extra web.
La [fase 4](PHASE_4_REPORT.md) utiliza las APIs revisadas por lectura de las ruedas:
`WebSocketRoute` de Starlette 1.7 y hooks `handle_connect`, `start_keepalive`,
`stop_keepalive`, `writable` y `server_state.tasks` de SansIO/Uvicorn 0.54.
El protocolo añade un abort por conexión antes de que corra la aplicación y
ping idle vacío heredado, sin política nueva de cierre por falta de pong.
Su semántica de buffers/fragmentación y contrapresión sigue siendo una puerta
de ejecución. Estas interfaces privadas requieren nueva auditoría al renovar pins.

## Evolución preparatoria de fase 5 — 2026-10-09

La [fase 5](PHASE_5_REPORT.md) genera la especificación OpenAPI 3.1.0 mediante
`build_openapi_schema` y los métodos `model_json_schema` de Pydantic 2.14 sin
invocar endpoints ni deserializar peticiones. El visor local prescinde de Swagger UI
o ReDoc externos y de cualquier paquete npm o CDN; utiliza Vanilla JS/CSS servido
directamente por el adaptador desde `src/web/docs_ui/`. Los pins de dependencias
permanecen inalterados y continúan opcionales sin instalarse en el entorno base.

## Evolución de adopción y auditoría por capas — 2026-10-09

El cambio `933ccce` seleccionó `AsgiWebServer` en el core y retiró el servidor
HTTP nativo. Esta evolución sustituye la propuesta de perfiles opcionales como
descripción de packaging actual, pero conserva las seis resoluciones originales,
sus hashes, restricciones y limitaciones como evidencia fechada. Adoptar el
servidor en código no acredita un despliegue real ni el paso de sus suites.

La auditoría posterior a `fcaf89b` mantiene cuatro pins iniciales y declara
directamente dos distribuciones cuyas interfaces utiliza el adaptador:

| Distribución ASGI | Pin en manifests y checker | Evidencia y razón |
| --- | --- | --- |
| FastAPI | `0.143.0` | Wheel de fase 0; registro de rutas y stack de middleware revisados. |
| Uvicorn | `0.54.0` | Wheel de fase 0; hooks de lifespan, readiness, H11 y WebSocket. |
| Pydantic | `2.14.0` | Wheel de fase 0; modelos descriptivos y generación de JSON Schema. |
| websockets | `16.1.1` | Wheel de fase 0; protocolo SansIO revisado por fuente. |
| Starlette | `1.7.0` | Transitiva de fase 0 declarada ahora directamente por sus interfaces de middleware, rutas y respuestas. |
| h11 | `0.16.0` | Transitiva de fase 0 declarada ahora directamente por el framing HTTP y hooks del protocolo. |

Los seis pins aparecen en [`requirements.txt`](../../requirements.txt), las
dependencias principales y el extra compatible `web` de
[`pyproject.toml`](../../pyproject.toml), y `WEB_DEPENDENCIES` de
[`check_runtime_dependencies.py`](../../scripts/check_runtime_dependencies.py).
Se contrastaron por lectura con METADATA de los wheels locales Windows/CPython
3.10 de fase 0. No se instalaron ni importaron esos paquetes en esta auditoría.
Las interfaces privadas requieren nueva revisión antes de renovar versiones.

`requirements-web.txt` conserva el comando anterior con `-r requirements.txt`,
sin repetir pins. El manifest habitual instala cuatro dependencias core más
seis ASGI; las transitivas siguen sus restricciones y no constituyen un lock
completo con hashes. Los rangos core no se han convertido en pins.

El checker tiene default `web` sin `MESHCORE_PROFILE`, exige igualdad exacta de
las seis versiones ASGI y rechaza pre/dev/post-releases, versiones más nuevas y
builds locales. Core conserva sus mínimos y no importa ASGI durante su probe.
Un perfil inválido devuelve fallo antes de importar paquetes. El argumento
explícito tiene prioridad sobre el entorno; los instaladores lo fijan a
`--profile web` tanto en sus probes de producción como después de instalar.
Los errores de importación muestran el nombre de distribución y tipo de excepción,
sin reflejar su texto crudo. El checker sigue devolviendo 0 al aprobar y 1 ante
fallos; el parser CLI mantiene 2 para argumentos inválidos.

`WEB_ENABLED=false` controla carga y arranque mediante imports diferidos del core;
`--profile core` sólo selecciona una comprobación. Ninguno elimina paquetes de un
entorno ni convierte los instaladores actuales en instaladores headless mínimos.
No existe un manifest mantenido de instalación sólo core, selector del servidor
nativo ni fallback de transporte ante dependencias ASGI ausentes.

Se actualizaron fixtures para perfiles explícitos y se declararon regresiones
aisladas sobre paquetes web ausentes, pins distintos, perfiles inválidos y
sanitización de errores, sin ejecutarlas. AST Python 3.10 y lectura de manifests
son evidencia estática; ejecución en Python 3.10, compatibilidad por destino,
instalación, apagado, REST/WS, rendimiento y hardware siguen pendientes. Se
retiran explícitamente las cifras RSS y garantías SBC sin medición que figuraban
en el informe anterior de fase 6; la respuesta «no importa» no autorizó inventar
presupuestos ni acreditar soporte universal.
