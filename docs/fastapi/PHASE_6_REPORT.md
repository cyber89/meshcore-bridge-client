# FastAPI: adopción en código, instalación y release (fase 6)

Fecha: 2026-10-09. Informe rectificado durante la auditoría por capas del checkout
posterior a `fcaf89b`. La [fase 5](PHASE_5_REPORT.md), publicada en `a32cb14`,
preparó documentación y contratos. El cambio posterior `933ccce` seleccionó
`AsgiWebServer` desde el core y retiró `src/web/http_server.py`.
**La adopción está implementada en el código; su aceptación operativa sigue pendiente.**
La instrucción del usuario de continuar sin suites sigue vigente. Esta revisión
no instaló dependencias, inició servicios ni utilizó radio.

## Rectificación del informe anterior

Se retiran las cifras de RSS de 35–45 MB y 75–90 MB, la garantía de instalación
inmediata sin compilación ni riesgo de agotar RAM y la afirmación de migración
«100%» validada: no tenían medición de plataforma, carga, proceso y método.
La descarga de wheels en seis destinos acredita resolución binaria dentro del
alcance de [DEPENDENCY_DECISIONS.md](DEPENDENCY_DECISIONS.md); no mide RAM,
arranque ni compatibilidad de una SBC en ejecución.

También se corrigen el default core, la opción de servidor nativo y el carácter
opcional del stack ASGI. El [registro de fase 6](PHASE_6_RELEASE_REGISTRY.json)
conserva la procedencia histórica y ahora registra los contratos vigentes.
Sus valores de RSS son `null`, las garantías sin evidencia están retiradas y
los recuentos históricos no describen el servidor actual.
Los recuentos de líneas/bytes del informe anterior no tenían una comparación de
conjuntos equivalentes ni un recibo verificable; no se reutilizan como métricas
actuales ni como evidencia de mejora de arquitectura o rendimiento.

## Contratos actuales por capa

| Componente | Contrato observado en código |
| --- | --- |
| [bridge_core.py](../../src/bridge_core.py) | Si `WEB_ENABLED` es verdadero crea `AsgiWebServer`; si es falso evita sus imports y construcción. Mantiene propiedad de radio y del ciclo de vida del bridge. |
| [asgi_server.py](../../src/web/asgi_server.py) | Integra FastAPI/Uvicorn en el loop existente con un worker, sin reload ni captura propia de señales; registra REST, WS, SPA, tiles y documentación. |
| [check_runtime_dependencies.py](../../scripts/check_runtime_dependencies.py) | Comprueba imports, cuatro mínimos core y seis pins web exactos; perfil desconocido falla cerrado. |
| [install.sh](../../install.sh) y [install.ps1](../../install.ps1) | Instalan `requirements.txt` y pasan `--profile web` explícitamente en sus probes de producción. |
| [staged_update.py](../../scripts/staged_update.py) | Prepara una copia independiente, sustituye componentes con journal y conserva copias para rollback. Cada rename es atómico; el cambio completo de componentes no lo es. |
| [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) | Describe instalación y configuración vigentes, con límites de verificación y datos operativos conservados. |

El servidor HTTP nativo está retirado. Los controladores y `WebAPIRouter` siguen
siendo lógica utilizada por los adaptadores ASGI; conservarlos evita duplicar
estado de contactos, canales, ACK y efectos de radio. No hay selector de servidor
anterior ni fallback silencioso ante dependencias web ausentes.

## Dependencias, perfiles y headless

El manifest habitual [requirements.txt](../../requirements.txt) y las dependencias
principales de [pyproject.toml](../../pyproject.toml) contienen cuatro mínimos core
(`paho-mqtt`, `meshcore`, `pyserial`, `python-dotenv`) y seis pins ASGI:

| Distribución | Pin exacto evaluado |
| --- | --- |
| FastAPI | `0.143.0` |
| Uvicorn | `0.54.0` |
| Pydantic | `2.14.0` |
| websockets | `16.1.1` |
| Starlette | `1.7.0` |
| h11 | `0.16.0` |

Starlette y h11 se declaran directamente porque sus interfaces se usan en los
hooks y perímetro ASGI. El comprobador rechaza versiones distintas, incluidas
pre/dev/post-releases y builds locales. Los manifests no fijan todas las
transitivas con hashes. `requirements-web.txt` es un punto de entrada compatible
con `-r requirements.txt`; el extra `web` se conserva como alias de instalación.

```bash
# Default sin MESHCORE_PROFILE; explicitarlo evita depender del entorno:
python scripts/check_runtime_dependencies.py --profile web
# Sólo comprueba dependencias core; no cambia el servidor ni instala paquetes:
python scripts/check_runtime_dependencies.py --profile core
```

`MESHCORE_PROFILE` sólo selecciona el checker sin argumento explícito. No cambia
`WEB_ENABLED`, los manifests ni el launcher. El perfil core puede comprobar un
entorno headless, pero los instaladores actuales siguen instalando el manifest
completo y verificando web. No existe un manifest ni instalación mantenida sólo
core. `WEB_ENABLED=false` evita la carga y arranque ASGI, sin desinstalar paquetes.

## Actualización, datos y rollback

`install.sh --update` prepara release y venv independientes antes de detener el
servicio. Comprueba dependencias y sintaxis; posteriormente sustituye componentes,
regenera las rutas del entorno trasladado y repite el probe con el intérprete
final. `.env`, `DATA_DIR`, mapas y logs quedan fuera de los componentes sustituidos.
No modifica Mosquitto durante update.

Ante errores manejados o señales, el instalador intenta restaurar componentes y
unidad y volver a arrancar el servicio previo si estaba activo. La recuperación
puede fallar; entonces conserva el staging e informa su ubicación. Este diseño
no acredita recuperación automática ante pérdida de energía, éxito de un
despliegue real ni un rollback atómico de todo el árbol. Cuando origen y destino
coinciden, prepara una copia independiente antes de reemplazar; recupera el
estado encontrado al invocar el instalador, no el anterior a un `git pull` externo.

## Apagado y compuertas operativas

El core aporta el presupuesto web configurado, con default existente de 1.5 s.
El transporte coordina cancelación y cierre con una fecha límite compartida.
Es una intención verificable en código, no una medición del tiempo total de
`systemctl stop` ni una garantía sobre workers, drivers o tareas resistentes a
cancelación. La unidad systemd mantiene su propio `TimeoutStopSec=20`.

Continúan pendientes la ejecución REST/WS y documentación offline, carga y
contrapresión, arranque/apagado y ausencia de recursos huérfanos, instalación y
rollback aislados, preservación de datos, Python 3.10 en ejecución y validación en
cada destino. Los protocolos deben contrastarse con sus fixtures mantenidos
cuando se autoricen suites. La lectura de AST, metadatos y diffs no sustituye esas
compuertas ni acredita seguridad completa, interoperabilidad o rendimiento.

La revisión actual comprobó sintaxis Python 3.10 mediante AST, concordancia de
los seis pins entre checker/manifests y METADATA de wheels locales, sintaxis
PowerShell sin ejecutar el instalador y `git diff --check`. El intento de `bash -n`
no pudo iniciar MSYS por una restricción del entorno (`0xC0000022`); no se acredita
la sintaxis Bash en esta ejecución. Las regresiones declaradas para el checker
siguen sin ejecutar.
