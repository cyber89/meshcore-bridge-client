# FastAPI: entrega de preparación de la fase 0

Fecha local: 2026-10-08. Base: `457903ddf623768a1c5f90f952fb8b77db45e0c6`
y checkout con modificaciones anteriores. El líder integra tres especialistas
simultáneos de contratos REST, web/seguridad e instalación, además del inventario
interno revisado en la tanda anterior. Cada especialista tuvo archivos propios.

El usuario autorizó comenzar las fases y respondió «no importa» a los equipos y
presupuestos. Posteriormente indicó **«Continúa sin ejecutar suites»**. Esa
instrucción se mantiene: no se ejecutaron pytest, cobertura, mypy, Ruff,
Playwright, fuzzing ni una estación virtual para esta entrega. No se arrancó el
bridge ni se importaron las bibliotecas candidatas. La preparación puede avanzar;
la aceptación operativa y el cambio de servidor siguen pendientes.

## Entregables y evidencia

| Área | Entrega | Resultado y límite |
| --- | --- | --- |
| REST | [Catálogo](REST_CONTRACT_BASELINE.md) | 90 operaciones JSON y un GET de tiles en 70 rutas/plantillas; 39 aliases añaden 50 operaciones. Total 141 operaciones en 109 rutas/plantillas. Conteo estático, no ejercicio de todas las rutas |
| WS, SPA, seguridad, mapas | [Catálogo web](WEB_CONTRACT_BASELINE.md) | Direcciones, mensajes, productores/consumidores, auth, Origin, cuerpos, headers, estáticos y formatos cartográficos. Discrepancias actuales registradas |
| Estado y consumidores | [Contrato interno](INTERNAL_CONTRACT_BASELINE.md) | Ownership de router/contextos/historiales/canales/mapas y tareas; callers y fixtures; propuesta de seam y riesgos del cierre |
| Paquetes y destinos | [Decisiones](DEPENDENCY_DECISIONS.md) | Windows x64, Linux x64 y ARM64 con glibc >=2.17; CPython 3.10 y 3.12. Ningún otro destino queda certificado |
| Resolución y descarga | [Recibo](dependencies/resolution.json) | Seis cierres binarios con identidad, versiones, marcadores, tags y SHA-256; cero incidencias de metadatos. No ejecución de ABI ni rendimiento |
| Base fuente | [Snapshot](SOURCE_SNAPSHOT.json) | Hashes de 95 archivos fuente/configuración/instalación antes de la fase 1. Incluye archivos con cambios anteriores; no datos de runtime ni secretos |

Los catálogos describen comportamiento observado, incluidos defectos. No autorizan
convertir un defecto en especificación permanente. REPEATER y LOCAL siguen fuera
de contactos/chat y la propia clave pública sigue siendo un destino prohibido.

## Procedimiento de dependencias reproducible

Entrada: [candidate.in](dependencies/candidate.in), con cuatro paquetes core
instalados como baseline y cuatro candidatos web. Se utilizó `uv 0.12.24`
instalado exclusivamente en `artifacts/fastapi-phase0/tooling`; el propósito fue
resolver marcadores del destino, sin modificar dependencias de producción ni
herramientas globales. La auditoría usó CPython 3.12.14 del entorno existente.

Resolución por destino:

```text
uv --no-config pip compile docs/fastapi/dependencies/candidate.in
  --python-platform <destino> --python-version <3.10|3.12>
  --only-binary :all: --no-python-downloads
  --default-index https://pypi.org/simple
  --cache-dir artifacts/fastapi-phase0/uv-cache --no-header --no-annotate
  --output-file docs/fastapi/dependencies/<nombre>.txt
```

Destinos UV: `x86_64-pc-windows-msvc`, `x86_64-manylinux_2_17` y
`aarch64-manylinux_2_17`. Se descargó cada manifest con `pip download`,
`--only-binary=:all:`, `--no-deps`, plataforma/ABI/versión correspondientes y
el índice público de PyPI. `--no-deps` es deliberado: el conjunto transitivo ya
había sido resuelto por UV para el destino. Los manifests exactos contienen
34/32 paquetes Windows y 26/24 paquetes por arquitectura Linux (3.10/3.12).

La primera descarga con resolución transitiva de pip se descartó: utilizaba
marcadores del host en parte de las dependencias. La resolución UV y la auditoría
posterior comprueban específicamente `exceptiongroup` y `async-timeout` en 3.10,
WinRT en Windows y dbus-fast en Linux. Los logs y wheels quedan en `artifacts/`
ignorado; manifests y recibo quedan versionados.

```text
.venv/Scripts/python.exe -B scripts/audit_fastapi_phase0.py
```

El [auditor](../../scripts/audit_fastapi_phase0.py) lee ZIP/METADATA, no instala
ni importa candidatos. Compara tags CPython con los destinos, incluyendo wheels
manylinux de glibc anterior compatibles con el piso 2.17. El hash identifica los
bytes descargados; no constituye una autenticación independiente del editor.
El índice declarado documenta el origen usado, no una URL individual por wheel.
La disponibilidad binaria no acredita soporte de un modelo concreto de SBC.

## Decisiones para continuar

1. Preparar el extra `web` opcional desde `pyproject.toml` y un manifest derivado;
   no cambiar instaladores ni el servidor predeterminado en esta fase.
2. Introducir una interfaz neutral y diferir los imports concretos de web.
   Mantener `.router.channels` y una única instancia del router como transición.
3. Preparar ASGI con Uvicorn embebido en el loop existente, sin poseer señales,
   radio, MQTT ni el lifecycle del bridge; conservar recuperación al servidor actual.
4. No fijar cifras de RAM/arranque sin medición ni nuevos límites/timers RF.
   El presupuesto de cierre de 1,5 s proviene del core existente.

La preparación documental y binaria está entregada. La **puerta operativa de
fase 0 permanece pendiente**: imports en destinos, baseline/candidato medidos,
lifecycle y paridad requieren evidencia de ejecución. El avance de infraestructura
se registra como preparación; no se presenta como una puerta aprobada por omisión.
La [fase 1](PHASE_1_REPORT.md) registra lo implementado y lo pendiente.
