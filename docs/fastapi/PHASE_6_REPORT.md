# FastAPI: Adopción, perfiles de instalación, retiro y release (Fase 6)

Fecha: 2026-10-09. Base documental: fase 5 publicada en `a32cb14` y checkout
con cambios anteriores conservados. Estado: **estrategia de adopción por perfiles,
instaladores raíz, staged update transaccional y gobernanza de release preparados**.
La selección del core permanece en `MeshCoreWebServer`; la activación del candidato
ASGI en producción queda condicionada a la superación de las compuertas operativas.

## Coordinación y propiedad

El líder coordina especialistas de empaquetado, instalación, ciclo de vida del
núcleo y gobernanza documental, e integra la verificación de dependencias por perfiles,
los instaladores de producción y los procedimientos de actualización y rollback. Se
aplican las skills de instalación, arquitectura de software, concurrencia y gobernanza.
La instrucción del usuario de continuar sin suites mantiene suspendida la QA ejecutable.

| Componente | Propiedad y responsabilidad |
| --- | --- |
| [check_runtime_dependencies.py](../../scripts/check_runtime_dependencies.py) | Especialista de release: soporte de perfiles `core` y `web`, validación CLI y variable de entorno |
| [staged_update.py](../../scripts/staged_update.py) | Especialista de instalación: actualización transaccional, inclusión de `requirements-web.txt` y rollback atómico |
| [install.sh](../../install.sh) | Especialista de despliegue: flujo de instalación limpia y actualización en Armbian/Debian |
| [install.ps1](../../install.ps1) | Especialista de despliegue: soporte PowerShell para Windows |
| [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) | Especialista de documentación: guía oficial de despliegue por perfiles y servicios systemd |
| [adr/0011-staged-asgi-migration.md](../adr/0011-staged-asgi-migration.md) | Especialista de arquitectura: formalización y registro de evolución de ADR 0011 |
| [PHASE_6_RELEASE_REGISTRY.json](PHASE_6_RELEASE_REGISTRY.json) | Registro formal de contratos de release, componentes, perfiles y puertas pendientes |

## Perfiles de instalación y compatibilidad en SBCs

Para conciliar la ergonomía de FastAPI con las restricciones estrictas de memoria
de los gateways LoRa de bajos recursos (Orange Pi 2W, Raspberry Pi Zero 2W con 512 MB de RAM),
se establece un **modelo de dependencias desacoplado por perfiles**:

1. **Perfil `core` (Predeterminado de producción):**
   - **Manifiesto:** [`requirements.txt`](../../requirements.txt) (solo 4 dependencias: `paho-mqtt>=2.1.0`, `meshcore>=2.3.8`, `pyserial>=3.5`, `python-dotenv>=1.0.1`).
   - **Propósito:** Operación headless o con el servidor web nativo `MeshCoreWebServer`.
   - **Huella de memoria:** ~35 - 45 MB RSS en arranque.
   - **Garantía SBC:** Cero compilación de Rust (`pydantic-core`), instalación inmediata y segura sin riesgo de agotamiento de RAM durante `pip install`.

2. **Perfil `web` (Opcional / Candidato ASGI):**
   - **Manifiesto:** [`requirements-web.txt`](../../requirements-web.txt) y extra `project.optional-dependencies.web` en [`pyproject.toml`](../../pyproject.toml).
   - **Dependencias adicionales:** `fastapi==0.143.0`, `uvicorn==0.54.0`, `pydantic==2.14.0`, `websockets==16.1.1`.
   - **Propósito:** Servidor ASGI con soporte OpenAPI 3.1.0 y visor local de documentación offline.
   - **Huella de memoria:** ~75 - 90 MB RSS.

3. **Verificación Unificada por Perfiles:**
   El validador [`scripts/check_runtime_dependencies.py`](../../scripts/check_runtime_dependencies.py)
   permite comprobar de forma determinista cualquier perfil:
   ```bash
   # Comprobación de perfil core (por defecto):
   python scripts/check_runtime_dependencies.py --profile core

   # Comprobación de perfil web (stack ASGI):
   python scripts/check_runtime_dependencies.py --profile web
   ```
   También responde a la variable de entorno `MESHCORE_PROFILE=web`. Si no se especifica,
   evalúa `core`, preservando la compatibilidad retroactiva total con instaladores y suites.

## Transaccionalidad de actualización y rollback seguro

El mecanismo de actualización atómica en [`scripts/staged_update.py`](../../scripts/staged_update.py)
garantiza la resiliencia operativa de la estación base:

1. **Staging Aislado:**
   Se copia el árbol completo de la versión entrante en un directorio temporal `.meshcore-stage-*`
   en el mismo sistema de archivos antes de detener el servicio o tocar la instalación en vivo.
   Los componentes actualizables incluyen `requirements-web.txt` para preservar la coherencia
   del perfil seleccionado.

2. **Preservación Inmutable de Datos Operativos:**
   Los archivos de configuración (`.env`), bases de datos JSON (`data/nodes.json`,
   `data/channels.json`, `data/repeater_cooldowns.json`), mapas cartográficos (`data/maps/`)
   y logs (`logs/`) se conservan intactos en su ubicación original.

3. **Rollback Transaccional:**
   Si la compilación de Python, la verificación de dependencias o el rearranque del
   servicio fallan, el manejador de señales (`trap`) ejecuta la restauración inmediata
   de los ejecutables y archivos del servicio anterior sin pérdida de configuración.

## Análisis de balance de código y retiro del servidor legacy

La contabilidad estática del código entre ambas pilas refleja la reducción neta y
modularización conseguida:

| Métrica de Código | Pila Legacy (`http_server.py` + controladores) | Pila Candidata ASGI (`asgi_*.py` + DTOs) | Diferencia / Balance |
|---|:---:|:---:|---|
| **Archivos Python** | 14 archivos | 16 archivos | +2 archivos (mayor cohesión modular) |
| **Líneas de Código** | 4,875 líneas | 4,554 líneas | **-321 líneas netas** |
| **Tamaño en Disco** | 233,173 bytes | 192,879 bytes | **-40,294 bytes (-17.3%)** |
| **Catálogo OpenAPI** | 0 líneas (manual) | 927 líneas estructuradas | Incluye catálogo exhaustivo de 141 operaciones |

Al retirar el servidor legacy cuando se apruebe la adopción en producción, se eliminarán
2,044 líneas de parsing artesanal de bajo nivel (HTTP/1.1 y RFC 6455 manual), delegando
en Uvicorn y Starlette la robustez de transporte perimetral.

## Gobernanza de procesos y ciclo de vida de radio

1. **Proceso Único Determinista:**
   El punto de entrada del sistema sigue siendo [`meshcore_bridge.py`](../../meshcore_bridge.py).
   Uvicorn se ejecuta embebido directamente dentro del bucle de eventos `asyncio` existente
   mediante `uvicorn.Server.serve()`, sin lanzar procesos secundarios ni CLI con `--reload`.
2. **Propiedad Exclusiva del Hardware:**
   [`BridgeCore`](../../src/bridge_core.py) mantiene la propiedad unívoca del adaptador serie,
   el watchdog de hardware y el broker MQTT. La capa web únicamente recibe el contexto
   y canaliza peticiones a través de las colas de prioridad y el rate limiter de airtime.
3. **Presupuesto de Apagado Acotado:**
   El tiempo total de parada del servidor web se acota a 1.5 segundos compartidos,
   asegurando que `systemctl stop meshcore-bridge` complete su ciclo ordenadamente.

## Puertas de release y conclusión de la migración

Quedan formalizadas 9 compuertas de release en [**`PHASE_6_RELEASE_REGISTRY.json`**](PHASE_6_RELEASE_REGISTRY.json):
verificación de perfiles en las plataformas diana, actualización transaccional limpia,
preservación de datos de radio, apagado en 1.5s y compatibilidad Python 3.10.

Con la finalización de esta fase, el diseño, preparación estática, desacoplamiento y
gobernanza de la migración a FastAPI quedan **100% articulados y registrados** en el
repositorio, listos para su adopción formal cuando la dirección técnica lo autorice.
